# -*- coding: utf-8 -*-
"""造一份演示用模板 docx（没有学校模板也能跑通）。

结构刻意做成"条目 + 若干空段落"——inkcell 就是往这些空段落里贴字迹图，
空段落本身就是版面留白，所以版面天然不会被改动。

    python examples/demo/make_demo_docx.py
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.shared import Pt

HERE = Path(__file__).resolve().parent
OUT = HERE / "src_docx" / "demo.docx"

ITEMS = [
    ("一、实验目的", 2),
    ("二、实验原理", 3),
    ("三、实验结果", 4),
    ("四、实验心得", 3),
]


def main() -> int:
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "SimSun"
    st.font.size = Pt(10.5)
    st.paragraph_format.line_spacing = Pt(18)

    doc.add_paragraph("inkcell 演示文档")
    doc.add_heading("说明：下面每个条目后的空行都会被填上手迹（字体或你的字库）", level=2)
    for title, blanks in ITEMS:
        p = doc.add_paragraph()
        r = p.add_run(title)
        r.bold = True
        r.font.size = Pt(12)
        for _ in range(blanks):
            doc.add_paragraph("")          # ← 这些空行 = 要填字的"格子"
    doc.add_paragraph("—— 完 ——")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT))
    print(f"✔ {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
