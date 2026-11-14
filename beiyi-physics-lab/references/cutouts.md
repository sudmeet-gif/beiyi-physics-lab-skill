# B5 图表裁剪稿

先列本次主报告的全部图表，再逐项定界；不包含默认只供电子查阅的附录。保留标题、表头、单位、末行、极性、轴箭头和图注。选区略超出最外侧笔画；文字范围不能代替图形范围，最右侧电源极板容易漏裁。

A4裁剪页默认约86%，内容最大宽153 mm，每侧2 mm留边，块间留裁剪间距。按实际B5可粘贴宽度调整；宽表不能缩到无法读写，长表整体放到下一页，小图可并排。保留矢量。写明“A4、单面、实际大小/100%”，不要再次按B5缩放。

## 清单与工具

工具 `scripts/build_cutouts.py` 的位置参数依次为源报告、UTF-8 JSON清单、目标PDF：

```json
{
  "items": [
    {"id": "apparatus", "page": 1, "bbox": [46, 240, 549, 478]},
    {"id": "results", "page": 4, "bbox": [46, 400, 549, 596], "caption": "拟合与计算结果记录表"}
  ]
}
```

页码从1开始，id唯一。bbox是 `[左, 上, 右, 下]`，单位为PDF点，原点在源页**左上角**，72点为1英寸。必须按实际PDF测定，不能套用示例坐标。caption可省略，源图已有标题时不重复。

清单顺序就是裁剪顺序；小块自动并排，整行放不下则换页。先将带旋转标记的源PDF规范化，再测定边界；工具遇到未规范化的旋转会报错，不猜坐标。

```text
python scripts/build_cutouts.py report.pdf figures.json cutouts.pdf --scale 0.86 --max-content-width-mm 153 --layout-json work/layout.json
```

需要pypdf、reportlab。默认寻找Windows宋体/黑体及常见可嵌入中文TrueType字体；也可用 `--font`、`--bold-font` 指定本机字体。不随skill分发字体。

`--layout-json`记录实际比例、每块位置和外框尺寸，仅用于工作区核对，不是新增交付物。工具检查范围、重复ID、重叠与页边界，但不能判断选区是否漏了一根电源极板，仍需渲染查看。

例如 `pdftoppm -r 130 -png cutouts.pdf work/cutouts`。检查所有输出页的右侧元件、表格边线与末行、坐标单位、下标和裁剪留边。最终仅返回裁剪稿与必要打印说明。
