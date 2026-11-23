# -*- coding: utf-8 -*-
"""hw.typo —— 中文排版：行内标记清理、断行、标点禁则与悬挂。

手写的断行和 Word 不一样：行尾不齐、标点可以挂在右边距外面、
括号不能落在行尾。这里的规则就是照真人习惯写的。
"""
from __future__ import annotations

import re
import unicodedata

# 行首禁则：这些字符不能出现在一行的开头
NO_START = set("。，、；：？！）〕｝】》」』〉”’·…—～,.!?;:)]}％‰℃′″")
# 行尾禁则：这些字符不能留在行末（要拉下来和后面的字同排）
NO_END = set("（〔｛【《「『〈“‘([{")

_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)\s]+\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)\s]+\)")
_MATH_RE = re.compile(r"\$([^$\n]+)\$")


def clean_inline(text: str) -> str:
    """去掉 Markdown 行内标记，留下要"手写"的纯文本。"""
    t = text
    t = _IMG_RE.sub("", t)
    t = _LINK_RE.sub(r"\1", t)
    t = _MATH_RE.sub(r"\1", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"\*\*([^*]*)\*\*", r"\1", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", t)
    t = re.sub(r"~~([^~]+)~~", r"\1", t)
    t = t.replace("**", "").replace("`", "")
    # 字体里没有的字符（emoji 等）直接丢掉，别印成方框
    t = "".join(c for c in t if unicodedata.category(c) not in {"So", "Cs"})
    return t.strip()


class Atom:
    __slots__ = ("text", "w", "kind")

    def __init__(self, text: str, w: float, kind: str):
        self.text, self.w, self.kind = text, w, kind

    def __repr__(self) -> str:                              # pragma: no cover
        return f"<{self.kind}:{self.text!r}>"


def _is_wide(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in {"W", "F"}


_LATIN_RUN = re.compile(r"[A-Za-z0-9_@#$&*+\-=/\\<>|~^.,:;'\"()\[\]{}%°′″]+")


def atoms(text: str, adv) -> list[Atom]:
    """把一段文本切成排版原子。adv(s) -> 宽度。"""
    out: list[Atom] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == " ":
            j = i
            while j < n and text[j] == " ":
                j += 1
            out.append(Atom(" " * (j - i), adv(" " * (j - i)), "space"))
            i = j
            continue
        if _is_wide(ch):
            kind = "punct" if unicodedata.category(ch).startswith("P") else "cjk"
            out.append(Atom(ch, adv(ch), kind))
            i += 1
            continue
        m = _LATIN_RUN.match(text, i)
        if m:                                              # 拉丁/数字整串不拆
            s = m.group(0)
            out.append(Atom(s, adv(s), "latin"))
            i = m.end()
            continue
        out.append(Atom(ch, adv(ch), "punct"))
        i += 1
    return out


def break_lines(atom_list: list[Atom], width: float, first_indent: float = 0.0,
                allow_hang: bool = True) -> list[list[Atom]]:
    """按宽度断行，套用行首/行尾禁则与标点悬挂。"""
    lines: list[list[Atom]] = []
    cur: list[Atom] = []
    cur_w = first_indent

    def close_line() -> None:
        nonlocal cur, cur_w
        # 行尾禁则：把结尾的"开引号/开括号"推到下一行
        trailing: list[Atom] = []
        while len(cur) > 1 and cur[-1].kind == "punct" and cur[-1].text in NO_END:
            trailing.insert(0, cur.pop())
        lines.append(cur)
        cur = trailing
        cur_w = sum(a.w for a in cur)

    for a in atom_list:
        if cur and cur_w + a.w > width:
            # 行首禁则 + 悬挂：标点允许探出右边距一点点
            if allow_hang and a.kind == "punct" and a.text in NO_START:
                cur.append(a)
                cur_w += a.w
                close_line()
                continue
            close_line()
        cur.append(a)
        cur_w += a.w
    if cur:
        lines.append(cur)
    return lines
