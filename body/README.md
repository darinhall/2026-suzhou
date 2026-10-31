# 身体固件（ESP32 + 两个飞特 ST3215）

连 WiFi → UDP 找中枢 → `hello(role=body)` → 收 `pose` / `gesture` / `torque`，上报 `head_press` / `state`，日志走 `log`（和脸共用 `shared/net.cpp`）。

**状态（10-31）：能编译（`body-esp32`、`body-s3` 两个环境），还没接真舵机测过。** 板子型号和引脚还没定，所以引脚都是 `platformio.ini` 里的 build_flags：

| | 普通 ESP32 | ESP32-S3（DEMO 板，避开屏幕 / 触摸 / PSRAM） |
|---|---|---|
| 舵机总线 RX / TX | 16 / 17 | 47 / 21 |
| 方向脚 `SERVO_DIR` | -1（不用：TX 经 1 kΩ 电阻接 DATA，RX 直接接 DATA，固件丢掉回显） | 同左 |

方向反了（抬头变低头）把 `SERVO_*_SIGN` 改成 -1；舵机 ID 在 `SERVO_YAW_ID` / `SERVO_PITCH_ID`（默认 1 / 2）。

```bash
python3 config/build_net.py
uvx --python 3.12 --from platformio pio run -d body -e body-esp32 -t upload --upload-port <端口>
```

## 它做的事

| | |
|---|---|
| `pose {yaw,pitch,ms}` | 限位 ±150° / ±25°，按"距离 ÷ 时间"算速度，两个舵机一个 SYNC WRITE 包同时动 |
| `gesture` | `nod` `shake` `look_up` `look_down` `home` `startle`（惊醒：猛抬头 + 小摇）；关键帧在板子上排队，新的 `pose` 打断它 |
| `torque {pct}` | 扭矩限制，默认 50；按头要小于 60 才按得动 |
| 按头 | 每 30 ms 读俯仰位置，目标没变、实际被压低 >8° 持续 200 ms → `head_press`，之后锁 1 秒 |
| `state` | 每秒一条：yaw / pitch / 电压 / 温度 |
| 中枢掉线 | 2 秒没连回来 → 1.5 秒慢慢回正（`HUB_LOST_HOME`），不卡在最后一个姿势 |
| 自检 | 开机 ping 两个舵机；没应答记 `SERVO_TIMEOUT`（每 30 秒一次），每 5 秒重试，好了记 `SERVO_OK` 并回正 |

日志码：`BOOT` `SERVO_OK` `SERVO_TIMEOUT` `SERVO_LOW_VOLT` `SERVO_HOT` `HEAD_PRESS` `HUB_LOST_HOME` `GESTURE_UNKNOWN`，加上联网那组（`WIFI_OK` `HUB_FOUND` `WS_UP` …）。

## 上板第一次要查

1. 串口 / 日志页里有没有 `SERVO_OK`。没有就是接线、供电（LM2596 先调到 7.4 V 再接舵机）或 ID 不对。
2. 发一条 `pose` 看方向，反了改 `SIGN`。
3. 用手轻按头：日志里应该出现 `HEAD_PRESS`。没有就把 `torque` 调小。
