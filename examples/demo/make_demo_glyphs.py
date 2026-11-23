# -*- coding: utf-8 -*-
"""造一套"假字库"，让 demo 不需要你的手迹、也不需要外部字体就能跑通。

用的是 Pillow 自带的矢量默认字体（load_default(size)），把 fill_data 里用到的
每个字画成 glyphs/ 里的 png + index.json —— 格式和真迹字库完全一样，
所以后面 inkcell fill 走的是**同一条代码路径**。
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from inkcell.paths import find_cjk_font

HERE = Path(__file__).resolve().parent
EM = 256


def chars_of(fill_data: Path) -> list[str]:
    s = json.load(open(fill_data, encoding="utf-8"))
    out: list[str] = []

    def walk(o):
        if isinstance(o, str):
            out.extend(c for c in o if c.strip())
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(s)
    seen, keep = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            keep.append(c)
    return keep


def main() -> int:
    gdir = HERE / "glyphs"
    gdir.mkdir(parents=True, exist_ok=True)
    cjk = find_cjk_font()
    if cjk:
        print(f"  用字体：{cjk}")
        font = ImageFont.truetype(str(cjk), int(EM * 0.86))
    else:
        print("  !! 没找到中文字体，中文会渲染成方块；把 .ttf 放进 assets/fonts/ 或设 INKCELL_FONTS")
        try:
            font = ImageFont.load_default(size=EM * 0.86)
        except TypeError:                   # Pillow < 10.1
            print("!! 需要 Pillow >= 10.1（load_default(size=...)）")
            return 2

    index = {"em": EM, "count": 0, "glyphs": {}}
    for ch in chars_of(HERE / "data" / "fill_data.json"):
        canvas = Image.new("L", (int(EM * 1.3), int(EM * 1.35)), 0)
        d = ImageDraw.Draw(canvas)
        d.text((canvas.width / 2, canvas.height * 0.78), ch, font=font,
               fill=255, anchor="ms")
        fn = f"{ord(ch):05x}_v1.png"
        canvas.save(gdir / fn)
        adv = EM if ord(ch) > 0x2E80 else int(EM * 0.62)
        index["glyphs"][f"{ord(ch):05x}"] = {
            "char": ch,
            "variants": [{"file": fn, "w": canvas.width, "h": canvas.height,
                          "dx": -((canvas.width - adv) // 2),
                          "dy": -(int(canvas.height * 0.80)),
                          "adv": adv, "src": "demo", "pass": 1}],
        }
    index["count"] = len(index["glyphs"])
    (gdir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    print(f"✔ 假字库 {index['count']} 字 → {gdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
