# NiceMCU T5（脸）调试记录

板子：NiceMCU-T5 2.8IPS（涂鸦 T5-E1 模组）。TuyaOpen 里的板名 `NICEMCU_T5_2_8ISP`；出厂固件里叫 `SPARKLEIOT_T5_DEV`，引脚完全一样。

## 已确认（2026-10-31）

| 部件 | 型号 / 引脚 | 状态 |
|---|---|---|
| 串口 | WCH CH340（0x1A86:0x7523），Mac 自带驱动，`/dev/cu.usbserial-*` | ✅ |
| 日志 | **460800**，和烧录共用同一个串口（UART0） | ✅ |
| 屏幕 | 2.8″ ST7789，240×320，横屏显示（实际 **320×240**），SPI0：CLK P44 · MOSI P46 · CS P45 · DC P47 · RST P6 · 背光 P9（高电平亮） | ✅ |
| 触摸 | CST816（芯片 ID 0xB6），I2C1：SCL P20 · SDA P21 · RST P23 | ✅ |
| 喇叭 | 功放使能 P7 | ✅ 开机有提示音 |
| 麦克风 | T5 片上音频 ADC，16 kHz 单声道，带回声消除 | 待测 |
| 按键 | P8 | — |
| 摄像头 | GC2145（没装，日志里的 `gc2145 i2c write err` 可以忽略） | — |

## 踩过的坑

- **屏幕全黑 + 日志一直报 `tdd_tp_i2c.c send addr fail` / `Failed to read tp data`**：屏幕排线接触不良。断电，打开排线座的卡扣，再扣回去就好了。触摸芯片和屏幕在同一个模组上，触摸 I2C 不通通常说明排线没接好。
- 偶尔一条 `send addr fail` 是正常的：CST816 没人摸时会休眠，不回 I2C；手指按在屏上时就不报错。持续刷屏才说明排线有问题。
- 出厂固件闲置一段时间会熄屏，按 RESET 会重新亮。
- 115200 和 921600 下看到的乱码是同一份日志用错了波特率，不是故障。
- 授权信息存在 OTP 里（日志 `Authorization otp read succeeds`），普通烧录不会动它；但依然不要用 BKFIL 的「全擦」。
- 出厂固件的唤醒词：你好涂鸦 / 小智同学 / hey tuya / hi tuya。

## 工具

```bash
uv run --with pyserial python t5/serial_probe.py                       # 三个波特率各录 10 秒
uv run --with pyserial python t5/serial_probe.py monitor --seconds 20  # 460800 录 20 秒，存到 t5/logs/
```

`t5/mic_test/`：TuyaOpen 小程序，串口每 100 ms 打印一行麦克风音量条（未编译验证）。

## 烧录注意

NiceMCU 说明：**不要选「全擦」**，会擦掉授权和校准数据。出厂固件和资料：https://github.com/NiceMCU-01/NiceMCU-T5-2.8IPS
