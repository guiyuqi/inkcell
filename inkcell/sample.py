# -*- coding: utf-8 -*-
"""TOOLS/make_sample.py —— 用（部分）真笔迹 + 缺字回落，拼一段样张，看效果。

    ./.venv/bin/python TOOLS/make_sample.py --text "实验一半加器实验"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from inkcell.paths import default_fonts, load_project

from inkcell.glyph.bitmap import BitmapGlyphs, HybridBook
from inkcell.render.core import Hand, Ink, Paper
from inkcell.render.layout import Style, Writer



def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path, default=Path("."), help="项目目录")
    ap.add_argument("--text", default="inkcell 写字台 0123 半加器 S=A⊕B")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--size", type=int, default=56)
    ap.add_argument("--glyphs", type=Path, default=None, help="换一个字形库目录")
    args = ap.parse_args()

    proj = load_project(args.project)
    gdir = args.glyphs or proj.glyphs
    args.out = args.out or (proj.out / "sample.png")
    bitmap = BitmapGlyphs(gdir) if (gdir / "index.json").exists() else None
    fonts = default_fonts()
    if not fonts and not (gdir / "index.json").exists():
        print("!! 既没有字库 (glyphs/index.json)，也没有回落字体。\n"
              "   要么先写字入库，要么把 .ttf 放进 assets/fonts/（或设 INKCELL_FONTS）。",
              file=sys.stderr)
        return 2
    hand = Hand("inkcell", fonts, variants=2)
    w = Writer(hand=hand, paper=Paper(dpi=200), style=Style(body=args.size),
               ink=Ink(bold=1), seed=3)
    w.book = HybridBook(hand, seed=3, bitmap=bitmap)
    w.paragraph(args.text)
    page = w.finish(page_numbers=False)[0]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    page.crop((150, 150, 1500, 460)).save(args.out)
    covered = sum(1 for c in args.text if bitmap and bitmap.has(c))
    print(f"✔ {args.out}　用真迹 {covered}/{len(args.text.replace(' ', ''))} 字"
          f"（其余回落到字体）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
