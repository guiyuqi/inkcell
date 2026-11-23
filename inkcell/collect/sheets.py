# -*- coding: utf-8 -*-
"""TOOLS/make_grid_sheet.py —— 生成"写字格子纸"：每格一个字，写上几遍自己选。

给方案 C（自己的手写字体）用：写好的纸拍照/扫描回来，由 import_handwriting.py 切格入库。

    # 只写这份报告用到的字（436 汉字 + 字母数字符号），两遍 → 4 页
    ./.venv/bin/python TOOLS/make_grid_sheet.py --charset corpus --passes 2

    # 常用 3500 字（GB2312 一级字），报告用字排在最前面
    ./.venv/bin/python TOOLS/make_grid_sheet.py --charset gb2312 --passes 2

产出（项目目录下）：
    out/sheets-<charset>.pdf     打印用（A4 300dpi）
    out/manifest-<charset>.json  每格是哪个字、在第几页第几行第几列（切格入库用）
    out/preview-<charset>-1.png  第 1 页预览
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from inkcell.paths import load_project

SIMSUN = "/mnt/c/Windows/Fonts/simsun.ttc"
A4_MM = (210.0, 297.0)


# ---------------------------------------------------------------- 字表
def gb2312_level1() -> list[str]:
    """GB2312 一级汉字 3755 个（按拼音序），等于"常用字"。"""
    out = []
    for hi in range(0xB0, 0xD8):
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("gb2312")
            except UnicodeDecodeError:
                continue
            if "\u4e00" <= ch <= "\u9fff":
                out.append(ch)
    return out


def corpus_chars(project: Path, with_ascii: bool = True) -> list[str]:
    """报告里真正出现过的手写字符（汉字 + ASCII + 符号），按首次出现顺序。"""
    data = project / "data"
    try:
        tpl = json.load(open(data / "template_data.json", encoding="utf-8"))
        fill = json.load(open(data / "fill_data.json", encoding="utf-8"))
    except FileNotFoundError:
        return []
    txt = "".join(e["title"] + "".join(i["text"] for i in e["items"]) for e in tpl)
    for v in fill.values():
        for d in v["fill"].values():
            txt += "".join(d.get("lead") or []) + "".join(d.get("text") or [])
            for r in d.get("table") or []:
                txt += "".join(r)
    seen, out = set(), []
    for c in txt:
        if c.isspace() or c in seen:
            continue
        if not with_ascii and c.isascii():
            continue                      # 已有英文字母数据集就不必再写
        seen.add(c)
        out.append(c)
    return out


# ---------------------------------------------------------------- 页面
def build(chars: list[str], passes: int, cols: int, rows: int, cell_mm: float,
          gap_mm: float, dpi: int, outdir: Path, tag: str,
          order: str = "pass-major", pdf: bool = True) -> int:
    k = dpi / 25.4
    W, H = int(A4_MM[0] * k), int(A4_MM[1] * k)
    per_page = cols * rows
    total = len(chars) * passes
    n_pages = math.ceil(total / per_page)

    f_hint = ImageFont.truetype(SIMSUN, int(cell_mm * 0.36 * k))
    f_id = ImageFont.truetype(SIMSUN, int(2.0 * k))
    f_head = ImageFont.truetype(SIMSUN, int(3.6 * k))

    grid_w = cols * (cell_mm + gap_mm) - gap_mm
    grid_h = rows * (cell_mm + gap_mm) - gap_mm
    ox = (A4_MM[0] - grid_w) / 2 * k
    oy = (A4_MM[1] - grid_h) / 2 * k + 4 * k

    pages, cells = [], []
    idx = 0
    for pno in range(1, n_pages + 1):
        im = Image.new("L", (W, H), 255)
        d = ImageDraw.Draw(im)
        head = f"第 {pno} / {n_pages} 页　　{tag}　　（每格一字，别出格；写完请保留四角十字）"
        d.text((W / 2, 6 * k), head, font=f_head, fill=110, anchor="ms")
        # 四角定位十字（切格时用来校正倾斜）
        for cx, cy in ((8 * k, 8 * k), (W - 8 * k, 8 * k),
                       (8 * k, H - 8 * k), (W - 8 * k, H - 8 * k)):
            d.line([(cx - 4 * k, cy), (cx + 4 * k, cy)], fill=0, width=max(2, int(0.35 * k)))
            d.line([(cx, cy - 4 * k), (cx, cy + 4 * k)], fill=0, width=max(2, int(0.35 * k)))
        for r in range(rows):
            for c in range(cols):
                if idx >= total:
                    break
                if order == "char-major":
                    # 同一个字连写 passes 遍（一屏正好四个格子同一个字）
                    ch = chars[idx // passes]
                    pw = idx % passes + 1
                else:
                    ch = chars[idx % len(chars)]
                    pw = idx // len(chars) + 1
                x = ox + c * (cell_mm + gap_mm) * k
                y = oy + r * (cell_mm + gap_mm) * k
                s = cell_mm * k
                d.rectangle([x, y, x + s, y + s], outline=150, width=max(1, int(0.25 * k)))
                # 淡淡的中线（田字格），写完切格时会被阈值去掉
                d.line([(x + s / 2, y), (x + s / 2, y + s)], fill=205, width=1)
                d.line([(x, y + s / 2), (x + s, y + s / 2)], fill=205, width=1)
                # 提示字：左上角，浅灰
                d.text((x + s * 0.06, y + s * 0.05), ch, font=f_hint, fill=196, anchor="la")
                # 格号
                d.text((x + s - 2, y + s - 1), str(idx + 1), font=f_id, fill=190, anchor="rs")
                cells.append({"id": idx + 1, "pass": pw, "page": pno,
                              "row": r, "col": c, "char": ch,
                              "box_px": [int(x), int(y), int(s), int(s)]})
                idx += 1
        pages.append(im)

    outdir.mkdir(parents=True, exist_ok=True)
    if pdf:
        pdf = outdir / f"sheets-{tag}.pdf"
        import img2pdf
        layout = img2pdf.get_layout_fun((img2pdf.mm_to_pt(A4_MM[0]), img2pdf.mm_to_pt(A4_MM[1])))
        pngs = []
        for i, p in enumerate(pages):
            f = outdir / f"_tmp-{tag}-{i + 1:02d}.png"
            p.save(f, dpi=(dpi, dpi))
            pngs.append(f)
        with open(pdf, "wb") as fh:
            img2pdf.convert([str(p) for p in pngs], outputstream=fh, layout_fun=layout)
        for f in pngs:
            f.unlink()
        pages[0].save(outdir / f"preview-{tag}-1.png")
    json.dump({"tag": tag, "passes": passes, "chars": len(chars),
               "cols": cols, "rows": rows, "cell_mm": cell_mm, "gap_mm": gap_mm,
               "dpi": dpi, "pages": n_pages, "cells": cells},
              open(outdir / f"manifest-{tag}.json", "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"  {tag}: {len(chars)} 字 × {passes} 遍 = {total} 格 → {n_pages} 页"
          f"（顺序 {order}{'' if pdf else '，未出 PDF'}）", file=sys.stderr)
    return n_pages


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path, default=Path("."),
                    help="项目目录（--charset corpus 时用它的 data/fill_data.json）")
    ap.add_argument("--charset", default="corpus", choices=["corpus", "gb2312"])
    ap.add_argument("--no-ascii", action="store_true",
                    help="不写 ASCII（已经有英文字母数据集时用）")
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--cols", type=int, default=14)
    ap.add_argument("--rows", type=int, default=21)
    ap.add_argument("--cell-mm", type=float, default=12.0)
    ap.add_argument("--gap-mm", type=float, default=1.0)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--out", type=Path, default=None,
                    help="输出目录，默认 <project>/sheets")
    ap.add_argument("--order", default="pass-major", choices=["pass-major", "char-major"],
                    help="pass-major=整本写完再写下一遍；char-major=同一个字连写几遍")
    ap.add_argument("--no-pdf", action="store_true", help="只出 manifest，不出格子纸 PDF")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    outdir = Path(args.out) if args.out else load_project(project).sheets

    if args.charset == "corpus":
        chars = corpus_chars(project, with_ascii=not args.no_ascii)
        tag = "corpus"
    else:
        gb = gb2312_level1()
        used = corpus_chars(project, with_ascii=not args.no_ascii)
        # 报告用字（含 ASCII、标点、⊕ ≥ → 这类符号）全部排最前，
        # 后面再按拼音序补 GB2312 —— 只写前一百多屏，报告就已经全是真迹了
        head = list(used)
        tail = [c for c in gb if c not in set(head)]
        chars = head + tail
        tag = "gb2312"

    if not chars:
        print("!! 没有字表（--charset corpus 需要项目里有 data/）")
        return 2
    build(chars, args.passes, args.cols, args.rows, args.cell_mm, args.gap_mm,
          args.dpi, outdir, tag, order=args.order, pdf=not args.no_pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
