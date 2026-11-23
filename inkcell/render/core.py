# -*- coding: utf-8 -*-
"""hw.core —— 手写渲染核心：字体、字形（含逐笔扰动）、纸面与墨色。

设计要点（对应调查研究里的三条结论）：
1. 同一个字不能每次长得一样 → 每个字预生成 N 个"写法"(variant)，
   由 (字符, variant) 派生随机种子，可复现。
2. 笔画要能"抖" → 把字形二值图做连通域分解，每一笔独立旋转+平移。
3. 拉丁/数字走同一个手写字体，但按半角字宽排版（霞鹜文楷那种全角的不能用）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage

# ---------------------------------------------------------------- 纸张 / 墨


@dataclass
class Ink:
    """墨色与"笔压"。打印出来是深灰而不是纯黑，更像中性笔。"""

    rgb: tuple[int, int, int] = (26, 27, 31)
    alpha: float = 0.92          # 整体浓度
    alpha_sigma: float = 0.05    # 每个字之间的浓度抖动
    pressure: float = 0.0        # >0 时整体描粗（px），模拟重笔
    bold: int = 1                # 全局加粗档数（0/1/2）：每档加粗约 2px


class Paper:
    """A4 @ 300 DPI 的纸面。默认纯白（要在白纸上打印，别浪费墨）。"""

    def __init__(self, dpi: int = 300, size_mm: tuple[float, float] = (210.0, 297.0),
                 base: int = 255, grain: int = 0, ruling_mm: float | None = None,
                 speckles: int = 0):
        self.dpi = dpi
        self.size = (int(size_mm[0] / 25.4 * dpi), int(size_mm[1] / 25.4 * dpi))
        self.base = base
        self.grain = grain
        self.ruling_mm = ruling_mm
        self.speckles = speckles

    def new(self, rng: np.random.Generator) -> Image.Image:
        w, h = self.size
        if self.ruling_mm is None and not self.grain and not self.speckles:
            return Image.new("RGB", (w, h), (self.base,) * 3)

        arr = np.full((h, w), self.base, dtype=np.int16)
        if self.ruling_mm:                                  # 横线本
            step = int(self.ruling_mm / 25.4 * self.dpi)
            for y in range(step, h - step // 2, step):
                arr[y:y + 2, :] = self.base - 24
        if self.grain:                                       # 纸面颗粒
            noise = rng.integers(-self.grain, self.grain + 1, (h, w))
            arr = np.clip(arr + noise, 150, 255)
        if self.speckles:                                    # 复印/扫描的脏点
            ys = rng.integers(0, h, self.speckles)
            xs = rng.integers(0, w, self.speckles)
            vals = rng.integers(190, 244, self.speckles)
            arr[ys, xs] = vals
        return Image.fromarray(arr.astype(np.uint8), "L").convert("RGB")


# ---------------------------------------------------------------- 字体


@dataclass
class Hand:
    """一只手（一个人）。一个 info 里可以放多个字体文件当"同一人的不同写法"。"""

    name: str
    fonts: list[Path]
    variants: int = 4            # 每个字预生成几种写法
    # 排版时的单字扰动（相对字号的倍数）
    size_sigma: float = 0.014    # 字号
    dx_sigma: float = 0.028      # 水平位置
    dy_sigma: float = 0.038      # 基线漂移
    rot_sigma: float = 0.026      # 整字旋转（弧度，约 1.5°）
    # 同一个字的不同"写法"之间的差异（这才是像不像的关键）
    var_scale: float = 0.042     # 横向/纵向各自 ±4%
    var_shear: float = 0.045     # 倾斜 ±4.5%
    var_rot: float = 0.040       # 整字旋转 ±2.3°
    # 单笔扰动（相对字号）
    stroke_dx: float = 0.024
    stroke_dy: float = 0.024
    stroke_rot: float = 0.030

    def __post_init__(self) -> None:
        self.fonts = [Path(p) for p in self.fonts]
        for p in self.fonts:
            if not p.exists():
                raise FileNotFoundError(p)

    _font_cache: dict = field(default_factory=dict, repr=False)

    def _font(self, idx: int, size: int) -> ImageFont.FreeTypeFont:
        key = (idx, size)
        f = self._font_cache.get(key)
        if f is None:
            f = ImageFont.truetype(str(self.fonts[idx]), size)
            self._font_cache[key] = f
        return f


# ---------------------------------------------------------------- 字形


@dataclass
class Glyph:
    """一个字（一种写法）的位图与度量。坐标为「基线左端」原点。"""

    img: Image.Image             # L 模式，255 = 墨
    dx: int                      # 贴到页面时，图形左上角相对基线左端的 x
    dy: int                      # 相对基线的 y（负数=在基线上方）
    advance: float               # 前进宽度（含字距的基准）


def _split_strokes(mask: Image.Image) -> list[tuple[int, int, Image.Image]]:
    """连通域分解：返回 [(x0, y0, 该笔画的子图)]。"""
    arr = np.asarray(mask, dtype=np.uint8)
    if not arr.any():
        return []
    labels, n = ndimage.label(arr > 40, structure=np.ones((3, 3), dtype=int))
    out: list[tuple[int, int, Image.Image]] = []
    for sl in ndimage.find_objects(labels):
        if sl is None:
            continue
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        sub = arr[y0:y1, x0:x1]
        sub = np.where(labels[y0:y1, x0:x1] > 0, sub, 0).astype(np.uint8)
        out.append((x0, y0, Image.fromarray(sub, "L")))
    return out


def _affine(img: Image.Image, M: np.ndarray, track: tuple[float, float]
            ) -> tuple[Image.Image, tuple[float, float]]:
    """绕图像中心做线性变换（可含缩放/错切/旋转），画布自动扩展。

    返回 (新图, track 点在变换后的坐标)。基线对齐靠它保证精确。
    """
    w, h = img.size
    c = np.array([w / 2.0, h / 2.0])
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], dtype=float) - c
    t = corners @ M.T
    mn, mx = t.min(0), t.max(0)
    W = int(np.ceil(mx[0] - mn[0])) + 4
    H = int(np.ceil(mx[1] - mn[1])) + 4
    shift = np.array([W / 2.0, H / 2.0]) - (mn + mx) / 2.0
    Minv = np.linalg.inv(M)
    off = c - Minv @ shift
    coeffs = (Minv[0, 0], Minv[0, 1], off[0], Minv[1, 0], Minv[1, 1], off[1])
    out = img.transform((W, H), Image.AFFINE, coeffs, resample=Image.BILINEAR)
    p = np.asarray(track, dtype=float) - c
    q = M @ p + shift                       # 与 AFFINE 逆映射严格互逆
    return out, (float(q[0]), float(q[1]))


def _make_one(font: ImageFont.FreeTypeFont, size: int, hand: Hand,
              rng: np.random.Generator) -> Glyph:
    """手写体的 "1" 就是一根竖线（没有头上那个撇），字体里没有就自己画。"""
    adv = float(font.getlength("1"))
    cap = 0.70 * size                       # 数字高度
    pad = max(6, size // 5)
    w = int(max(adv, size * 0.40)) + 2 * pad
    h = int(cap) + 2 * pad
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    xs = w / 2 + float(rng.normal(0, size * 0.02))
    slant = float(rng.normal(0, size * 0.035))       # 允许略微右倾
    wid = max(2, int(size * 0.060))
    top_y, bot_y = pad * 0.9, h - pad * 0.9
    # 分成几段画，带一点点弯，不要像尺子画的
    pts = []
    for t in (0.0, 0.35, 0.7, 1.0):
        pts.append((xs + slant * t + float(rng.normal(0, size * 0.006)),
                    top_y + (bot_y - top_y) * t))
    d.line(pts, fill=255, width=wid, joint="curve")
    ox = xs - adv / 2.0                              # 笔尖原点（前进量为 adv 的起点）
    oy = bot_y
    return Glyph(img=img, dx=-ox, dy=-oy, advance=adv)


def _make_glyph(font: ImageFont.FreeTypeFont, ch: str, hand: Hand,
                rng: np.random.Generator) -> Glyph:
    """渲染一个字：逐笔扰动 + 每个写法自己的缩放/倾斜/旋转，并精确定位基线。"""
    size = font.size
    if ch == "1":
        return _make_one(font, size, hand, rng)
    try:
        adv = font.getlength(ch)
        bbox = font.getbbox(ch)
    except Exception:                                    # 字体里没有这个字
        adv, bbox = size, (0, 0, size, size)
    ascent, _descent = font.getmetrics()
    pad = max(8, size // 5)
    cw = max(1, bbox[2] - bbox[0]) + 2 * pad
    chh = max(1, bbox[3] - bbox[1]) + 2 * pad

    canvas = Image.new("L", (cw, chh), 0)
    ox, oy = pad - bbox[0], pad - bbox[1]                  # 文本原点的落笔处
    ImageDraw.Draw(canvas).text((ox, oy), ch, font=font, fill=255)
    baseline = (float(ox), float(oy + ascent))             # 基线在 tile 中的坐标

    # 逐笔扰动：每一笔绕自身中心转一点、平移一点
    strokes = _split_strokes(canvas)
    if len(strokes) > 1:
        sdx = hand.stroke_dx * size
        sdy = hand.stroke_dy * size
        merged = Image.new("L", (cw, chh), 0)
        for x0, y0, sub in strokes:
            ang = rng.normal(0.0, hand.stroke_rot) * 180.0 / math.pi
            rot = sub.rotate(ang, resample=Image.BILINEAR, expand=True,
                             center=(sub.width / 2, sub.height / 2))
            rdx = int(round(rng.normal(0.0, sdx)))
            rdy = int(round(rng.normal(0.0, sdy)))
            px = x0 - (rot.width - sub.width) // 2 + rdx
            py = y0 - (rot.height - sub.height) // 2 + rdy
            tmp = Image.new("L", (cw, chh), 0)
            tmp.paste(rot, (px, py))
            merged = ImageChops.lighter(merged, tmp)
        canvas = merged

    # 这个"写法"自己的骨架：横向/纵向缩放 + 错切 + 旋转
    sx = 1.0 + float(rng.normal(0, hand.var_scale))
    sy = 1.0 + float(rng.normal(0, hand.var_scale))
    sh = float(rng.normal(0, hand.var_shear))
    ang = float(rng.normal(0, hand.var_rot))
    M = np.array([[sx, sh], [0.0, sy]]) @ np.array(
        [[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
    canvas, base = _affine(canvas, M, baseline)
    return Glyph(img=canvas, dx=-base[0], dy=-base[1], advance=adv)


class GlyphBook:
    """字形缓存：按 (字符, 写法编号) 缓存，并记住哪些字在哪几个字体里。"""

    def __init__(self, hand: Hand, seed: int = 0):
        self.hand = hand
        self.seed = seed
        self._cache: dict[tuple[str, int, int], Glyph] = {}
        self._cov: dict[int, frozenset[str]] = {}

    def _usable_font_idx(self, ch: str) -> int:
        """中文/数字用第 1 个字体（数字的 1 是竖线，没有头上的撇）；
        其余 ASCII 反过来用最后一个（字母字形更规整）。"""
        order = range(len(self.hand.fonts))
        if ord(ch) < 128 and not ch.isdigit() and len(self.hand.fonts) > 1:
            order = reversed(order)
        for i in order:
            if ch in self._covered(i):
                return i
        return 0

    def _covered(self, idx: int) -> frozenset[str]:
        hit = self._cov.get(idx)
        if hit is not None:
            return hit
        from fontTools.ttLib import TTFont
        t = TTFont(str(self.hand.fonts[idx]), lazy=True)
        cmap: set[int] = set()
        for tb in t["cmap"].tables:
            cmap |= set(tb.cmap.keys())
        t.close()
        cov = frozenset(chr(c) for c in cmap)
        self._cov[idx] = cov
        return cov

    def get(self, ch: str, size: int, variant: int) -> Glyph:
        key = (ch, size, variant)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        fi = self._usable_font_idx(ch)
        rng = np.random.default_rng(
            abs(hash((ch, variant, size, self.seed))) % (2 ** 63))
        g = _make_glyph(self.hand._font(fi, size), ch, self.hand, rng)
        self._cache[key] = g
        return g

    def variant_picker(self, rng: np.random.Generator):
        """给每个字挑写法：同一个字在同一段里尽量不连续重复。"""
        last: dict[str, int] = {}

        def pick(ch: str) -> int:
            n = self.hand.variants
            if n <= 1:
                return 0
            prev = last.get(ch)
            v = int(rng.integers(0, n))
            if v == prev:
                v = (v + 1 + int(rng.integers(0, n - 1))) % n
            last[ch] = v
            return v

        return pick

    def cache_info(self) -> str:
        return f"glyphs={len(self._cache)}"


def ink_tile(glyph: Glyph, ink: Ink, alpha: float) -> Image.Image:
    """把字形位图按墨色染成可直接 paste 的小图。"""
    a = max(0.0, min(1.0, alpha))
    mask = glyph.img
    for _ in range(int(ink.bold) + (1 if ink.pressure > 0 else 0)):
        mask = mask.filter(ImageFilter.MaxFilter(3))       # 加粗一档 ≈ 两边各 1px
    solid = Image.new("RGB", mask.size, ink.rgb)
    return solid, mask.point(lambda v: int(v * a))
