# -*- coding: utf-8 -*-
"""hw/slot.py —— 按"行"渲染手写内容：一行一张图，字绝不跨界。

为什么要按行渲染而不是切图：
  从一整张图上横着切条，刀口会落在字上（字被切成上下两半）。
  这里改成"每一行单独画一张"，字永远在自己那一条里，
  条与条之间哪怕有几十分之一毫米的缝，也只会落在空白处。

对外两个函数：
  render_figure(...) -> 整格一张图（电路图那种，不分条）
  render_bands(...)  -> 每个空行一张图（文字 / 手列真值表）
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .core import Hand, Ink, Paper
from .layout import Style, Writer
from .typo import atoms as make_atoms, break_lines, clean_inline


def _canvas(w_pt: float, h_pt: float, dpi: int, noise: int) -> tuple[Paper, int, int]:
    k = dpi / 72.0
    W, H = max(24, int(w_pt * k)), max(24, int(h_pt * k))
    paper = Paper(dpi=dpi, size_mm=(w_pt / 72.0 * 25.4, h_pt / 72.0 * 25.4),
                  grain=noise, speckles=int(noise) * 40 if noise else 0)
    return paper, W, H


def _make_writer(paper: Paper, W: int, H: int, hand: Hand, seed: int, bold: int,
                 body_px: int, book=None) -> Writer:
    style = Style(body=body_px, pitch=1.45, margin_l=max(2, int(body_px * 0.10)),
                  margin_r=int(body_px * 0.85),
                  margin_t=0, margin_b=0, indent_chars=2.0, para_gap=0.0)
    w = Writer(hand=hand, paper=paper, style=style, ink=Ink(bold=bold), seed=seed,
               keep_with_next=1)
    if book is not None:
        w.book = book                            # 真迹字库（HybridBook）
    w.ensure = lambda *a, **kw: None             # type: ignore[method-assign]
    w._new_page = lambda *a, **kw: None          # type: ignore[method-assign]
    return w


def _safe(img: Image.Image, pad: int = 4) -> Image.Image:
    """兜底：墨迹离画布边至少留 pad 像素，否则平移/微缩。

    真迹是按"它自己写的高度"摆的，偶尔会比汉字高半格，贴到画布上沿就少一截；
    行首的第一个字也可能压到左沿。与其让人去挑错，不如这里保证不出界。
    """
    a = np.asarray(img.convert("L"))
    ink = a < 128
    if not ink.any():
        return img
    ys, xs = np.where(ink)
    W, H = img.size
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    ink_w, ink_h = x1 - x0 + 1, y1 - y0 + 1
    if ink_w > W - 2 * pad or ink_h > H - 2 * pad:      # 实在放不下 → 等比缩一点
        f = min((W - 2 * pad) / ink_w, (H - 2 * pad) / ink_h)
        nw, nh = max(1, int(img.width * f)), max(1, int(img.height * f))
        small = img.resize((nw, nh), Image.LANCZOS)
        return _safe(small, pad) if (nw, nh) != (W, H) else small
    dx = pad - x0 if x0 < pad else (W - pad - 1) - x1 if x1 > W - pad - 1 else 0
    dy = pad - y0 if y0 < pad else (H - pad - 1) - y1 if y1 > H - pad - 1 else 0
    if dx == 0 and dy == 0:
        return img
    out = Image.new("RGB", (W, H), (255, 255, 255))
    out.paste(img, (dx, dy))
    return out


def _flat(w: Writer, W: int, H: int) -> Image.Image:
    page = w.pages[0].crop((0, 0, W, H))
    base = Image.new("RGB", (W, H), (255, 255, 255))
    base.paste(page, (0, 0))
    return base


def _logical_lines(fill: dict, body_px: int, hand: Hand, text_w: float, book=None,
                   stats: dict | None = None):
    """把一格内容排成"逻辑行"，每行 = ['p', 原子] 或 ['t', [(原子, x), ...]]。

    量宽度必须走**实际要画的那套字**（book），否则真迹字距和字体不同，
    断行会算错、行尾会超出或空一大截。
    """
    out: list[tuple[str, object]] = []
    if book is None:
        # 没有字库时才需要字体来量宽度；有字库就按字库的 advance 量，
        # 这样 "没有回落字体" 也能跑（只要求字库覆盖所有字）。
        font = hand._font(0, body_px)

        def meas(s: str) -> float:
            return font.getlength(s)
    else:
        def meas(s: str) -> float:
            tot = 0.0
            for ch in s:
                tot += body_px * 0.5 if ch == " " else book.get(ch, body_px, 0).advance
            return tot

    def para(text: str) -> None:
        t = clean_inline(text)
        if not t:
            return
        at = make_atoms(t, meas)
        ind = body_px * 2.0
        for n, ln in enumerate(break_lines(at, text_w, first_indent=ind)):
            out.append(("p", (ln, ind if n == 0 else 0.0)))

    for line in fill.get("lead", []):
        para(line)

    if fill.get("table"):
        rows = fill["table"]
        ncol = max(len(r) for r in rows)
        rows = [[clean_inline(c) for c in (r + [""] * (ncol - len(r)))] for r in rows]
        widths = [max(meas(r[j]) for r in rows) for j in range(ncol)]
        gap = body_px * 0.95
        total = sum(widths) + gap * (ncol - 1)
        # 列太宽就把列间距收紧，绝不让最后一列冲出画面（右边会被裁掉）
        if total > text_w and ncol > 1:
            gap = max(body_px * 0.30, (text_w - sum(widths)) / (ncol - 1))
            total = sum(widths) + gap * (ncol - 1)
        if stats is not None:
            stats["tbl_w"] = max(stats.get("tbl_w", 0.0), total)
        x0 = (text_w - total) / 2 if total < text_w * 0.92 else 0.0
        colx, acc = [], x0
        for wd in widths:
            colx.append(acc)
            acc += wd + gap
        out.append(("blank", None))
        for row in rows:
            cells = []
            for c, cell in enumerate(row):
                if not cell:
                    continue
                lw = meas(cell)
                cells.append((make_atoms(cell, meas),
                              colx[c] + (widths[c] - lw) / 2))
            out.append(("t", cells))

    for line in fill.get("text", []):
        para(line)
    return out


def render_bands(fill: dict, w_pt: float, band_pts: list[float],
                 hand: Hand, seed: int = 0, dpi: int = 300, bold: int = 1,
                 noise: int = 4, body_pt: float = 11.0, book=None
                 ) -> list[tuple[int, int, Image.Image]]:
    """每个空行一张图（返回到 band_pts 等长的列表，None = 该行留白）。

    一"条"可以占多个空行（span>1），这样表格行、心得行就能写得大一点；
    仍然是一整块图钉在第一个空行上，不切图，所以不会切到字。
    """
    out: list[tuple[int, int, Image.Image]] = []
    if not fill or not band_pts:
        return out
    k = dpi / 72.0

    # 每行最多能写多大字：1.55 倍字号才能保证笔画不出界
    n_bands = len(band_pts)
    body_pt = min(body_pt, min(band_pts) / 1.55)
    body_px = max(8, int(body_pt * k))

    # 可用宽度必须扣掉 Writer 的右页边距，否则行尾会溢出画布、最后一个字被裁掉
    avail = w_pt * k - body_px * 0.85 - body_px * 0.10
    stats: dict = {}
    items = _logical_lines(fill, body_px, hand, avail, book=book, stats=stats)
    if len(items) > n_bands:                      # 先去掉表前那一空行
        items = [it for it in items if it[0] != "blank"]
    # 行数比空格子还多 / 表格比版心还宽 → 逐步缩小字号（绝不丢内容、绝不裁字）
    while (len(items) > n_bands or stats.get("tbl_w", 0) > avail) and body_pt > 7.0:
        body_pt *= 0.92
        body_px = max(7, int(body_pt * k))
        avail = w_pt * k - body_px * 0.85 - body_px * 0.10
        stats = {}
        items = _logical_lines(fill, body_px, hand, avail, book=book, stats=stats)
    if not items:
        return out
    # 内容少就每条占 2 行（写大一点），内容多就一条一行；绝不丢条目
    span = 2 if len(items) * 2 <= n_bands else 1
    if len(items) > n_bands:
        print(f"   ⚠ 缩到 {body_pt:.1f}pt 仍然 {len(items)} 行 > {n_bands} 行", flush=True)
    body_pt = min(body_pt, (min(band_pts) * span) / 1.45)
    body_px = max(8, int(body_pt * k))

    used = min(len(items), max(1, n_bands // span))
    top = max(0, (n_bands - used * span) // 2)

    for n, item in enumerate(items[:used]):
        bi = top + n * span
        if bi >= n_bands:
            break
        kind, payload = item
        if kind == "blank":
            continue
        h_pt = sum(band_pts[bi:bi + span])
        paper, W, H = _canvas(w_pt, h_pt, dpi, noise)
        w = _make_writer(paper, W, H, hand, seed + bi * 31, bold, body_px, book=book)
        base_y = min(float(H * 0.62), float(H - body_px * 0.30))
        w.y = base_y
        if kind == "p":
            atoms_line, ind = payload                            # type: ignore[misc]
            jitter = float(np.random.default_rng(seed + bi).normal(0.0, body_px * 0.10))
            w._draw_line(atoms_line, ind + jitter, base_y, body_px)
        else:
            for cell_atoms, x in payload:                        # type: ignore[misc]
                w._draw_line(cell_atoms, float(x), base_y, body_px)
        out.append((bi, span, _safe(_flat(w, W, H))))
    return out


def load_code(names: list[str], src_dir: Path) -> list[str]:
    """读 VHDL 源码，返回要贴进 Word 的行（保留缩进与注释）。"""
    out: list[str] = []
    for n in names:
        p = src_dir / n
        if not p.exists():
            continue
        out.append(f"-- ======== {n} ========")
        out.extend(p.read_text(encoding="utf-8").rstrip("\n").splitlines())
        out.append("")
    return out


def render_figure(fill: dict, w_pt: float, h_pt: float, fig_dir: Path | None,
                  dpi: int = 300) -> Image.Image | None:
    """整格一张图（电路图）：不分条，避免把线条切开。"""
    if not fill or not fill.get("figure") or not fig_dir:
        return None
    p = fig_dir / fill["figure"]
    if not p.exists():
        return None
    k = dpi / 72.0
    W, H = int(w_pt * k), int(h_pt * k)
    img = Image.open(p).convert("RGB")
    scale = min(W / img.width, (H * 0.96) / img.height)
    img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                     Image.LANCZOS)
    base = Image.new("RGB", (W, H), (255, 255, 255))
    base.paste(img, ((W - img.width) // 2, max(0, (H - img.height) // 2)))
    return base
