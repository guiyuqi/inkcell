# -*- coding: utf-8 -*-
"""hw/strict2trans.py —— 把 Word 的 "Strict Open XML" 转成普通 (Transitional) OOXML。

Word 另存为 .docx 时，如果文档是从旧 .doc 转来的，可能存成 Strict 版：
关系类型和命名空间是 http://purl.oclc.org/ooxml/...，python-docx 一律读不了。
这里只把这些 URI 换成 schemas.openxmlformats.org 的写法，其余字节不动。
"""
from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

MAP = {
    "http://purl.oclc.org/ooxml/officeDocument/relationships":
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "http://purl.oclc.org/ooxml/officeDocument/math":
        "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "http://purl.oclc.org/ooxml/wordprocessingml/main":
        "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/drawingml/main":
        "http://schemas.openxmlformats.org/drawingml/2006/main",
    "http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing":
        "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "http://purl.oclc.org/ooxml/drawingml/spreadsheetDrawing":
        "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "http://purl.oclc.org/ooxml/drawingml/chart":
        "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "http://purl.oclc.org/ooxml/drawingml/diagram":
        "http://schemas.openxmlformats.org/drawingml/2006/diagram",
}


def is_strict(path: Path) -> bool:
    with zipfile.ZipFile(path) as z:
        try:
            rels = z.read("_rels/.rels").decode("utf-8", "ignore")
        except KeyError:
            return False
    return "purl.oclc.org/ooxml" in rels


def convert(src: Path, dst: Path) -> bool:
    """返回是否真的做了转换。"""
    src, dst = Path(src), Path(dst)
    if not is_strict(src):
        if src != dst:
            shutil.copyfile(src, dst)
        return False
    tmp = dst.with_suffix(".tmp.zip")
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith((".xml", ".rels")):
                txt = data.decode("utf-8", "ignore")
                for k, v in MAP.items():
                    txt = txt.replace(k, v)
                txt = re.sub(r"http://purl\.oclc\.org/ooxml/([A-Za-z]+)/([A-Za-z]+)",
                             r"http://schemas.openxmlformats.org/\1/2006/\2", txt)
                data = txt.encode("utf-8")
            zout.writestr(item, data)
    tmp.replace(dst)
    return True
