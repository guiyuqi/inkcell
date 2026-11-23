# -*- coding: utf-8 -*-
"""inkcell/paths.py —— 一个"手写项目"的目录约定 + 字体/工具路径。

项目就是一个普通文件夹，约定如下（都可由 CLI 的 --project 指过去）：

    <project>/
      data/fill_data.json     # 每个条目要写进去什么（文本/表格/图/代码）
      data/cover.json         # 可选：封面、表头这类固定字段（label → 文字）
      src_docx/*.docx         # 模板：被填的原始文档（Strict OOXML 会自动转）
      assets/figures/*.png    # 要贴的图（可以直接打印的成品图）
      assets/code/*.txt|vhd   # 要贴的代码
      sheets/                 # 生成的格子字表（manifest-*.json）
      raw/<tag>-p<N>/         # 采集回来的原始字迹（png + json）
      glyphs/                 # 入库后的字形库（index.json + png）
      out/                    # 生成结果（docx / 样张）
      work/                   # 中间产物（每格的小图）

这套路径对"写字台采集"和"文档填充"是同一套，所以一个项目可以同时是
"某个作业"和"自己的字库积累"，也可以拆成两个项目（--project 各指一个）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG_ROOT = HERE.parent                    # 仓库根（含 pyproject.toml）

# 字体回退用（OFL）。仓库里不塞字体（CJK 动辄 10~25 MB），
# 放自己的 .ttf/.otf 到 assets/fonts/ 或用 INKCELL_FONTS 指过去。
FONTS = Path(os.environ.get("INKCELL_FONTS") or (PKG_ROOT / "assets" / "fonts"))


CJK_FONT_CANDIDATES = (
    "/mnt/c/Windows/Fonts/simsun.ttc",       # WSL 下的宋体
    "/mnt/c/Windows/Fonts/msyh.ttc",
    "/System/Library/Fonts/PingFang.ttc",    # macOS
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)


def find_cjk_font(extra=()) -> Path | None:
    """找一个能显示中文的字体文件（demo / 标题之类的打印文字用）。"""
    for p in list(extra) + [*default_fonts(), *CJK_FONT_CANDIDATES]:
        if p and Path(p).exists():
            return Path(p)
    return None


def default_fonts(extra=()) -> list[Path]:
    """按顺序返回可用字体：先 extra，再 assets/fonts 里的 .ttf/.otf。"""
    out: list[Path] = [Path(p) for p in extra]
    if FONTS.is_dir():
        out += [p for p in sorted(FONTS.iterdir())
                if p.suffix.lower() in (".ttf", ".otf")]
    return out


@dataclass(frozen=True)
class Project:
    """项目目录 + 各种约定位置的便捷访问。"""

    root: Path

    def __post_init__(self):  # noqa: D105
        object.__setattr__(self, "root", Path(self.root).expanduser().resolve())

    # ---- 输入 ----
    @property
    def data_dir(self) -> Path: return self.root / "data"

    @property
    def fill_data(self) -> Path: return self.data_dir / "fill_data.json"

    @property
    def cover(self) -> Path: return self.data_dir / "cover.json"

    @property
    def src_docx(self) -> Path: return self.root / "src_docx"

    @property
    def assets(self) -> Path: return self.root / "assets"

    @property
    def figures(self) -> Path: return self.assets / "figures"

    @property
    def code(self) -> Path: return self.assets / "code"

    # ---- 采集 / 字库 ----
    @property
    def sheets(self) -> Path: return self.root / "sheets"

    @property
    def raw(self) -> Path: return self.root / "raw"

    @property
    def glyphs(self) -> Path: return self.root / "glyphs"

    # ---- 输出 ----
    @property
    def out(self) -> Path: return self.root / "out"

    @property
    def work(self) -> Path: return self.root / "work"

    def manifest(self, tag: str) -> Path:
        return self.sheets / f"manifest-{tag}.json"

    def raw_dir(self, tag: str, passes: int | str) -> Path:
        return self.raw / f"{tag}-p{passes}"

    def ensure(self) -> "Project":
        for d in (self.data_dir, self.src_docx, self.assets, self.sheets,
                  self.raw, self.glyphs, self.out, self.work):
            d.mkdir(parents=True, exist_ok=True)
        return self


def load_project(path) -> Project:
    return Project(Path(path))
