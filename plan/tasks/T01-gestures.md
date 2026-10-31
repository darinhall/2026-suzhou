# T01 ID1 定基准 + 点头 / 摇头 · 轨道 A · 阶段 0–1

**目标：** 中枢发 `{"t":"gesture","name":"nod|shake"}`，板子点头 / 摇头，安全、可重复。

## 为什么先做
**ID1（偏航 / 摇头）停在 ~4080，靠近量程尽头 4095**，往一边转 10° 就会撞到量程边界。不定基准就不能摇头。见《开发交接》§2。

## 做什么
- [ ] 手动把头转到"正前方"，确认安全后给 ID1 定基准（仿照 `servotest.cpp` 的 `rebasePitch`，写一个 `rebaseYaw`，同样记 NVS 只做一次）。**全程 30% 扭矩，先 ≤5° 小幅试。**
- [ ] `servotest.cpp`：`gesture(name, times, ampDeg)`：
  - nod：ID2 绕当前位置 ±amp，`times` 次
  - shake：ID1 绕当前位置 ±amp，`times` 次
  - amp 上限 15°；做完回原位并放松扭矩
  - 非阻塞或 ≤1.2 秒（不能卡住 WebSocket 太久，否则掉线）
- [ ] `main.cpp` 收 `gesture` 消息。
- [ ] 模拟器加两个按钮（或用 `relay` 手发）。

## 验收
- [ ] 连发 10 次 nod、10 次 shake，位置不漂移（回到 ±1°）。
- [ ] 动作中屏幕和 WebSocket 不断。
- [ ] `{"t":"gesture","name":"shake","amp":40}` 被限到 15°。

## 风险
- 舵机 12 V 电源现场有没有？没有就整个 T01 降级为"屏幕上画点头 / 摇头的表情动画"（`ui.cpp`），协议不变。
