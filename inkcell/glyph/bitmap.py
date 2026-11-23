# -*- coding: utf-8 -*-
"""handwrite/bitmap.py —— 位图字迹库：把"自己写的字"接进渲染管线。

渲染管线本来就是 PIL 位图（GlyphBook 返回 mask），所以不需要 TTF：
glyphs/index.json 里每个字有若干写法，每写法一张灰度图 + dx/dy/adv，
这里按目标字号缩放、按 variant 挑选，缺字自动回落到字体（Hand）。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image

from inkcell.render.core import Glyph, GlyphBook, Hand


class BitmapGlyphs:
    def __init__(self, glyph_dir: Path):
        self.dir = Path(glyph_dir)
        idx = json.load(open(self.dir / "index.json", encoding="utf-8"))
        self.em = int(idx.get("em", 256))
        self.table: dict[str, list[dict]] = {}
        for hexcode, ent in idx["glyphs"].items():
            self.table[ent["char"]] = ent["variants"]
        self._cache: dict[tuple[str, int, int], Glyph] = {}

    def has(self, ch: str) -> bool:
        return ch in self.table

    @property
    def chars(self) -> set[str]:
        return set(self.table)

    def variants(self, ch: str) -> int:
        return len(self.table.get(ch, []))

    def get(self, ch: str, size: int, variant: int) -> Glyph | None:
        vs = self.table.get(ch)
        if not vs:
            return None
        key = (ch, size, variant % len(vs))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        v = vs[key[2]]
        img = Image.open(self.dir / v["file"]).convert("L")
        k = size / self.em
        w, h = max(1, int(img.width * k)), max(1, int(img.height * k))
        img = img.resize((w, h), Image.LANCZOS)
        g = Glyph(img=img, dx=int(v["dx"] * k), dy=int(v["dy"] * k),
                  advance=float(v["adv"]) * k)
        self._cache[key] = g
        return g


class HybridBook(GlyphBook):
    """优先用自己的字迹，没有的字回落到字体。"""

    def __init__(self, hand: Hand, seed: int = 0, bitmap: BitmapGlyphs | None = None):
        super().__init__(hand, seed=seed)
        self.bitmap = bitmap

    def get(self, ch: str, size: int, variant: int) -> Glyph:
        if self.bitmap is not None and self.bitmap.has(ch):
            g = self.bitmap.get(ch, size, variant)
            if g is not None:
                return g
        return super().get(ch, size, variant)

    def cache_info(self) -> str:
        return f"glyphs={len(self._cache)}" + (
            f" / 手迹 {len(self.bitmap.chars)} 字" if self.bitmap else "")
