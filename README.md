# -
Panda AI的小机器人

**新队友先看 [`开发交接.md`](开发交接.md)**（分支 `design-system`）：硬件接线、代码结构、编译烧录、网络、协议、已知问题都在里面。下面是早期的说明，部分已过时。

## 模拟器 `sim/`

ESP32-S3 + 3.5″（480×320）屏幕的网页版"假机器人"，说的是《队友交接文档》§4 的 JSON 协议，可以直接当手机 H5 用。

```bash
python3 -m http.server 8090 -d sim     # 打开 http://localhost:8090
pip install websockets && python hub/mock_hub.py   # 可选：假中枢，终端里输 JSON 发给机器人
```

- `?ws=ws://<笔记本IP>:8765/robot` 指定中枢地址；https 部署的页面默认单机模式
- `?demo=moyu|feishu|a2a|all` 打开即自动播放三个使用场景（录 Demo 视频用）

## PandaAI 赛道：寻找你的交易人格 `sim/game.html`

互动（陪 DeskBot 走一段隐藏名字的历史行情，6 个关键时刻选 加仓/持有/减仓）→ 画像（从行为算 风险偏好/趋势跟随/逆向思维/耐心/果断，匹配 5 种交易人格）→ 推荐（PandaAI 入口 + QuantSkill）→ 下一步（去 PandaAI / 订阅 DeskBot 提醒 / 再玩一局）。

- 打开 http://localhost:8090/game.html ；`?auto=1` 自动玩（展台循环、截图）
- 行情入口 `sim/game/scenario.js` 的 `fromBars({name, code, period, bars:[{date, close}]})`，Panda Data 日线直接喂进来
- 人格与推荐表在 `sim/game/persona.js`

## 协议新增（在交接文档 §4 基础上）

```jsonc
// 摸鱼模式：只有眼睛。pct = 自选股平均涨跌幅(%)，vol = 波动 0–1，alert = 眨眼提醒一次
{"t": "face", "state": "stealth", "card": {"pct": 1.2, "vol": 0.4, "alert": false}}
// 伪装成办公助手（老板键画面）
{"t": "face", "state": "decoy", "card": {"meeting": "15:00 · 产品评审会", "todo": 3}}
// 上行：老板键（双击屏幕，机器人本地立即切换，再上报）
{"t": "boss", "on": true}
```

表情对照：≥ +2% 眯眼笑 + 脸红；+0.5~2% 微红；−0.5~−2% 眼皮下垂；≤ −2% 更低更"难过"。偏紫 = 涨，偏青 = 跌。老板键打开时，下行的表情只缓存不显示。

## 屏幕设计实验室 `sim/lab.html`

屏幕全部按 [DeskBot 设计系统](https://claude.ai/artifact/QWRb6EptAeYye9yTq3593V) v1 的 tokens 画（`sim/screen.css`）。实验室把三个使用场景的每一步画成故事板，可以调旋钮看不同版本：

- 旋钮：屏幕尺寸（**2.8″ 320×240 = T5 实机，默认** / 3.5″ 480×320）、主题（浅 / 深）、强调色、数字字体（点阵 / 细体 / 等宽）、卡片（反白 / 安静）、圆角、字号
- 并排对比：选一个旋钮，每一步同时画出它的所有选项
- 旋钮存在浏览器里，模拟器和游戏页（同一浏览器的其他标签页）实时跟着变
- 三个场景和示例数据在 `sim/usecases.js`：盘中摸鱼看盘 / 飞书会议助手 / A2A 盘前简报。每一步都是协议消息，模拟器按顺序播放

两种屏幕各有一套尺寸变量（`sim/screen.css` 里的 `data-size`）：小屏不是等比缩小，正文 ≥13px、说明 ≥10px。并排看时按物理大小对齐（2.8″ 屏放大 1.175 倍）。真机上标题尽量控制在一行。

新增屏幕状态：`meeting`（会议倒计时 + 刻度尺）、`weather`（市场天气）、`agent`（A2A 智能体发言）、`brief`（三条要点）、`ask`（冲动前的护栏）。字段见 `sim/usecases.js` 里的示例。
