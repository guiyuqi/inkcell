# inkcell · 写字台

**写一遍，之后该手写的东西都由你的手迹代笔。**
*Your handwriting, as a font — and back into Word without touching the layout.*

采集手写（手机端，带压感）→ 位图字形库 → 填进既有 `.docx`，版面不变。

MIT License · Python ≥ 3.10 · 全程离线

## 安装

```bash
git clone https://github.com/guiyuqi/inkcell && cd inkcell
pip install -e .
# 要打印格子纸（可选）：pip install -e ".[sheets]"
```

字体回退可选：把任意 `.ttf` 放进 `assets/fonts/`，或设 `INKCELL_FONTS=/path/to/fonts`。
字库覆盖全部要写的字时不需要字体。

## 命令

| 命令 | 作用 |
| --- | --- |
| `inkcell sheets` | 生成字表（每格一个字，带 id/pass） |
| `inkcell desk` | 起写字台（浏览器）或 `--offline-out` 出离线页面 |
| `inkcell app` | 打包手机离线 APK（aapt2 + javac + d8 + apksigner，不用 Gradle） |
| `inkcell import` | 原始字迹 PNG → 字形库 |
| `inkcell glyphs` | 原始矢量笔迹（含压力）→ 重渲字形库，粗细可调 |
| `inkcell sample` | 用字库拼一段样张 |
| `inkcell fill` | 把字迹填进 docx |
| `inkcell verify` | 交付前自检 |

```bash
# 生成字表：报告用字在前，后面补常用字；同一个字连写四遍
inkcell sheets --project . --charset gb2312 --passes 4 --order char-major --no-pdf

# 写字（浏览器 / 手机 APK）
inkcell desk --project . --tag gb2312 --all-passes
inkcell app  PROJECT=.

# 入库、填充、自检
inkcell glyphs --project . --tag gb2312 --passes 0
inkcell fill   --project . --docx src_docx/tpl.docx
inkcell verify --src src_docx/tpl-trans.docx --out out/report.docx \
    --fill-data data/fill_data.json --slots-dir work/slots
```

不写自己的字也能验证管线：`examples/demo/` 有造文档和造假字库的脚本，
跑完 `fill` + `verify` 即可（CI 跑的就是这个）。

## 项目结构

一个文件夹就是一个项目，`--project` 指过去：

```
data/fill_data.json     每个条目写什么（必需）
data/cover.json         封面字段，如 {"班 级": "…"}（可选）
src_docx/*.docx         被填的模板
assets/figures/         要贴的图：<dir>/figures/<file>.png
assets/code/            要贴的代码
sheets/                 生成的产物：manifest-<tag>.json
raw/<tag>-p<N>/         采集的原始字迹（png + json，json 里是矢量笔迹与压力）
glyphs/                 字形库：index.json + 每字一张 png
out/                    生成的 docx / 样张
```

条目后面紧跟的空段落就是"格子"，留几行就写几行——篇幅由模板决定。
文字超长时自动缩小字号，不删内容。

## fill_data.json

```jsonc
// 扁平：一个条目一段
{
  "一、实验目的": { "text": ["第一行", "第二行"] },
  "三、实验结果": { "table": [["项目", "结果"], ["版面", "未改动"]] }
}

// 分节：同名条目在多个章节重复时用
{
  "实验一 半加器实验": {
    "dir": "05-报告-半加器",                     // 图在此目录的 figures/ 下
    "fill": {
      "一、实验目的":   { "text": ["…"] },
      "3.电路接线图":   { "figure": "half-adder.png" },
      "四、Entity…程序": { "code": ["top.vhd", "core.vhd"] }   // 贴印刷体代码
    }
  }
}
```

字段：`text`（段落）、`table`（表格行）、`figure`（整格一张图）、`code`（原文粘贴）。
条目名与文档段落的开头匹配。

## 已知边界

- 采集端只有 Android（WebView 壳）；电脑上是浏览器页面。
- 手写字体只作用于正文内容，模板自带的标题/表头仍是印刷体。
- 只支持 `.docx`；Strict Open XML 会自动转成普通 OOXML。
- 生成结果需要在 Word 里自己看：本项目不做 docx 渲染。

## 注意事项

- 只用浮动图（`wp:anchor` + `behindDoc` + `wrapNone`）。inline 图会参与行高，把后面的内容挤到下一页。
- 图的显示宽高比必须等于 PNG 真实比例，差 3% 以上字就被拉长。`verify` 会逐张量。
- 段落数、`exact` 行距数不能变。`verify` 会与模板对比。
- 行距 `w:line` 的纯数字单位是缇（1/20 磅），`"18pt"` 才是磅——两种都要处理。
- 字形入库时竖向往**写出来的位置**放，不要一律"墨迹底边贴基线"，否则 `一`、`：`、`→` 会掉到基线上。
- 压感→粗细：`rmin` 太小时看不出轻重，0.42 时全压力范围只有 1.3× 差异，0.20 约 2.9×。
- `raw/`、`glyphs/`、`out/` 已在 `.gitignore` 里。手写字迹可以用来伪造签名，别提交。

## License

MIT © 2026 guiyuqi
