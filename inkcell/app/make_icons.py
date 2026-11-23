# -*- coding: utf-8 -*-
"""inkcell.app.make_icons —— 给 APK 画启动图标（"写"字）。

    python -m inkcell.app.make_icons
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}


def _icon_png(size: int) -> bytes:
    import io
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (size, size), (34, 37, 42))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([8, 8, size - 8, size - 8], radius=max(8, size // 7),
                        fill=(253, 253, 251))
    font = None
    for cand in ("/mnt/c/Windows/Fonts/simsun.ttc", "/mnt/c/Windows/Fonts/msyh.ttc",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(cand, int(size * 0.62))
            break
        except Exception:
            continue
    try:
        d.text((size / 2, size / 2), "写", font=font, fill=(20, 21, 26), anchor="mm")
    except Exception:
        d.line([(size * 0.3, size * 0.5), (size * 0.7, size * 0.5)],
               fill=(20, 21, 26), width=max(3, size // 20))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def main() -> int:
    n = 0
    for dpi, px in SIZES.items():
        out = HERE / "src" / "res" / f"mipmap-{dpi}" / "ic_launcher.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(_icon_png(px))
        n += 1
    print(f"图标 {n} 个已生成（{HERE / 'src' / 'res'}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
