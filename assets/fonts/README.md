# 字体放这里（可选）

仓库不附带字体（CJK 字体 10–25 MB）。需要"缺字回落到字体"时，
把任意 `*.ttf` / `*.otf` 放进本目录，或用环境变量指定：

```bash
export INKCELL_FONTS=/path/to/fonts
```

适合的中文手写体（都是 OFL，免费可商用）：
清松手写体 JasonHandwriting、Yozai（悠哉）、Xiaolai（小赖）、LXGW WenKai（霞鹜文楷）。

**字库覆盖率高时不需要字体**：所有字都在 `glyphs/` 里时，渲染完全走真迹。
