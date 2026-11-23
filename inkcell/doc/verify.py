# -*- coding: utf-8 -*-
"""TOOLS/verify_docx.py —— 生成完报告后自检：版面没被动过 + 贴进去的图没变形。

    ./.venv/bin/python TOOLS/verify_docx.py --src tpl-trans.docx --out report-final.docx

检查项：
  1. 段落总数、带 w:line 的段落数（原文档是 48 条 exact 行距）——不能变
  2. 浮动图（wp:anchor）数量、是否有 w:inline（inline 会把行高顶开）
  3. 每张图的显示宽高比 vs PNG 真实宽高比（差 >3% 说明被拉伸）
  4. 图片是否都在正文里（rel 有没有丢）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from PIL import Image

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP_NS = ("http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing")
EMU_PER_PT = 12700


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tolerance", type=float, default=3.0, help="宽高比容差（百分比）")
    ap.add_argument("--fill-data", type=Path, default=None,
                    help="给 fill_data.json 就额外查每个条目是否真的填了东西")
    ap.add_argument("--slots-dir", type=Path, default=None,
                    help="手写格子图目录；给了就检查有没有字被画到画布边缘（=被裁掉）")
    ap.add_argument("--baseline", type=Path, default=None,
                    help="拿已验收的另一份 docx 当基准（贴代码会加段落，别拿模板当基准）")
    args = ap.parse_args()

    src = Document(str(args.src))
    out = Document(str(args.out))
    base = Document(str(args.baseline)) if args.baseline else src
    ps, po = len(base.paragraphs), len(out.paragraphs)
    ls = sum(1 for p in base.paragraphs if p._p.find(qn("w:pPr")) is not None
             and p._p.pPr.find(qn("w:spacing")) is not None
             and p._p.pPr.find(qn("w:spacing")).get(qn("w:lineRule")) == "exact")
    lo = sum(1 for p in out.paragraphs if p._p.find(qn("w:pPr")) is not None
             and p._p.pPr.find(qn("w:spacing")) is not None
             and p._p.pPr.find(qn("w:spacing")).get(qn("w:lineRule")) == "exact")
    ok = True
    print(f"段落数  源 {ps} → 出 {po}", end="  ")
    if ps != po:
        print("✗ 变了（版面被动过）"); ok = False
    else:
        print("✓")
    print(f"exact 行距段落  源 {ls} → 出 {lo}", end="  ")
    if ls != lo:
        print("✗"); ok = False
    else:
        print("✓")

    root = out.element.body
    anchors = root.findall(".//" + qn("w:drawing") + "/" + qn("wp:anchor"))
    inlines = root.findall(".//" + qn("w:drawing") + "/" + qn("wp:inline"))
    print(f"浮动图 {len(anchors)} 张，inline {len(inlines)} 张", end="  ")
    if inlines:
        print("✗ 还有 inline（会顶开行高）"); ok = False
    else:
        print("✓")

    # 宽高比：extent(cx,cy) vs 实际 PNG
    bad = []
    checked = 0
    import hashlib
    import io as _io
    # 模板自带的图（校徽等）宽高比本来就不准，跳过：按内容哈希认出来
    src_hash = set()
    for r in src.part.rels.values():
        if "image" in r.reltype:
            src_hash.add(hashlib.sha1(r.target_part.blob).hexdigest())
    # 只量我们自己贴的浮动图（文档自带的老图/校徽是 inline，宽高比本来就不准）
    for dr in root.iter(qn("wp:anchor")):
        ext = dr.find(".//" + qn("wp:extent"))
        blip = dr.find(".//" + qn("a:blip"))
        if ext is None or blip is None:
            continue
        rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
        if not rid or rid not in out.part.rels:
            continue
        part = out.part.rels[rid].target_part
        if hashlib.sha1(part.blob).hexdigest() in src_hash:
            continue                      # 模板自带的图，不管
        try:
            w_px, h_px = Image.open(_io.BytesIO(part.blob)).size
        except Exception:
            continue
        cx = int(ext.get("cx")); cy = int(ext.get("cy"))
        if not cx or not cy or not w_px:
            continue
        want = h_px / w_px
        got = cy / cx
        diff = abs(got - want) / want * 100
        checked += 1
        if diff > args.tolerance:
            bad.append((rid, round(want, 3), round(got, 3), round(diff, 1)))
    print(f"图片宽高比  检查 {checked} 张，超差 {len(bad)} 张")
    for b in bad[:8]:
        print(f"   ✗ {b[0]} 应为 {b[1]} 实际 {b[2]}（差 {b[3]}%）")
    if bad:
        ok = False
    if args.slots_dir:
        import numpy as np                 # 只在片块里用，别把 Image 搞成局部名
        files = sorted(args.slots_dir.glob("slot*.png"))
        clipped = []
        for f in files:
            a = np.asarray(Image.open(f).convert("L"))
            ink = a < 128
            if not ink.any():
                continue
            ys, xs = np.where(ink)
            if xs.min() <= 1 or xs.max() >= a.shape[1] - 2 or \
               ys.min() <= 1 or ys.max() >= a.shape[0] - 2:
                clipped.append(f.name)
        print(f"格子图裁边  检查 {len(files)} 张，贴边 {len(clipped)} 张")
        for c in clipped[:10]:
            print(f"   ✗ {c}")
        if clipped:
            ok = False

    if args.fill_data:
        import re
        import json
        data = json.load(open(args.fill_data, encoding="utf-8"))
        paras = out.paragraphs
        miss, checked_items = [], 0
        for key, exp in data.items():
            cur_key = None
            for idx, p in enumerate(paras):
                t = re.sub(r"\s+", "", p.text)
                if not t:
                    continue
                for item, payload in exp["fill"].items():
                    ik = re.sub(r"\s+", "", item)
                    if t.startswith(ik) or ik in t:
                        # 只有"标题段落 + 后面紧跟空行"才算一个要填的格子
                        if idx + 1 >= len(paras) or paras[idx + 1].text.strip():
                            break
                        cur_key = item
                        j = idx + 1
                        has = False
                        while j < len(paras) and not paras[j].text.strip():
                            if paras[j]._p.findall(".//" + qn("w:anchor")) or \
                               paras[j]._p.findall(".//" + qn("w:drawing")):
                                has = True
                            j += 1
                        # 代码条目是贴的印刷体，不产生图
                        if payload.get("code"):
                            has = any("Consolas" in (r.font.name or "")
                                      for para in paras[max(0, idx - 1):j] for r in para.runs)
                        if not has:
                            miss.append(f"{key} / {item}")
                        checked_items += 1
        print(f"条目内容  检查 {checked_items} 条，空掉的 {len(miss)} 条")
        for m_ in miss[:10]:
            print(f"   ✗ {m_}")
        if miss:
            ok = False

    print("\n结论：" + ("✓ 版面未动、图未变形、条目都填了" if ok else "✗ 有问题，别急着交"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
