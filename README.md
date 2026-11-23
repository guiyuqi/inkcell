# inkcell · 写字台

**写一遍，之后该手写的东西都由你的手迹代笔。**
*Your handwriting, as a font — and back into Word without touching the layout.*

用手机（随手写板/压感笔）一格一字采集手迹 → 生成**位图字形库**（不需要 TTF 工具链）
→ 把字迹**回填进既有的 `.docx`**，而且版面一行不动。中文实验报告、签名页、
手写作业、讲义补充，都是同一套流程。

MIT License · Python ≥ 3.10 · 不做云端，全部离线

---

## 为什么另做一个

| 现成的轮子 | 它做的事 | 缺的那一环 |
| --- | --- | --- |
| `perfect-freehand` 等笔刷库 | 把笔迹画得好看 | 只画，不入库、不回填文档 |
| 手写字体教程（扫描 → FontForge → TTF） | 做出一套字体 | 要手工切字、调基线，中文动辄几千字，跑一遍数小时 |
| 手写合成（handwriting synthesis） | 让机器**生成**手写笔迹 | 那是"假手写"，不是**你的**字 |
| Word 的"签名图片"功能 | 贴一张图 | 会顶开行高、压扁图片、破坏分页 |

inkcell 补的是整条链路上没人做的那一段：**离线压感采集 → 字形库 → 回填既有文档且版面不变**。

## 三条铁律（都是踩坑换来的）

1. **绝不重排原文档。** 只往已有的空行里贴浮动图（`wp:anchor behindDoc="1" wrapNone`），
   段落数、`exact` 行距数必须一字不差；完成后有 `inkcell verify` 自动核对。
2. **绝不使用 inline 图。** inline 会参与行高、把后面的内容挤到下一页——这就是
   "条目被吃了" 的经典翻车。
3. **图的显示宽高比必须等于 PNG 真实宽高比。** 差 3% 以上就会看到字被拉长，
   `inkcell verify` 会逐张量出来。

## 安装

```bash
git clone https://github.com/guiyuqi/inkcell && cd inkcell
pip install -e .              # 需要 pillow>=10.1 / numpy / scipy / python-docx
# 想打印格子纸（可选）：pip install -e ".[sheets]"
```

字体回退是可选的：仓库不带字体（CJK 字体 10–25 MB）。把任意手写体 `.ttf` 放进
`assets/fonts/`，或设 `INKCELL_FONTS=/path/to/fonts`。**字库覆盖率高时完全不需要字体。**

## 30 秒跑通（不需要你的手迹，也不需要字体）

```bash
cd examples/demo
python make_demo_docx.py        # 造一份"条目 + 空行"的模板 docx
python make_demo_glyphs.py      # 用系统里的中文字体造一套"假字库"（格式与真迹字库一致）
inkcell fill --project . --docx src_docx/demo.docx
inkcell verify --src src_docx/demo.docx --out out/report.docx \
               --fill-data data/fill_data.json --slots-dir work/slots
```

## 完整流程

```bash
# 0) 项目目录（一个文件夹就是一个项目）
mkdir my-report && cd my-report
mkdir -p data src_docx assets/fonts
#    data/fill_data.json   ← 每个条目要写什么（见下）
#    data/cover.json       ← 可选，封面字段 {"班 级": "…"}
#    src_docx/tpl.docx     ← 学校/单位给的原始文档

# 1) 生成字表：报告用字排最前，后面补常用字
inkcell sheets --project . --charset gb2312 --passes 4 --order char-major --no-pdf

# 2) 写字（二选一）
inkcell desk --project . --tag gb2312 --all-passes        # 浏览器：http://127.0.0.1:8765
inkcell app  --project . TAG=gb2312 ALL=1                 # 手机 APK：离线、带桌面图标

# 3) 入库：每格字迹 → 一张灰度图 + dx/dy/adv
inkcell glyphs --project . --tag gb2312 --passes 0        # 用矢量笔迹重渲（可调压感对比）
#    或者直接用写字台画的 png：
# inkcell import --project . --tag gb2312 --passes 0

# 4) 填文档
inkcell fill --project . --docx src_docx/tpl.docx

# 5) 交付前自检
inkcell verify --src src_docx/tpl-trans.docx --out out/report.docx \
    --fill-data data/fill_data.json --slots-dir work/slots
```

## 数据格式

`data/fill_data.json`，两种写法都支持：

```jsonc
// 1) 扁平：一个条目一段
{
  "一、实验目的": { "text": ["第一行", "第二行"] },
  "三、实验结果": { "table": [["项目", "结果"], ["版面", "未改动"]] }
}

// 2) 分节：同一批条目名在多个章节里重复时用（报告/论文常见）
{
  "实验一 半加器实验": {
    "dir": "05-报告-半加器",              // 可选：图在 assets/figures/<dir>/figures/
    "fill": {
      "一、实验目的":   { "text": ["…"] },
      "3.电路接线图":   { "figure": "half-adder.png" },
      "四、Entity…程序": { "code": ["top.vhd", "core.vhd"] }   // 贴印刷体代码，不手写
    }
  }
}
```

条目后面**紧跟的空段落就是"格子"**——留几行就写几行，篇幅完全由模板决定，
inkcell 不会替你增删版面。文字太长时自动缩小字号（绝不丢内容），
行数超过格子会提示。

## 已知边界

- 采集端只有 Android（WebView 壳）；iOS 没做。浏览器方式在电脑上也能用。
- 手写字体**只影响正文内容**；标题、表头这些模板自带的文字仍是印刷体（一般正是想要的）。
- `--order char-major`（同字连写）比"整本写完再写一遍"快得多，适合一次攒几千字。
- 文档必须是 `.docx`。Strict Open XML（Word 另存时可能产生）会被自动转成普通 OOXML。
- 生成结果**需要你自己在 Word 里看一眼**：项目不做 docx 渲染，机器上也没装 Word。

## 隐私

`raw/`（原始笔迹）、`glyphs/`（字库）、`out/`（成品）都在 `.gitignore` 里。
**别把它们提交到公开仓库**——手写字迹可以被用来伪造签名。

## 目录结构

```
inkcell/
  inkcell/collect/   # sheets（字表）+ desk（写字台页面/服务）
  inkcell/glyph/     # normalize（归一化）+ import_png + from_strokes + bitmap（位图字库）
  inkcell/render/    # core/layout/slot/anchor：把字画到页面上
  inkcell/doc/       # filler（填 docx）+ verify（自检）+ strict2trans
  inkcell/app/       # Android WebView 壳：Java + 打包脚本（不用 Gradle）
  examples/demo/     # 零依赖跑通的演示
  docs/              # 管线细节与坑
```

## License

MIT © 2026 guiyuqi
