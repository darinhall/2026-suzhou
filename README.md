# -
Panda AI的小机器人

## 模拟器 `sim/`

ESP32-S3 + 3.5″（480×320）屏幕的网页版"假机器人"，说的是《队友交接文档》§4 的 JSON 协议，可以直接当手机 H5 用。

```bash
python3 -m http.server 8090 -d sim     # 打开 http://localhost:8090
pip install websockets && python hub/mock_hub.py   # 可选：假中枢，终端里输 JSON 发给机器人
```

- `?ws=ws://<笔记本IP>:8765/robot` 指定中枢地址；https 部署的页面默认单机模式
- `?demo=feishu|market|all` 打开即自动播放剧本（录 Demo 视频用）

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
