# demo：零依赖跑通整条管线

不需要你的手迹，也不需要外部字体（用系统里的中文字体造一套"假字库"，
格式与真迹字库完全一致，所以走的是**同一套代码路径**）。

```bash
python make_demo_docx.py      # → src_docx/demo.docx（条目 + 空行）
python make_demo_glyphs.py    # → glyphs/（index.json + png）
inkcell fill --project . --docx src_docx/demo.docx
inkcell verify --src src_docx/demo.docx --out out/report.docx \
               --fill-data data/fill_data.json --slots-dir work/slots
```

产物：`out/report.docx`（用 Word 打开看效果）、`work/slots/*.png`（每张"格子图"，
可以直接看单个屏幕里写了什么）。

想换成真迹：把你的字库放到 `glyphs/`，或 `inkcell fill --glyphs /path/to/glyphs`。
