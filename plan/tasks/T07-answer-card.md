# T07 答案卡片 · 轨道 A（板子）+ C（模拟器）· 阶段 1

**目标：** `face state=answer` 在板子和模拟器上长得一样，按 protocol.md 画。

## 板子 `esp32s3/bringup/src/screens.cpp`
- [ ] `answer` 加进 `handles()`；简洁 / 专业两种密度都画（简洁：大字 head + 一条线；专业：q + head + 双线 + stats 2×2 + pts）。
- [ ] 颜色：tone=up 红、down 绿、flat 灰、warn 黄边框（用 `design/tokens.json` 的语义色，过 `devColor()`）。
- [ ] 折线：pts 自己归一到绘图区；两条线不同色 + 图例。
- [ ] 字段缺失不崩（series 没有就不画图，stats 少于 4 个就少画）。
- [ ] 底部 `say` 字幕（≤2 行）+ `src` 小字，永远显示。
- [ ] 配色跟 T14 的熊猫黑白主题走（先用现有主题画，T14 换 token 即可）。
- [ ] 新表情 state：`thinking`（`ui.cpp`，眼睛往上看 + 三个点）。

## 模拟器 `sim/`
- [ ] `screen.css` / 渲染器里加 `answer`，和板子同版面（480×320 坐标照抄）。

## 验收
- [ ] 用 `tests/fixtures/cards/*.json`（3 个剧本各一张 + 一张缺字段的）分别发给板子和模拟器，拍照对比。
- [ ] 一张卡从收到到上屏 < 300 ms。
