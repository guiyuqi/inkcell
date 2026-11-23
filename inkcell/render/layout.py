# -*- coding: utf-8 -*-
"""hw.layout —— 排版与书写：把 Markdown 块流"写"到 A4 纸面上。

一个 Writer = 一支笔 + 一叠纸。它负责：
  * 行距/段距/首行缩进、行首禁则、标点悬挂
  * 每个字的写法、位置、浓度抖动（并随页号逐渐"写飘"）
  * 手画表格、手绘插图、图注、页码
"""
from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .core import GlyphBook, Hand, Ink, Paper, ink_tile
from .sketch import handify, pen_line
from .typo import Atom, atoms as make_atoms, break_lines, clean_inline


@dataclass
class Style:
    body: int = 56                  # 正文字号 px @300dpi ≈ 4.7 mm
    pitch: float = 1.66             # 行距 = body * pitch
    margin_l: int = 235
    margin_r: int = 205
    margin_t: int = 205
    margin_b: int = 215
    indent_chars: float = 2.0       # 首行缩进
    para_gap: float = 0.34          # 段间距（行距的倍数）
    table_scale: float = 0.60       # 表内字号 / 正文
    caption_scale: float = 0.70     # 图注字号 / 正文
    # 印刷体（模板条目）——按五号 10.5pt、2 倍行距，和学校那份 .doc 一致
    print_font: str = ""
    print_index: int = 0
    print_pt: float = 10.5
    print_pitch_pt: float = 21.6    # 一条印刷行的行距（留白也按它算）


@dataclass
class Writer:
    hand: Hand
    paper: Paper
    style: Style = field(default_factory=Style)
    ink: Ink = field(default_factory=Ink)
    seed: int = 0
    keep_with_next: int = 2         # 标题不能落单，至少带几行正文

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        self.book = GlyphBook(self.hand, seed=self.seed)
        self.pick_variant = self.book.variant_picker(np.random.default_rng(self.seed + 7))
        self.pages: list[Image.Image] = []
        self.page_no = 0
        self.y = 0.0
        self.print_font = None
        if self.style.print_font:
            self.print_font = ImageFont.truetype(
                self.style.print_font,
                int(self.style.print_pt / 72.0 * self.paper.dpi),
                index=self.style.print_index)
        self._new_page()

    # ------------------------------------------------------------ 纸面
    @property
    def pw(self) -> int:
        return self.paper.size[0]

    @property
    def ph(self) -> int:
        return self.paper.size[1]

    @property
    def text_w(self) -> float:
        return self.pw - self.style.margin_l - self.style.margin_r

    def _new_page(self) -> None:
        self.page_no += 1
        self.canvas = self.paper.new(self.rng)
        self.draw = ImageDraw.Draw(self.canvas)
        self.y = float(self.style.margin_t) + self.style.body
        self.pages.append(self.canvas)
        self.fresh = True                     # 这一页还没写过东西
        # 越写到后面越"飘"：手会累、墨会变淡
        t = min(1.0, max(0.0, (self.page_no - 1) / 22.0))
        self.slack = 0.86 + 0.42 * t + float(self.rng.normal(0, 0.05))
        self.ink_alpha = self.ink.alpha * (1.0 - 0.05 * t)
        self._drift = 0.0

    def ensure(self, n_lines: float = 1.0) -> None:
        """剩余空间不足 n 行就翻页。"""
        need = self.style.body * self.style.pitch * n_lines
        if self.y + need > self.ph - self.style.margin_b:
            self._new_page()

    # ------------------------------------------------------------ 印刷体（模板条目）
    @property
    def print_pitch(self) -> float:
        return self.style.print_pitch_pt / 72.0 * self.paper.dpi

    def _pmeasure(self, text: str) -> float:
        return float(self.print_font.getlength(text))

    def print_para(self, text: str, indent_chars: float = 0.0, center: bool = False,
                   bold: bool = False, size_pt: float | None = None) -> None:
        """排一段"印刷"的模板条目文字（宋体），行距用 print_pitch。"""
        f = self.print_font
        if size_pt:
            f = ImageFont.truetype(self.style.print_font,
                                   int(size_pt / 72.0 * self.paper.dpi),
                                   index=self.style.print_index)
        text = text.strip()
        if not text:
            return
        ind = indent_chars * (f.size * 0.5)
        at = make_atoms(text, lambda s_: float(f.getlength(s_)))
        lines = break_lines(at, self.text_w - ind)
        color = (18, 18, 20)
        for i, line in enumerate(lines):
            self.ensure(1.0)
            s_ = "".join(a.text for a in line)
            w = float(f.getlength(s_))
            x = self.style.margin_l + (ind if i == 0 else 0.0)
            if center:
                x = self.style.margin_l + (self.text_w - w) / 2
            self.draw.text((x, self.y), s_, font=f, fill=color, anchor="ls")
            if bold:                      # 假粗体：错开 1px 再描一遍
                self.draw.text((x + max(1, f.size // 26), self.y), s_, font=f,
                               fill=color, anchor="ls")
            self.fresh = False
            self.y += self.print_pitch

    # ------------------------------------------------------------ 写字
    def _measure(self, size: int, text: str) -> float:
        fi = self.book._usable_font_idx(text[0]) if text else 0
        return float(self.hand._font(fi, size).getlength(text))

    def _draw_line(self, line: list[Atom], x0: float, baseline: float, size: int,
                   pressure: float = 0.0, alpha_mul: float = 1.0) -> None:
        pen = x0
        slope = float(self.rng.normal(0, 0.00055))       # 行基线微微翘
        dy_line = float(self.rng.normal(0, 0.010 * size)) * self.slack
        prev_kind = ""
        for a in line:
            if a.kind == "space":
                pen += a.w
                continue
            # 中英/数字交界处自然留一点空隙（真人不会贴着写）
            if prev_kind and prev_kind != a.kind and {prev_kind, a.kind} & {"latin"}:
                pen += size * float(self.rng.uniform(0.05, 0.11))
            prev_kind = a.kind
            gy = baseline + dy_line + slope * (pen - x0)
            for ch in a.text:
                if ch == " ":
                    pen += self._measure(size, " ")
                    continue
                variant = self.pick_variant(ch)
                g = self.book.get(ch, size, variant)
                dx = float(self.rng.normal(0, self.hand.dx_sigma * size)) * self.slack
                dy = float(self.rng.normal(0, self.hand.dy_sigma * size)) * self.slack
                a_i = self.ink_alpha * alpha_mul + float(self.rng.normal(0, self.ink.alpha_sigma))
                ink_now = Ink(rgb=self.ink.rgb, alpha=max(0.55, min(1.0, a_i)),
                              pressure=pressure)
                solid, mask = ink_tile(g, ink_now, ink_now.alpha)
                self.canvas.paste(solid, (int(pen + dx + g.dx), int(gy + dy + g.dy)), mask)
                self.fresh = False
                pen += g.advance

    def write_lines(self, lines: list[list[Atom]], size: int, indent: float = 0.0,
                    pressure: float = 0.0, extra_pitch: float = 0.0,
                    align: str = "left", alpha_mul: float = 1.0) -> None:
        pitch = size * self.style.pitch + extra_pitch
        for i, line in enumerate(lines):
            self.ensure(1.0)
            # 一整页写下来会慢慢"走偏"：行基线做随机游走
            self._drift = float(np.clip(self._drift + self.rng.normal(0, 1.1 * self.slack),
                                        -7.0, 7.0))
            w = sum(a.w for a in line)
            if align == "center":
                x0 = self.style.margin_l + (self.text_w - w) / 2
            elif align == "right":
                x0 = self.pw - self.style.margin_r - w
            else:
                x0 = (self.style.margin_l + (indent if i == 0 else 0.0)
                      + float(self.rng.normal(0, 3.2)))
            self._draw_line(line, x0, self.y + self._drift, size,
                            pressure=pressure, alpha_mul=alpha_mul)
            self.y += pitch

    def paragraph(self, text: str, size: int | None = None, indent: float | None = None,
                  pressure: float = 0.0, align: str = "left", alpha_mul: float = 1.0) -> None:
        size = size or self.style.body
        text = clean_inline(text)
        if not text:
            return
        ind = size * (self.style.indent_chars + float(self.rng.normal(0, 0.15))) \
            if indent is None else indent
        at = make_atoms(text, lambda s: self._measure(size, s))
        lines = break_lines(at, self.text_w, first_indent=ind)
        self.write_lines(lines, size, indent=ind, pressure=pressure,
                         align=align, alpha_mul=alpha_mul)
        self.y += size * self.style.pitch * self.style.para_gap

    # ------------------------------------------------------------ 块
    def heading(self, text: str, level: int) -> None:
        text = clean_inline(text)
        if not text:
            return
        if level == 1:
            size = int(self.style.body * 1.26)
            self.y += self.style.body * 0.55
            self.ensure(3.2)
            self.paragraph(text, size=size, indent=0.0, pressure=1.0, align="center")
            self.y += self.style.body * 0.20
        elif level == 2:
            size = int(self.style.body * 1.08)
            self.y += self.style.body * 0.42
            self.ensure(self.keep_with_next)
            self.paragraph(text, size=size, indent=0.0, pressure=1.0)
            self.y += self.style.body * 0.10
        elif level == 3:
            self.y += self.style.body * 0.18
            self.ensure(self.keep_with_next)
            self.paragraph(text, indent=0.0, pressure=0.6)
        else:
            self.ensure(self.keep_with_next)
            self.paragraph(text, indent=self.style.body * 1.0, pressure=0.5)

    def bullets(self, items: list[tuple[str, str]]) -> None:
        """items = [(marker, text)]；marker 如 '1.' 或 '·'。"""
        size = self.style.body
        for marker, text in items:
            text = clean_inline(text)
            if not text:
                continue
            ind = size * 1.6
            mw = self._measure(size, marker + " ")
            at = make_atoms(text, lambda s: self._measure(size, s))
            lines = break_lines(at, self.text_w - ind + size * self.style.indent_chars,
                                first_indent=0.0)
            self.ensure(1.0)
            self._draw_line(make_atoms(marker, lambda s: self._measure(size, s)),
                            self.style.margin_l + size * 0.7, self.y, size)
            self.write_lines(lines, size, indent=ind, extra_pitch=0.0)
            self.y += size * self.style.pitch * 0.12
            del mw
        self.y += size * self.style.pitch * self.style.para_gap

    def quote(self, text: str) -> None:
        size = int(self.style.body * 0.82)
        self.paragraph(text, size=size, indent=size * 2.0, alpha_mul=0.95)

    def code_block(self, lines: list[str]) -> None:
        """公式/推导：稍小、居中偏左、行距紧一点，像"另起一块写公式"。"""
        size = int(self.style.body * 0.96)
        self.y += self.style.body * 0.18
        for raw in lines:
            t = clean_inline(raw)
            if not t:
                continue
            self.paragraph(t, size=size, indent=size * 2.0)
        self.y += self.style.body * 0.10

    def hand_table(self, rows: list[list[str]], size: int | None = None,
                   x0: float | None = None, gap: float | None = None) -> None:
        """手列的真值表/状态表：只对齐不画线（照着参考里那种写法）。"""
        if not rows:
            return
        size = size or int(self.style.body * 0.94)
        gap = size * 0.95 if gap is None else gap
        pitch = size * 1.46
        ncol = max(len(r) for r in rows)
        rows = [[clean_inline(c) for c in (r + [""] * (ncol - len(r)))] for r in rows]
        widths = [max(self._measure(size, r[j]) for r in rows) for j in range(ncol)]
        total = sum(widths) + gap * (ncol - 1)
        x = self.style.margin_l + size * 2.4 if x0 is None else x0
        if total > self.text_w - size * 2.4:            # 太宽才居中收一收
            x = self.style.margin_l + max(0.0, (self.text_w - total) / 2)
        col_x, acc = [], x
        for wd in widths:
            col_x.append(acc)
            acc += wd + gap
        self.y += size * 0.16
        for ri, row in enumerate(rows):
            self.ensure(1.0)
            for c, cell in enumerate(row):
                if not cell:
                    continue
                wl = self._measure(size, cell)
                cx = col_x[c] + (widths[c] - wl) / 2      # 列内居中
                self._draw_line(make_atoms(cell, lambda s_: self._measure(size, s_)),
                                cx, self.y, size)
            self.y += pitch
            if ri == 0:
                self.y += size * 0.10
        self.y += size * 0.10

    # ------------------------------------------------------------ 表格
    def table(self, rows: list[list[str]], header: bool = True) -> None:
        if not rows:
            return
        size = max(22, int(self.style.body * self.style.table_scale))
        pad = int(size * 0.45)
        padx = int(size * 0.62)
        pitch = size * 1.30
        ncol = max(len(r) for r in rows)
        rows = [[clean_inline(c) for c in (r + [""] * (ncol - len(r)))] for r in rows]

        # 列宽：先按内容自然宽度，超出版面再整体缩放
        avail = self.text_w
        nat = [max(self._measure(size, r[j]) for r in rows) for j in range(ncol)]
        nat = [min(max(v, size * 1.5), avail * 0.40) + 2 * pad for v in nat]
        k = avail / sum(nat)                     # 一律铺满版面宽度
        nat = [v * k for v in nat]
        col_x = [float(self.style.margin_l)]
        for w in nat:
            col_x.append(col_x[-1] + w)
        col_x[-1] = float(self.style.margin_l) + avail

        def wrap(cell: str, j: int) -> list[list[Atom]]:
            at = make_atoms(cell, lambda s: self._measure(size, s))
            return break_lines(at, nat[j] - 2 * padx) if at else [[]]

        wrapped = [[wrap(c, j) for j, c in enumerate(r)] for r in rows]
        heights = [max(len(w) for w in wr) * pitch + 2 * pad for wr in wrapped]
        color = self.ink.rgb

        import os
        if os.environ.get("HW_DEBUG_TABLE"):
            print(f"[table] size={size} pad={pad} pitch={pitch:.1f} ncol={ncol} "
                  f"nat={[round(v) for v in nat]} heights={[round(h) for h in heights]} "
                  f"top={self.y:.0f} lines={[max(len(w) for w in wr) for wr in wrapped]}",
                  flush=True)
        i = 0
        first_chunk = True
        while i < len(rows):
            if first_chunk:
                self.y += size * 0.7
            top = self.y
            bottom_lim = self.ph - self.style.margin_b
            body: list[tuple[int, float, float]] = []
            acc = 0.0
            j = i
            while j < len(rows) and top + acc + heights[j] <= bottom_lim:
                body.append((j, acc, heights[j]))
                acc += heights[j]
                j += 1
            if not body:
                # 这一页连一行都放不下 → 翻页重来；新页还放不下就硬画一行，避免死循环
                if not first_chunk:
                    self._new_page()
                    first_chunk = False
                    continue
                body = [(i, 0.0, heights[i])]
                acc, j = heights[i], i + 1
            elif len(body) < 2 and j < len(rows) and not first_chunk:
                self._new_page()                    # 别把表头孤零零留在页底
                continue
            # 单元格文字：基线与行顶对齐
            for ri, y0, hh in body:
                nline = max(len(w) for w in wrapped[ri])
                lead = (hh - nline * pitch) / 2 + size * 1.02
                for c, wlines in enumerate(wrapped[ri]):
                    colw = col_x[c + 1] - col_x[c]
                    for li, ln in enumerate(wlines):
                        lw = sum(x.w for x in ln)
                        center = lw < colw * 0.62
                        x = col_x[c] + padx + ((colw - 2 * padx - lw) / 2 if center else 0)
                        self._draw_line(ln, x, top + y0 + lead + li * pitch, size)
            # 手画表格线
            x_l, x_r = col_x[0], col_x[-1]
            pen_line(self.draw, (x_l, top), (x_r, top), self.rng, color, width=3)
            for ri, y0, hh in body:
                y = top + y0 + hh
                pen_line(self.draw, (x_l, y), (x_r, y), self.rng, color, width=3)
                if header and ri == 0:            # 表头下双线
                    pen_line(self.draw, (x_l, y + size * 0.16), (x_r, y + size * 0.16),
                             self.rng, color, width=2, double=False)
            for x in col_x:
                pen_line(self.draw, (x, top), (x, top + acc), self.rng, color, width=3)
            self.y = top + acc + self.style.body * 1.45
            i = j
            first_chunk = False
            if i < len(rows):
                self._new_page()
        self.y += self.style.body * 0.16

    # ------------------------------------------------------------ 图
    def figure(self, path: Path, caption: str, upscale: float = 1.4,
               gentle: bool = True, printed: bool = False,
               max_h: float | None = None) -> None:
        try:
            img = Image.open(path)
        except Exception:
            self.paragraph(f"（图缺失：{path.name}）")
            return
        aspect = img.height / max(1, img.width)
        usable_h = self.ph - self.style.margin_t - self.style.margin_b
        # 图是按 200 dpi 出的，按"原尺寸放大 1.4 倍"落版，别硬拉满页宽
        nat = img.width * self.paper.dpi / 200.0
        w = min(self.text_w, nat * upscale)
        cap_total = usable_h * 0.52 if max_h is None else max_h
        if w * aspect > cap_total:                 # 限高（手写版按页、模板版按篇幅）
            w = cap_total / aspect
        w = int(min(w, self.text_w))
        cap_size = int(self.style.body * self.style.caption_scale)
        cap_h = cap_size * self.style.pitch * (1.0 + self.style.para_gap)
        need = w * aspect + cap_h + self.style.body * 0.4
        bottom = self.ph - self.style.margin_b
        if self.y - self.style.body * 1.05 + need > bottom:
            # 本页还留着不少地方：把图缩小塞进去（真人也会画小一点挤一挤）
            avail = bottom - (self.y - self.style.body * 1.05)
            if avail > usable_h * 0.16:
                k = max(0.50, (avail - cap_h) / max(1.0, w * aspect))
                w = int(w * k)
                need = w * aspect + cap_h + self.style.body * 0.4
            if self.y - self.style.body * 1.05 + need > bottom:
                self._new_page()
        if printed:                                # 直接打印的印刷图，不加工
            pic = img.convert("RGB")
            if pic.width != w:
                pic = pic.resize((int(w), int(pic.height * w / pic.width)), Image.LANCZOS)
            if False:
                pic = pic.resize((w, int(pic.height * w / pic.width)), Image.LANCZOS)
        else:
            pic = handify(img, self.rng, ink=self.ink.rgb, max_w=w, gentle=gentle)
        x = int(self.style.margin_l + (self.text_w - pic.width) / 2)
        y = int(self.y - self.style.body * 1.05)
        self.canvas.paste(pic, (x, y))
        self.y = y + pic.height + cap_size * 1.35
        if caption:
            self.paragraph(caption, size=cap_size, indent=0.0, align="center",
                           alpha_mul=0.98)
        self.y += self.style.body * 0.12

    # ------------------------------------------------------------ 收尾
    def _scan_noise(self, img: Image.Image) -> Image.Image:
        """复印/扫描那一层底噪：整页轻微噪点 + 少量深一点的脏点。"""
        amt = int(getattr(self.paper, "grain", 0))
        if amt <= 0:
            return img
        arr = np.asarray(img, dtype=np.int16).copy()
        h, w = arr.shape[:2]
        noise = self.rng.normal(0, amt * 0.6, (h, w)).astype(np.int16)
        arr = np.clip(arr + noise[..., None], 0, 255)
        n = max(1, int(h * w / 9000))
        ys = self.rng.integers(0, h, n)
        xs = self.rng.integers(0, w, n)
        for y, x in zip(ys, xs):
            arr[y, x] = np.clip(arr[y, x] - int(self.rng.integers(20, 70)), 0, 255)
        return Image.fromarray(arr.astype(np.uint8), "RGB")

    def finish(self, page_numbers: bool = True) -> list[Image.Image]:
        if page_numbers:
            size = int(self.style.body * 0.56)
            for i, page in enumerate(self.pages):
                t = str(i + 1)
                w = self._measure(size, t)
                self.canvas = page
                self._draw_line(make_atoms(t, lambda s: self._measure(size, s)),
                                (self.pw - w) / 2, self.ph - self.style.margin_b * 0.5,
                                size, alpha_mul=0.9)
        self.pages = [self._scan_noise(p) for p in self.pages]
        return self.pages
