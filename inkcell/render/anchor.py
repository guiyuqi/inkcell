# -*- coding: utf-8 -*-
"""hw/anchor.py —— 把"嵌入型图片"(inline) 改成"浮动图"(anchor, 衬于文字下方)。

为什么要这么干：
  嵌入型图片会参与行高计算，插进去就把排版顶走（条目会跑到别的页）。
  浮动图不参与排版：段落还是原来那些空行，图只是"浮"在那片空白上，
  所以 Word 的分页、行高、段距一个字都不会变。
"""
from __future__ import annotations

from docx.oxml.ns import nsdecls, qn
from lxml import etree

WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"


def to_anchor(drawing, offset_x: int = 0, offset_y: int = 0,
              behind_doc: bool = True, shape_id: int = 1) -> None:
    """把 <w:drawing>/<wp:inline> 就地换成 <wp:anchor>。drawing 是 w:drawing 元素。"""
    inline = drawing.find(qn("wp:inline"))
    if inline is None:
        return
    extent = inline.find(qn("wp:extent"))
    graphic = inline.find(qn("a:graphic"))
    docPr = inline.find(qn("wp:docPr"))
    if extent is None or graphic is None:
        return

    anchor = etree.SubElement(drawing, f"{{{WP}}}anchor")
    anchor.set("distT", "0")
    anchor.set("distB", "0")
    anchor.set("distL", "0")
    anchor.set("distR", "0")
    anchor.set("simplePos", "0")
    anchor.set("relativeHeight", str(251658240 + shape_id))
    anchor.set("behindDoc", "1" if behind_doc else "0")
    anchor.set("locked", "0")
    anchor.set("layoutInCell", "1")
    anchor.set("allowOverlap", "1")

    sp = etree.SubElement(anchor, f"{{{WP}}}simplePos")
    sp.set("x", "0")
    sp.set("y", "0")

    ph = etree.SubElement(anchor, f"{{{WP}}}positionH")
    ph.set("relativeFrom", "column")
    etree.SubElement(ph, f"{{{WP}}}posOffset").text = str(int(offset_x))

    pv = etree.SubElement(anchor, f"{{{WP}}}positionV")
    pv.set("relativeFrom", "paragraph")
    etree.SubElement(pv, f"{{{WP}}}posOffset").text = str(int(offset_y))

    anchor.append(extent)
    ee = etree.SubElement(anchor, f"{{{WP}}}effectExtent")
    for k in ("l", "t", "r", "b"):
        ee.set(k, "0")
    etree.SubElement(anchor, f"{{{WP}}}wrapNone")

    if docPr is not None:
        docPr.set("id", str(shape_id))
        docPr.set("name", f"hw-{shape_id}")
        anchor.append(docPr)

    cnv = etree.SubElement(anchor, f"{{{WP}}}cNvGraphicFramePr")
    locks = etree.SubElement(cnv, "{http://schemas.openxmlformats.org/drawingml/2006/main}graphicFrameLocks")
    locks.set("noChangeAspect", "1")

    anchor.append(graphic)
    drawing.remove(inline)
