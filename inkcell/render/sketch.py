# -*- coding: utf-8 -*-
"""hw.sketch —— 把"印刷体"的东西弄成手绘：弹性扭曲的插图、手画的表格线。

插图：整张图在低频随机位移场上重采样，直线自然变弯（笔走得不直），
      高频分量再叠一点，模拟笔尖抖动。
表格线：分段 + 法向抖动 + 两端出格，且每一笔都重画两次（真人会描）。
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


def _field(shape: tuple[int, int], rng: np.random.Generator,
           sigma_lo: float, amp_lo: float,
           sigma_hi: float = 0.0, amp_hi: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    h, w = shape
    d = np.zeros((2, h, w), dtype=np.float32)
    n1 = rng.normal(0, 1, (h, w)).astype(np.float32)
    for ch in range(2):
        f = ndimage.gaussian_filter(n1, sigma_lo, mode="wrap")
        f = f / (np.abs(f).max() + 1e-6) * amp_lo
        if amp_hi > 0:
            g = ndimage.gaussian_filter(rng.normal(0, 1, (h, w)).astype(np.float32),
                                        sigma_hi, mode="wrap")
            g = g / (np.abs(g).max() + 1e-6) * amp_hi
            f = f + g
        d[ch] = f
    return d[0], d[1]


def warp(arr: np.ndarray, rng: np.random.Generator,
         amp_lo: float = 2.2, sigma_lo: float = 34.0,
         amp_hi: float = 0.5, sigma_hi: float = 2.2) -> np.ndarray:
    """对一个 (h,w) 或 (h,w,c) 数组做弹性扭曲。"""
    h, w = arr.shape[:2]
    dy, dx = _field((h, w), rng, sigma_lo, amp_lo, sigma_hi, amp_hi)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    coords = [np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)]
    if arr.ndim == 2:
        return ndimage.map_coordinates(arr, coords, order=1, mode="nearest")
    out = np.empty_like(arr)
    for c in range(arr.shape[2]):
        out[..., c] = ndimage.map_coordinates(arr[..., c], coords, order=1, mode="nearest")
    return out


def handify(img: Image.Image, rng: np.random.Generator,
            ink: tuple[int, int, int] = (26, 27, 31),
            max_w: int = 2100, rotate_deg: float | None = None,
            gentle: bool = False) -> Image.Image:
    """插图手绘化：先放大到印刷尺寸，再扭曲 + 整体微微歪，最后把线染成墨色。"""
    img = img.convert("L")
    if img.width < max_w:
        s = max_w / img.width
        img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
    arr = np.asarray(img, dtype=np.float32)
    # 白底 -> 纸，黑线 -> 墨（保留原图的灰度层次，像铅笔/钢笔画的）
    darkness = np.clip((255.0 - arr) / 255.0, 0, 1)
    if gentle:            # 图本身已经是手绘笔触了，只再"抖"一点点
        amp = float(rng.uniform(0.5, 1.3))
    else:
        amp = max(2.6, min(6.0, max_w / 420)) * float(rng.uniform(0.85, 1.2))
    warped = warp(darkness, rng, amp_lo=amp, sigma_lo=max_w / 26.0,
                  amp_hi=amp * 0.30, sigma_hi=2.4)
    warped = np.clip(warped, 0, 1)
    out = np.empty(warped.shape + (3,), dtype=np.float32)
    for c in range(3):
        out[..., c] = 255.0 - warped * (255.0 - ink[c]) * 0.95
    pic = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")
    ang = rotate_deg if rotate_deg is not None else float(rng.normal(0, 0.10 if gentle else 0.18))
    if abs(ang) > 0.02:                                  # 贴图也贴不正
        pic = pic.rotate(ang, resample=Image.BILINEAR, expand=True, fillcolor=(255, 255, 255))
    return pic


def pen_line(draw: ImageDraw.ImageDraw, p0: tuple[float, float], p1: tuple[float, float],
             rng: np.random.Generator, color, width: int = 3,
             seg: float = 26.0, wobble: float = 1.5, overshoot: float = 2.5,
             double: bool = True) -> None:
    """手画一条直线：分段抖动 + 两端出格 + 描第二遍。"""
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    length = max(1e-6, (dx * dx + dy * dy) ** 0.5)
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux                                     # 法向
    o0 = rng.normal(0, overshoot)                        # 两端的出格量
    o1 = rng.normal(0, overshoot)
    steps = max(2, int(length / seg) + 1)
    for _pass in range(2 if double else 1):
        off = 0.0 if not _pass else rng.normal(0, 0.8)
        w = width if not _pass else max(1, width - 1)
        pts: list[tuple[float, float]] = []
        for i in range(steps + 1):
            t = i / steps
            # 两端各延长一点（出格），中段轻微弯曲
            ts = -o0 / length + t * (1 + (o0 + o1) / length)
            bend = np.sin(t * np.pi) * rng.normal(0, wobble * 0.5) if 0 < i < steps else 0
            j = rng.normal(0, wobble * 0.35) + bend + off
            pts.append((x0 + ux * ts * length + nx * j, y0 + uy * ts * length + ny * j))
        draw.line(pts, fill=color, width=w, joint="curve")
