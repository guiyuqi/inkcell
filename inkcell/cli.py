# -*- coding: utf-8 -*-
"""inkcell.cli —— 一条命令一个子命令：

    inkcell sheets     生成格子字表（manifest）
    inkcell desk       起"写字台"（浏览器写）/ --offline-out 出离线页面
    inkcell import     原始字迹 png → 字形库
    inkcell glyphs     原始矢量笔迹（含压力）→ 重渲字形库（可调粗细/压感）
    inkcell sample     用字库拼一段样张
    inkcell fill       把字迹填进既有 docx（版面不动）
    inkcell verify     交付前自检（版面/图变形/裁边/条目完整性）
    inkcell app        打包手机离线 APK
"""
from __future__ import annotations

import sys
from importlib import import_module

from . import __version__

COMMANDS = {
    "sheets": ("inkcell.collect.sheets", "生成格子字表"),
    "desk": ("inkcell.collect.desk", "写字台（本地服务 / 离线页面）"),
    "import": ("inkcell.glyph.import_png", "原始 png → 字形库"),
    "glyphs": ("inkcell.glyph.from_strokes", "矢量笔迹 → 字形库"),
    "sample": ("inkcell.sample", "拼样张"),
    "fill": ("inkcell.doc.filler", "填充 docx"),
    "verify": ("inkcell.doc.verify", "自检"),
    "app": ("inkcell.app.build", "打包 APK"),
}


def _usage() -> str:
    lines = ["用法：inkcell <命令> [参数...]", "", "命令："]
    for name, (_, desc) in COMMANDS.items():
        lines.append(f"  {name:<8} {desc}")
    lines += ["", "例：", "  inkcell sheets --project . --charset gb2312 --passes 4 --order char-major",
              "  inkcell desk --project . --tag gb2312 --all-passes",
              "  inkcell fill --project . --docx src_docx/tpl.docx"]
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_usage())
        return 0
    if argv[0] in ("-V", "--version", "version"):
        print(f"inkcell {__version__}")
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd not in COMMANDS:
        print(f"未知命令：{cmd}\n\n{_usage()}", file=sys.stderr)
        return 2
    mod = import_module(COMMANDS[cmd][0])
    sys.argv = [f"inkcell {cmd}"] + rest
    return int(mod.main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
