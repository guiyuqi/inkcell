# -*- coding: utf-8 -*-
"""TOOLS/import_handwriting.py —— 把写字台存下来的原始格图，整理成能直接用的字形库。

输入：PROJECTS/手写字体/raw/<tag>-p<N>/<id>_p<N>_<hex>.png（+ 同名 .json 带矢量笔迹）
输出：
    glyphs/<hex>_v<k>.png   每个写法一张（灰度，255=墨）
    glyphs/index.json       {char: [{file, w, h, dx, dy, adv}, ...]}
    glyphs/montage.png      联系表，一眼看质量

归一化是关键：每个人写字大小不一样，入库时按**墨迹包围盒**缩放，让同一个字在
em 方框里比例一致（汉字缩放到 0.88 em 高，且单笔画字额外限幅，避免"一"被放大成一条柱）。

    ./.venv/bin/python TOOLS/import_handwriting.py            # 整理 corpus-p1
    ./.venv/bin/python TOOLS/import_handwriting.py --demo      # 顺便用真实矢量笔迹拼一张样张
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from inkcell.paths import load_project

EM = 256                 # 字形图的 em 方框像素（够 300dpi 用：256px ≈ 大写 21.3pt）


def load_png_ink(png: Path) -> Image.Image | None:
    """读写字台存的 PNG：透明背景 + 黑色墨迹 → 灰度（255=墨）。"""
    try:
        im = Image.open(png)
    except Exception:
        return None
    im = im.convert("RGBA")
    arr = np.asarray(im)
    alpha = arr[..., 3].astype(np.float32) / 255.0
    lum = arr[..., :3].astype(np.float32).mean(axis=2)
    ink = (1.0 - lum / 255.0) * alpha          # 越黑越有墨
    ink = np.clip(ink * 255 * 1.15, 0, 255).astype(np.uint8)
    return Image.fromarray(ink, "L")


def trim(ink: Image.Image, thr: int = 26):
    a = np.asarray(ink)
    ys, xs = np.where(a > thr)
    if len(ys) == 0:
        return None, None
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    return ink.crop(box), box


PUNCT = set("，。、；：？！）】》」』’”…—,.;:?!)]}")


SMALL_NAT = 0.30          # 天然尺寸小于这个（em）的当"小标记"：· ' " “ ” 等


def normalize(ink: Image.Image, ch: str, bold: int = 0,
              nat: float | None = None, ycen: float | None = None,
              ybot: float | None = None
              ) -> tuple[Image.Image, int, int, float]:
    """按墨迹包围盒归一化到 em 方框，返回 (图, dx, dy, advance)。

    dx/dy：贴到页面时相对"笔尖原点 = (0, 基线)"的偏移。

    nat / ycen / ybot：这个字在 12mm 格子里的天然大小、中心高度、**墨迹底边高度**
    （单位都是"格"，1.0 = 一格，格子下沿 0.80 处当基线）。

    **竖向必须按写出来的位置放**，不能一律"墨迹底边贴基线"：
    否则 `一`、`：`、`→`、`——` 这类笔画够不到基线的字会全部掉到基线上、
    变成一条下划线；标点则会被推到格子底边外面。小标记（间隔号、引号）同理，
    还要按天然尺寸入图，否则一个点会被拉成一坨黑团。
    """
    big = max(ink.width, ink.height)
    is_punct = ch in PUNCT
    wide = (not is_punct) and (ord(ch) > 0x2E80)
    small = (not is_punct and not wide and nat is not None and nat < SMALL_NAT)
    # 目标尺寸：汉字墨迹高 ≈ 0.86 em；标点/小标记按**天然尺寸**（绝不放大）
    if is_punct or small:
        if nat is not None:
            # 按天然大小（写多大就多大），只封顶 0.9 em，避免一个括号被放大成柱
            scale = (min(nat, 0.90) * EM) / max(1, big)
        else:
            scale = min(EM * 0.20 / max(1, ink.height),
                        EM * 0.30 / max(1, ink.width))
    elif wide:
        target_h = EM * 0.86
        target_w = EM * 0.90
        scale = min(target_h / max(1, ink.height), target_w / max(1, ink.width))
    else:
        target_h = EM * 0.68
        target_w = EM * 0.64
        scale = min(target_h / max(1, ink.height), target_w / max(1, ink.width))
    # 单笔画字（如 一、-）限幅，别被放大得离谱
    if not is_punct and not small and big > 0 \
            and min(ink.width, ink.height) <= max(2, big * 0.09):
        scale = min(scale, EM * 1.05 / max(1, big))
    scale = max(0.04, min(scale, 6.0))
    w, h = max(1, int(ink.width * scale)), max(1, int(ink.height * scale))
    pic = ink.resize((w, h), Image.LANCZOS)
    if bold:                                     # 让真迹的笔画粗细接近回落字体
        for _ in range(int(bold)):
            pic = pic.filter(ImageFilter.MaxFilter(3))

    canvas = Image.new("L", (int(EM * 1.3), int(EM * 1.35)), 0)
    base = canvas.height * 0.80                              # 画布里的基线高度
    if is_punct:
        adv = max(int(w * 1.15), int(EM * 0.42))
        ox = int((canvas.width - w) / 2)          # 居中，别偏左压到前一个字
    elif small:
        adv = max(int(w * 1.25), int(EM * 0.30))
        ox = int((canvas.width - w) / 2)
    elif wide:
        adv = EM
        ox = int((canvas.width - w) / 2)
    else:
        adv = max(int(w * 1.12), int(EM * 0.34))
        ox = int((canvas.width - w) / 2)
    # 竖向：按写字人自己的位置放（墨迹底边离基线多远，就照原样保留）
    if ybot is not None:
        oy = int(round(base + (ybot - 0.80) * EM - h))
    elif small and ycen is not None:
        oy = int(round(base + (ycen - 0.80) * EM - h / 2))
    else:
        oy = int(base - h)                                   # 老规则：底边贴基线
    oy = int(max(0, min(canvas.height - h, oy)))
    canvas.paste(pic, (ox, oy))
    dx = -((canvas.width - adv) // 2)
    dy = -(int(base))                    # 画布基线 ↔ 页面基线，一律这样对齐
    return canvas, dx, dy, adv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path, default=Path("."),
                    help="项目目录（raw/ 与 glyphs/ 都在它下面）")
    ap.add_argument("--tag", default="corpus")
    ap.add_argument("--passes", default="1,2")
    ap.add_argument("--raw", type=Path, default=None, help="原始字迹目录（默认 <project>/raw）")
    ap.add_argument("--out", type=Path, default=None, help="字库输出目录（默认 <project>/glyphs）")
    ap.add_argument("--bold", type=int, default=1, help="笔画加粗档数（让真迹接近回落字体）")
    ap.add_argument("--demo", action="store_true", help="用矢量笔迹拼样张")
    ap.add_argument("--demo-text", default="实验一半加器实验：由真值表写出 S = A ⊕ B，C = A·B。")
    args = ap.parse_args()

    proj = load_project(args.project)
    raw_root = Path(args.raw) if args.raw else proj.raw
    outdir = Path(args.out) if args.out else proj.glyphs
    outdir.mkdir(parents=True, exist_ok=True)

    variants: dict[str, list[dict]] = {}
    n_files = 0
    for pw in [int(x) for x in args.passes.split(",") if x.strip()]:
        d = raw_root / f"{args.tag}-p{pw}"
        if not d.is_dir():
            continue
        for png in sorted(d.glob("*.png")):
            meta_f = png.with_suffix(".json")
            if not meta_f.exists():
                continue
            meta = json.loads(meta_f.read_text(encoding="utf-8"))
            ch = meta.get("char") or ""
            if not ch or ch == " ":
                continue
            ink = load_png_ink(png)
            if ink is None:
                continue
            t, box = trim(ink)
            if t is None:
                continue
            # 从矢量笔迹量出这个字的天然大小 / 中心高度（单位：格 = 1 em）
            nat = ycen = None
            st = meta.get("strokes") or []
            if st:
                xs = [p[0] for seg in st for p in seg]
                ys = [p[1] for seg in st for p in seg]
                if xs and ys:
                    nat = max(max(xs) - min(xs), max(ys) - min(ys))
                    ycen = (min(ys) + max(ys)) / 2.0
            ybot = max(ys) if ys else None
            canvas, dx, dy, adv = normalize(t, ch, bold=args.bold, nat=nat,
                                            ycen=ycen, ybot=ybot)
            k = len(variants.setdefault(ch, [])) + 1
            fn = f"{ord(ch):05x}_v{k}.png"
            canvas.save(outdir / fn)
            variants[ch].append({"file": fn, "w": canvas.width, "h": canvas.height,
                                 "dx": dx, "dy": dy, "adv": adv,
                                 "src": png.name, "pass": pw})
            n_files += 1

    index = {"em": EM, "count": len(variants),
             "glyphs": {f"{ord(c):05x}": {"char": c, "variants": v}
                        for c, v in sorted(variants.items())}}
    (outdir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1),
                                       encoding="utf-8")

    # 联系表
    chars = sorted(variants)
    if chars:
        cols = min(16, len(chars))
        rows = (len(chars) + cols - 1) // cols
        cell = 96
        sheet = Image.new("L", (cols * cell, rows * cell), 255)
        d = ImageDraw.Draw(sheet)
        for i, c in enumerate(chars):
            v = variants[c][0]
            g = Image.open(outdir / v["file"])
            s = cell * 0.8 / max(g.width, g.height)
            g = g.resize((max(1, int(g.width * s)), max(1, int(g.height * s))), Image.LANCZOS)
            x, y = (i % cols) * cell, (i // cols) * cell
            sheet.paste(Image.eval(g, lambda p: 255 - p), (x + (cell - g.width) // 2,
                                                           y + (cell - g.height) // 2))
            d.rectangle([x, y, x + cell - 1, y + cell - 1], outline=220)
        sheet.save(outdir / "montage.png")

    print(f"✔ 入库 {n_files} 个字迹图，覆盖 {len(variants)} 个字符 → {outdir}", file=sys.stderr)
    have = set(variants)
    print(f"  多写法：{sum(1 for c in chars if len(variants[c]) > 1)} 个字符有两遍",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
