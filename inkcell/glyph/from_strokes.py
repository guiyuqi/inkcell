# -*- coding: utf-8 -*-
"""TOOLS/glyph_from_strokes.py —— 用**已存的矢量笔迹 + 压力**重新渲字形库。

写字台当时是用固定参数把笔迹画成 PNG 的；那些参数把压感对比压得很平
（rMin = 0.42·rMax）。既然每次落盘都存了 `strokes`（含每点压力），
就可以不上手重写、直接按新的粗细参数重新渲一遍。

    ./.venv/bin/python TOOLS/glyph_from_strokes.py --tag corpus --passes 1 \
        --out work/v_mid --rmin 0.20 --easing 0.85

参数含义（都是"笔尖半径"，1.0 em = 一格 12mm）：
    --rmax     最大半径，默认 0.030 em（= 线宽 0.06 em，中性笔偏粗）
    --rmin     最轻时的半径相对 rmax 的比例，默认 0.20
    --easing   压力→粗细的曲线指数，1.0 = 线性，<1 抬高中间调
    --psmooth  压力平滑（0 = 完全用原始值，0.35 和页面一致）
    --weight   跨字重量补偿指数：0 = 关，0.5 = 按每字平均压力调粗细
    --ss       超采样倍数
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inkcell.paths import load_project                          # noqa: E402
from inkcell.glyph.import_png import EM, load_png_ink, normalize, trim   # noqa: E402



def smooth_pts(pts: list[list[float]], stream: float, psmooth: float):
    out = []
    for p in pts:
        if not out:
            out.append([p[0], p[1], p[2]])
        else:
            q = out[-1]
            out.append([q[0] + (p[0] - q[0]) * (1 - stream),
                        q[1] + (p[1] - q[1]) * (1 - stream),
                        q[2] + (p[2] - q[2]) * (1 - psmooth)])
    return out


def render_cell(strokes, rmax, rmin, easing, psmooth, stream, weight, ss):
    """把一格笔迹画成 EM×EM（超采样 ss 倍）的灰度墨迹图。"""
    W = H = int(EM * ss)
    img = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(img)
    for seg in strokes:
        if len(seg) < 2:
            continue
        sp = smooth_pts(seg, stream, psmooth)
        xs = [p[0] for p in sp]; ys = [p[1] for p in sp]
        n = len(sp)
        # 弧长
        ln = [0.0]
        for i in range(1, n):
            ln.append(ln[-1] + math.hypot(sp[i][0] - sp[i - 1][0], sp[i][1] - sp[i - 1][1]))
        total = ln[-1] or 1e-6
        taper = max(0.04, total * 0.18)
        L, R = [], []
        for i in range(n):
            a = sp[max(0, i - 1)]; b = sp[min(n - 1, i + 1)]
            nx, ny = -(b[1] - a[1]), (b[0] - a[0])
            m = math.hypot(nx, ny) or 1.0
            nx, ny = nx / m, ny / m
            p = max(0.0, min(1.0, sp[i][2]))
            r = rmax * (rmin + (1.0 - rmin) * (p ** easing))
            r *= weight
            dIn, dOut = ln[i], total - ln[i]
            if dIn < taper:
                r *= 0.3 + 0.7 * (dIn / taper)
            if dOut < taper:
                r *= 0.3 + 0.7 * (dOut / taper)
            r = max(0.0015, r)
            L.append(((sp[i][0] + nx * r) * W, (sp[i][1] + ny * r) * H))
            R.append(((sp[i][0] - nx * r) * W, (sp[i][1] - ny * r) * H))
        d.polygon(L + R[::-1], fill=255)
        # 两端补圆，避免尖头
        for cx, cy, rr in ((L[0][0], L[0][1], 1),):
            pass
    return img


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path, default=Path("."),
                    help="项目目录（raw/ 与 glyphs/ 都在它下面）")
    ap.add_argument("--tag", default="corpus")
    ap.add_argument("--passes", default="1")
    ap.add_argument("--raw", type=Path, default=None, help="原始字迹目录（默认 <project>/raw）")
    ap.add_argument("--out", type=Path, default=None, help="字库输出（默认 <project>/glyphs）")
    ap.add_argument("--rmax", type=float, default=0.030)
    ap.add_argument("--rmin", type=float, default=0.20)
    ap.add_argument("--easing", type=float, default=0.85)
    ap.add_argument("--psmooth", type=float, default=0.5)
    ap.add_argument("--stream", type=float, default=0.35)
    ap.add_argument("--weight", type=float, default=0.0)
    ap.add_argument("--ss", type=int, default=4)
    ap.add_argument("--bold", type=int, default=0)
    args = ap.parse_args()

    proj = load_project(args.project)
    raw_root = Path(args.raw) if args.raw else proj.raw
    outdir = args.out or proj.glyphs
    outdir.mkdir(parents=True, exist_ok=True)

    # 先算全局平均压力，供 --weight 用
    pmeans = []
    for pw in [int(x) for x in args.passes.split(",") if x.strip()]:
        for f in (raw_root / f"{args.tag}-p{pw}").glob("*.json"):
            d = json.loads(f.read_text(encoding="utf-8"))
            ps = [pt[2] for s in d.get("strokes") or [] for pt in s if len(pt) > 2]
            if ps:
                pmeans.append(float(np.mean(ps)))
    pref = float(np.median(pmeans)) if pmeans else 0.3

    variants: dict[str, list[dict]] = {}
    for pw in [int(x) for x in args.passes.split(",") if x.strip()]:
        d = raw_root / f"{args.tag}-p{pw}"
        if not d.is_dir():
            continue
        for js in sorted(d.glob("*.json")):
            meta = json.loads(js.read_text(encoding="utf-8"))
            ch = meta.get("char") or ""
            st = meta.get("strokes") or []
            if not ch or ch == " " or not st:
                continue
            ps = [pt[2] for s in st for pt in s if len(pt) > 2]
            wgt = 1.0
            if args.weight and ps:
                wgt = (float(np.mean(ps)) / pref) ** args.weight
                wgt = max(0.7, min(1.35, wgt))
            img = render_cell(st, args.rmax, args.rmin, args.easing,
                              args.psmooth, args.stream, wgt, args.ss)
            img = img.resize((EM, EM), Image.LANCZOS)
            t, _ = trim(img)
            if t is None:
                continue
            xs = [pt[0] for s in st for pt in s]; ys = [pt[1] for s in st for pt in s]
            nat = max(max(xs) - min(xs), max(ys) - min(ys))
            ycen = (min(ys) + max(ys)) / 2.0
            ybot = max(ys)
            canvas, dx, dy, adv = normalize(t, ch, bold=args.bold, nat=nat,
                                            ycen=ycen, ybot=ybot)
            k = len(variants.setdefault(ch, [])) + 1
            fn = f"{ord(ch):05x}_v{k}.png"
            canvas.save(outdir / fn)
            variants[ch].append({"file": fn, "w": canvas.width, "h": canvas.height,
                                 "dx": dx, "dy": dy, "adv": adv,
                                 "src": js.stem, "pass": pw})

    index = {"em": EM, "count": len(variants),
             "glyphs": {f"{ord(c):05x}": {"char": c, "variants": v}
                        for c, v in sorted(variants.items())}}
    (outdir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    # 联系表
    from PIL import ImageFont
    chars = sorted(variants)
    if chars:
        cols = min(16, len(chars)); rows = (len(chars) + cols - 1) // cols
        cell = 96
        sheet = Image.new("L", (cols * cell, rows * cell), 255)
        dd = ImageDraw.Draw(sheet)
        try:
            fnt = ImageFont.truetype("/mnt/c/Windows/Fonts/simsun.ttc", int(cell * 0.86))
        except Exception:
            fnt = ImageFont.load_default()
        for i, c in enumerate(chars):
            cx, cy = (i % cols) * cell, (i // cols) * cell
            g = Image.open(outdir / variants[c][0]["file"]).convert("L")
            sheet.paste(g, (cx, cy))            # 字形图本身带 dx/dy 偏移，直接贴就对齐
            dd.text((cx + 2, cy + cell - 14), c, font=fnt, fill=150)
        sheet.save(outdir / "montage.png")

    print(f"✔ 从矢量笔迹渲出 {sum(len(v) for v in variants.values())} 个字形，"
          f"覆盖 {len(variants)} 字符 → {outdir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
