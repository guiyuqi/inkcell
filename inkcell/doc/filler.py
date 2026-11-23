# -*- coding: utf-8 -*-
"""在**原 .docx** 里填空：不动一个字、不动一个格式，只把每个空格子里贴上手写图。

    ./.venv/bin/python docx_fill.py --docx work/doc/tpl.docx --out out/report-final.docx

原理：
  1. 用 python-docx 读段落，按学校条目（"1.真值表"这类）找到它的位置；
  2. 条目后面那一串空段落就是"格子"，从它们的段落格式里算出格子有多高（磅）；
  3. 按格子的物理宽高画一张手写图（hw/slot.py），塞进第一个空段落并撑满这个宽度；
  4. 删掉这一格里多余的空段落，格子占的高度不变 → 整篇版面一个字都不会动。
"""
from __future__ import annotations

import argparse
import numpy as np
import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Length
from docx.shared import Pt, RGBColor

from inkcell.render.anchor import to_anchor
from inkcell.render.core import Hand
from inkcell.render.slot import render_bands, render_figure

from inkcell.paths import default_fonts, load_project       # noqa: E402

HERE = Path(__file__).resolve().parent
SRC = Path(".")          # 由 --project 覆盖


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\t", " ").replace("\u3000", " ")).strip()


# ------------------------------------------------------------------ 段落度量
def para_size_pt(p) -> float:
    for r in p.runs:
        if r.font.size is not None:
            return r.font.size.pt
    try:
        st = p.style
        while st is not None:
            if st.font.size is not None:
                return st.font.size.pt
            st = st.base_style
    except Exception:
        pass
    return 10.5


def _dim_pt(val: str | None, per_twip: float = 1 / 20.0) -> float | None:
    """Strict 版会写成 "18pt"，普通版是 twips 数字。统一换成磅。"""
    if not val:
        return None
    v = val.strip()
    try:
        if v.endswith("pt"):
            return float(v[:-2])
        if v.endswith("in"):
            return float(v[:-2]) * 72.0
        if v.endswith("mm"):
            return float(v[:-2]) / 25.4 * 72.0
        if v.endswith("cm"):
            return float(v[:-2]) / 2.54 * 72.0
        if v.endswith("%"):
            return None
        return float(v) * per_twip
    except ValueError:
        return None


def line_height_pt(p, default: float = 10.5) -> float:
    """一条空行占多高（含段前段后），单位磅。"""
    pPr = p._p.pPr
    line = rule = None
    in_twips = False                 # line 这个数字是"缇(1/20 磅)"还是"磅"
    before = after = 0.0
    if pPr is not None:
        sp = pPr.find(qn("w:spacing"))
        if sp is not None:
            raw_line = sp.get(qn("w:line"))
            rule = sp.get(qn("w:lineRule")) or "auto"
            if raw_line:
                if re.match(r"^[\d.]+$", raw_line):        # 纯数字：缇，或 1/240 行
                    line = float(raw_line)
                    in_twips = True
                else:                                       # Strict 的 "18pt"
                    line = _dim_pt(raw_line, per_twip=0.05)
                    in_twips = False
                    if line is not None and rule == "auto":
                        rule = "exact"
            before = _dim_pt(sp.get(qn("w:before"))) or 0.0
            after = _dim_pt(sp.get(qn("w:after"))) or 0.0
    # 段落自己没有设行距，就去样式链上找
    if line is None:
        try:
            st = p.style
            while st is not None:
                ls = st.paragraph_format.line_spacing
                if ls is not None:
                    # 注意 docx.shared.Length 是 int 的子类（EMU 值），必须先判它，
                    # 否则 18pt 会被当成"18 倍行距"→ 高度放大两百万倍。
                    if isinstance(ls, Length):
                        line, rule, in_twips = float(ls.pt), "exact", False
                    else:                                    # 倍数（float）
                        line, rule, in_twips = float(ls) * 240.0, "auto", True
                    break
                st = st.base_style
            st = p.style
            while st is not None:
                if not before and st.paragraph_format.space_before is not None:
                    before = st.paragraph_format.space_before.pt
                if not after and st.paragraph_format.space_after is not None:
                    after = st.paragraph_format.space_after.pt
                st = st.base_style
        except Exception:
            pass

    size = para_size_pt(p) or default
    if line is None:
        h = size * 1.2
    elif rule in ("exact", "atLeast"):
        h = (line / 20.0) if in_twips else line          # 缇 → 磅
    else:                                                # auto：1/240 行
        h = (line / 240.0) * size * 1.2
    return h + before + after


def is_blank(p) -> bool:
    if p.text.strip():
        return False
    xml = p._p.xml
    return "<w:drawing" not in xml and "<w:pict" not in xml


def text_width_pt(doc, p) -> float:
    sec = doc.sections[0]
    usable = sec.page_width.pt - sec.left_margin.pt - sec.right_margin.pt
    try:
        pf = p.paragraph_format
        if pf.left_indent:
            usable -= pf.left_indent.pt
        if pf.right_indent:
            usable -= pf.right_indent.pt
    except Exception:
        pass
    return max(60.0, usable)


# ------------------------------------------------------------------ 贴代码
CODE_MONO = "/mnt/c/Windows/Fonts/consola.ttf"
CODE_CJK = "/mnt/c/Windows/Fonts/simsun.ttc"


def paste_code(doc, blanks, lines: list[str], size_pt: float = 9.0,
               pitch_pt: float = 11.6) -> int:
    """把代码当成正文文字贴进这些空段落；不够就克隆最后一段的格式继续加。

    返回用掉的行数。字号/行距按"打印体代码"设，不参与手写那一套。
    """
    from docx.oxml import OxmlElement
    from docx.shared import Pt as _Pt

    def style_para(p, text: str) -> None:
        for r in list(p.runs):
            r._r.getparent().remove(r._r)
        pPr = p._p.get_or_add_pPr()
        sp = pPr.find(qn("w:spacing"))
        if sp is None:
            sp = OxmlElement("w:spacing")
            pPr.append(sp)
        sp.set(qn("w:line"), str(int(round(pitch_pt * 20))))
        sp.set(qn("w:lineRule"), "exact")
        sp.set(qn("w:before"), "0")
        sp.set(qn("w:after"), "0")
        p.paragraph_format.left_indent = _Pt(0)
        p.paragraph_format.first_line_indent = _Pt(0)
        run = p.add_run(text if text else "")
        run.font.size = _Pt(size_pt)
        run.font.name = "Consolas"
        rPr = run._r.get_or_add_rPr()
        rf = rPr.find(qn("w:rFonts"))
        if rf is None:
            rf = OxmlElement("w:rFonts")
            rPr.append(rf)
        rf.set(qn("w:ascii"), "Consolas")
        rf.set(qn("w:hAnsi"), "Consolas")
        rf.set(qn("w:eastAsia"), "宋体")

    last = None
    for k, line in enumerate(lines):
        if k < len(blanks):
            style_para(blanks[k], line)
            last = blanks[k]
            continue
        if last is None:
            return k
        from docx.text.paragraph import Paragraph
        import copy as _copy
        new_el = _copy.deepcopy(last._p)
        last._p.addnext(new_el)
        last = Paragraph(new_el, last._parent)
        style_para(last, line)
    return min(len(lines), len(blanks) + max(0, len(lines) - len(blanks)))


# ------------------------------------------------------------------ 封面字段
def _width(t: str) -> int:
    return sum(2 if ord(c) > 0x2E80 else 1 for c in t)


def fill_cover(doc, values: dict[str, str]) -> int:
    """往封面已有的下划线空格里填字，格式（字号/下划线）一律沿用原来的 run。"""
    done = 0
    for p in doc.paragraphs[:40]:
        t = norm(p.text)
        for label, val in values.items():
            if not t.startswith(label):
                continue
            runs = p.runs
            ul = [r for r in runs if r.font.underline]
            if not ul:                       # 日期这种没有下划线的，单独处理
                continue
            total = sum(_width(r.text) for r in ul)
            body = " " + val
            pad = max(0, total - _width(body))
            ul[0].text = body + " " * pad
            for r in ul[1:]:
                r.text = ""
            done += 1
    # 日期：年 月 日
    for p in doc.paragraphs[:40]:
        if not norm(p.text).startswith("日期"):
            continue
        rs = p.runs
        texts = [r.text for r in rs]
        joint = "".join(texts)
        if "年" in joint and "月" in joint and "日" in joint and "2026" not in joint:
            plan = [" ", "2026 ", "年", "  ", "11 ", "月", "  ", "19 日"]
            for i, r in enumerate(rs[1:1 + len(plan)]):
                r.text = plan[i]
            done += 1
    return done


# ------------------------------------------------------------------ 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docx", type=Path, required=True)
    ap.add_argument("--project", type=Path, default=Path("."),
                    help="项目目录（数据在 data/，产物在 out/）")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--font", action="append", default=None)
    ap.add_argument("--body-pt", type=float, default=11.0, help="手写字大小（磅）")
    ap.add_argument("--bold", type=int, default=1)
    ap.add_argument("--noise", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20261119)
    ap.add_argument("--only", default="", help="只填某几道，如 实验一,实验六")
    ap.add_argument("--dump", action="store_true", help="只打印段落结构，不填")
    ap.add_argument("--code-pt", type=float, default=9.0, help="贴代码的字号（磅）")
    ap.add_argument("--code-pitch", type=float, default=11.6, help="贴代码的行距（磅）")
    ap.add_argument("--glyphs", type=Path, default=None,
                    help="真迹字库目录（默认 <project>/glyphs）")
    ap.add_argument("--figures", type=Path, default=None,
                    help="图目录（默认 <project>/assets/figures）")
    ap.add_argument("--code-dir", type=Path, default=None,
                    help="代码目录（默认 <project>/assets/code）")
    ap.add_argument("--cover", type=Path, default=None,
                    help="封面字段 JSON（默认 <project>/data/cover.json）")
    ap.add_argument("--no-handwriting", action="store_true", help="不用真迹，退回字体")
    args = ap.parse_args()
    args.project = Path(args.project).resolve()
    proj = load_project(args.project)
    SRC = proj.assets                     # 图/代码的相对根
    args.out = Path(args.out) if args.out else proj.out / "report.docx"
    args.font = args.font or [str(p) for p in default_fonts()]
    FILLS = proj.fill_data
    if not FILLS.exists():
        print(f"!! 没有内容数据：{FILLS}", file=sys.stderr)
        return 2
    fig_dir = Path(args.figures) if args.figures else proj.figures
    code_dir = Path(args.code_dir) if args.code_dir else proj.code
    cover_json = Path(args.cover) if args.cover else proj.cover

    from inkcell.doc.strict2trans import convert, is_strict
    src = args.docx
    if is_strict(src):
        fixed = args.project / "src_docx" / (src.stem + "-trans.docx")
        fixed.parent.mkdir(parents=True, exist_ok=True)
        convert(src, fixed)
        print(f"（Strict → 普通 OOXML: {fixed}）", file=sys.stderr)
        src = fixed
    doc = Document(str(src))
    paras = doc.paragraphs

    # 结构转储：先看清"条目 + 空格子"到底长什么样
    if args.dump:
        for i, p in enumerate(paras):
            t = norm(p.text)
            if t or i < 12:
                print(f"{i:4d} [{line_height_pt(p):5.1f}pt] {t[:56]}")
        return 0

    fills = json.load(open(FILLS, encoding="utf-8"))
    # 数据格式（两种都行）：
    #   1) 分节：{ "实验一 半加器实验": {"fill": {"一、实验目的": {...}}}, ... }
    #   2) 扁平：{ "一、实验目的": {...}, "二、实验原理": {...} }
    if not any(isinstance(v, dict) and "fill" in v for v in fills.values()):
        fills = {"": {"fill": {k: v for k, v in fills.items()
                               if not k.startswith("_")}}}
    else:
        for k, v in fills.items():
            if "fill" not in v:
                v["fill"] = {ik: iv for ik, iv in v.items() if not ik.startswith("_")}
    gdir_hint = Path(args.glyphs) if args.glyphs else proj.glyphs
    if not args.font and not args.no_handwriting and not (gdir_hint / "index.json").exists():
        print("!! 既没有真迹字库也没有回落字体；先写字入库，或把 .ttf 放进 assets/fonts/",
              file=sys.stderr)
        return 2
    hand = Hand(name="inkcell", fonts=[Path(f) for f in args.font], variants=4)

    # 真迹字库：有位图就用位图，缺字自动回落到字体
    book = None
    if not args.no_handwriting:
        from inkcell.glyph.bitmap import BitmapGlyphs, HybridBook
        gdir = Path(args.glyphs) if args.glyphs else proj.glyphs
        if (gdir / "index.json").exists():
            bitmap = BitmapGlyphs(gdir)
            book = HybridBook(hand, seed=args.seed, bitmap=bitmap)
            print(f"  真迹字库：{len(bitmap.chars)} 字（{gdir}）", file=sys.stderr)
        else:
            print(f"  !! 没有字形索引：{gdir/'index.json'}，退回字体渲染", file=sys.stderr)

    cover_values = {}
    if cover_json.exists():                       # data/cover.json：{"班 级": "…"}
        cover_values = json.load(open(cover_json, encoding="utf-8"))
    n_cov = fill_cover(doc, cover_values) if cover_values else 0
    if n_cov:
        print(f"  封面填了 {n_cov} 栏（印刷体）", file=sys.stderr)

    outdir = args.project / "work" / "slots"
    outdir.mkdir(parents=True, exist_ok=True)

    cur_exp = "" if "" in fills else None
    cur_fill: dict = fills[""]["fill"] if "" in fills else {}
    stat = {"slots": 0, "imgs": 0}

    i = 0
    n = len(paras)
    while i < n:
        p = paras[i]
        t = norm(p.text)

        # 章节：段落文字就是（或以 fill_data 的某个 key 开头）→ 切换当前章节
        if cur_exp is None or (cur_exp not in fills):
            pass
        key = next((k for k in fills if k and
                    (t.startswith(norm(k)) or norm(k) in t)), None)
        if key is not None and len(t) <= len(norm(key)) + 20:
            cur_exp = key
            cur_fill = fills[key]["fill"]
            cur_dir = (fig_dir / fills[key]["dir"] / "figures"
                       if fills[key].get("dir") else fig_dir)
            # 不 continue：同一个段落可能就是条目标题，交给下面的 slot 匹配

        slot = None
        if cur_fill and t:
            for k, v in cur_fill.items():
                if t.startswith(norm(k)) or norm(k) in t:
                    slot = (k, v)
                    break

        # 数一数后面有几个空段落 = 这个格子有几行
        if slot:
            j = i + 1
            while j < n and is_blank(paras[j]):
                j += 1
            blanks = paras[i + 1:j]
            only = [norm(k) for k in args.only.split(",") if k.strip()]
            skip = bool(only) and not any(norm(cur_exp or "").startswith(o[:3]) for o in only)
            if blanks and not skip:
                W = text_width_pt(doc, blanks[0])
                heights = [line_height_pt(b) for b in blanks]
                H = sum(heights)
                s_rng = np.random.default_rng(args.seed + stat["slots"] * 7 + 13)
                body_pt = max(8.0, min(16.0, args.body_pt * float(s_rng.normal(1.0, 0.05))))

                if slot[1].get("code"):
                    from inkcell.render.slot import load_code
                    src_dir = code_dir
                    lines = load_code(slot[1]["code"], src_dir)
                    used = paste_code(doc, blanks, lines, size_pt=args.code_pt,
                                      pitch_pt=args.code_pitch)
                    print(f"     贴代码 {len(lines)} 行（占 {used} 个空行，其余另起）",
                          file=sys.stderr)
                    stat["imgs"] += 1
                    i = j
                    continue

                if slot[1].get("figure"):
                    # 电路图：整格一张，不分条（分条会把线条切开）
                    img = render_figure(slot[1], W - 4, H, cur_dir, dpi=300)
                    if img is not None:
                        stat["slots"] += 1
                        png = outdir / f"slot{stat['slots']:02d}_fig.png"
                        img.save(png, dpi=(300, 300))
                        run = blanks[0].add_run()
                        run.font.size = Pt(para_size_pt(blanks[0]))
                        run.add_picture(str(png), width=Pt(W - 4), height=Pt(H))
                        dr = run._r.find(qn("w:drawing"))
                        if dr is not None:
                            to_anchor(dr, offset_y=0, shape_id=stat["slots"] * 100)
                        stat["imgs"] += 1
                        stat.setdefault("calc", []).append((slot[0], round(H, 1), body_pt))
                else:
                    items = render_bands(slot[1], W - 4, heights, hand,
                                         seed=args.seed + stat["slots"], dpi=300,
                                         bold=args.bold, noise=args.noise, body_pt=body_pt,
                                         book=book)
                    if items:
                        stat["slots"] += 1
                        sid = stat["slots"] * 100
                        for nn, (bi, span, strip) in enumerate(items):
                            spng = outdir / f"slot{stat['slots']:02d}_{nn:02d}.png"
                            strip.save(spng, dpi=(300, 300))
                            acc_h = sum(heights[bi:bi + span])
                            run = blanks[bi].add_run()
                            run.font.size = Pt(para_size_pt(blanks[bi]))
                            run.add_picture(str(spng), width=Pt(W - 4), height=Pt(acc_h))
                            dr = run._r.find(qn("w:drawing"))
                            if dr is not None:
                                to_anchor(dr, offset_y=0, shape_id=sid + nn)
                            stat["imgs"] += 1
                        stat.setdefault("calc", []).append((slot[0], round(H, 1), body_pt))
            i = j
            continue

        i += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(args.out))
    print(f"✔ {args.out}  填了 {stat['imgs']} 个格子（手写图在 work/slots/）", file=sys.stderr)
    sizes = [b for _, _, b in stat.get("calc", [])]
    if sizes:
        print(f"  每格字号 {min(sizes):.1f}~{max(sizes):.1f}pt", file=sys.stderr)
    tot = sum(h for _, h, _ in stat.get("calc", []))
    print(f"  格子总高 {tot:.0f}pt（≈{tot / 72 * 2.54:.1f}cm），"
          f"每格平均 {tot / max(1, len(stat.get('calc', []))):.0f}pt", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
