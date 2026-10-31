# T16 人格驱动行为（`brain/personas.json`）· **搁置（11-01 01:30 决定）**

> 先不做，不进演示。`brain/personas.json` 和 `brain/persona.py` 保留：提醒阶梯用其中的 `standard`（标准）阈值。5 个人格的数据和游戏一致，以后要接只需做下面的"同步到机器人"和设置面板。

**一句话：** 同一台机器人，因人而异。交易人格游戏（PandaAI 赛题）的结果写进设置，决定它什么时候提醒、怎么说话、多容易摇头。

## 文件
- `brain/personas.json`：5 个人格，**id 和 `sim/game/persona.js` 完全一致**（surfer / hunter / guardian / holder / flash），行为照抄游戏里每个人格的 `robot:` 描述。
- `hub/profile.json` 加 `"persona": "guardian"`（默认稳健守望者：最安静，展台不吵）。
- 字段：
  ```jsonc
  {"id":"guardian","name":"稳健守望者",
   "alerts":{"cross_pct":3.0,"glance_ratio":0.7,"surge_pct_5m":1.5,"vol_ratio":3.0,"max_level":2,"cooldown_s":60,"quiet_hours":["09:30-11:30","13:00-15:00"]},
   "brief":{"morning":true,"close":false,"weekly":false},
   "guard":{"drawdown_warn_pct":5.0,"advice_shake":2},
   "voice":{"tone":"简短、稳重，先讲风险","focus":["max_drawdown","volatility"]}}
  ```

## 做什么
- [ ] `brain/persona.py`：`load(id) -> Persona`，不认识的 id 退回 `guardian`，字段缺省用默认值。
- [ ] 中枢：`{"t":"profile","set":{"persona":"surfer"}}` 生效（`modes.py` 校验 id）。
- [ ] 游戏 `sim/game.html` 出结果后，"同步到机器人"按钮发上面这条消息。
- [ ] 大模型提示词把 `voice.tone` 和 `voice.focus` 带进去（T05）。
- [ ] 模拟器设置面板加人格下拉框。

## 验收
- [ ] `tests/test_persona.py` 全绿（5 个 id 都能读、和游戏 id 一致、缺字段有默认值）。
- [ ] 切换人格后不用重启，下一次提醒就按新阈值。
