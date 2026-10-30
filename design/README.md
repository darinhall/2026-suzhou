# DeskBot 设计系统 `design/`

屏幕（3.5″，480×320）的视觉规范：暖灰底、黑色胶囊/圆形按钮、点阵大数字、刻度尺、只有一个橙色强调色。完整规则见 [`BRAND.md`](BRAND.md)，参考图在 `references/`。

```bash
python3 -m http.server 8091 -d design   # 打开 http://localhost:8091 看全部组件（右上角切换深色）
python3 design/scripts/build_tokens.py  # 改完 tokens.json 后重新生成下面两个文件
```

| 文件 | 用途 |
|---|---|
| `tokens.json` | **唯一来源**：颜色（light / dark）、字体、间距、圆角、阴影 |
| `tokens.css` | 生成的 CSS 变量，网页 / `sim/` 用 |
| `deskbot_tokens.h` | 生成的 C 头文件，Arduino + LVGL 固件用：`lv_color_hex(DB_LIGHT_INK)` |
| `components/<名>/preview.html` | 每个组件的网页预览 + `README.md` 用法 |
| `BRAND.md` | 品牌手册：文案、颜色、字体、布局、动效 |

组件：`MessageCard`（飞书消息 / 日程红卡）、`MarketCard`（盯盘卡片）、`Face`（点阵眼睛）、`Numeral`、`TickRuler`、`DayPicker`、`Button`。

注意：
- 字体（Geist / Geist Mono / Doto 点阵）是 Google Fonts 的开源替代；固件里要用 `lv_font_conv` 按 `deskbot_tokens.h` 里的字号转成位图字体，只保留用到的字符。
- 涨跌：红涨绿跌，并且**总是**带 ▲▼ 和 +/− 号。
- 还没覆盖 `sim/` 新增的 `stealth`（摸鱼）和 `decoy`（老板键）两种表情。
