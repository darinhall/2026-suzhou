# 维可思 ESP32-S3 DEMO + 3.5″ 8 位并口屏（脸，备选方案）

> 2026-10-31 更新：拿到厂家资料包 v2.3，下面的引脚都是从里面的例程读出来的，不是猜的。

| | |
|---|---|
| 主板 | 维可思 ESP32-S3 DEMO V3.2，ESP32-S3-WROOM-1 **N16R8**（16 MB Flash、8 MB **八线** PSRAM，rev v0.2） |
| 串口 | 板子下面那个 USB-C 是芯片自带 USB（Mac 上是 `/dev/cu.usbmodem*`，**换线 / 换口端口名会变**，比如 1101 → 101）；上面那个是 USB-TTL 烧录口 |
| 屏 | 「TFT 3.5寸彩屏 V2.0」，320×480 竖屏原生，横过来用就是 480×320；驱动芯片 **ST7796U**（不是 ST7796S），**8 位并口**（模组上电阻选 8BIT 电容触摸） |
| 触摸 | **GT911**（不是 FT6336），I2C，地址 0x5D（备用 0x14），坐标系是竖屏 320×480 |
| 出厂固件 | PlatformIO + Arduino + TFT_eSPI 2.4.71 + LVGL v8 Widgets demo，33 FPS |

## 引脚（厂家 `Setup_myTFT_ST7796_parallel.h` 和 `lv_port_indev.h`）

| 屏幕（8 位并口） | GPIO | | 触摸（GT911） | GPIO |
|---|---|---|---|---|
| D0 … D7 | **1, 2, 7, 8, 3, 18, 17, 16** | | SDA | 42 |
| CS | 10 | | SCL | 41 |
| DC（= RS） | 9 | | INT | 40 |
| RST | 14 | | RST | 39 |
| WR | 15 | | | |
| RD | 6 | | | |
| 背光 BL | 4，**低电平点亮** | | | |

和板子背面 2×11 排母上的数字、和出厂固件开机日志里的触摸 I2C（`sda=42 scl=41`）都对得上。

## 方向

厂家例程用 `tft.setRotation(3)`（"横屏，翻转"）。我们的白色头盒里屏幕是转了 180° 装的，所以**出厂 demo 在头盒里是倒着的**（见 10-31 的照片）。要正着显示用 **`setRotation(1)`**。触摸坐标也要跟着转：厂家 rotation 3 的换算是 `x = 原始y, y = 319 − 原始x`，rotation 1 是 `x = 479 − 原始y, y = 原始x`（`bringup/src/main.cpp` 里是这么写的，还没在真机上验证）。

## 点亮测试：`bringup/`

PlatformIO 工程，开机依次：彩条 + 方向标记 → 设计系统的待机表情（会眨眼）→ 触摸（串口打印原始坐标和换算后的坐标，屏幕上画橙点）。

```bash
uvx --python 3.12 --from platformio pio run -d esp32s3/bringup                                          # 编译（第一次要下载工具链，几分钟）
uvx --python 3.12 --from platformio pio run -d esp32s3/bringup -t upload --upload-port /dev/cu.usbmodem101
uvx --python 3.12 --from platformio pio device monitor -b 115200 -p /dev/cu.usbmodem101
```

TFT_eSPI 不用库里的 `User_Setup.h`，引脚全部通过 `platformio.ini` 的 `build_flags` 传入（`-DUSER_SETUP_LOADED=1`）。工程路径里不要有中文。

## 厂家资料包

百度网盘 https://pan.baidu.com/s/1Fna4l82jTXC5Zeo87LtoWA 提取码 3333（wiki：http://wiki.waaax.cn/boards/ESP32/ESP32-LVGL%E5%BC%80%E5%8F%91%E6%9D%BF.html）。2.3 GB，里面有用的：

- `3.例程/PlatformIO/ESP32-S3-LVGL-PIO-PROJECT-TFT3.5-ST7796U-CPT.zip`：**我们这块屏**的完整例程（CPT = 电容触摸）
- `3.例程/IDF/IDF_ESP32-S3_8BIT_TFT3.5_GT911.zip`：同一块屏的 ESP-IDF 版本
- `2.原理图/TFT3.5_8BIT电容触摸屏原理图.pdf`、`ESP32_S3主控板原理图.pdf`
- `4.文档资料/YT350S006+电容触摸/`：屏幕规格书和 GT911 数据手册

注意：
- 压缩包里的文件名是 GBK 编码，macOS 自带的 `unzip` 解不了（会报 "Illegal byte sequence"，还会误报 "disk full"）。用 Python `zipfile` 读，文件名 `n.encode('cp437').decode('gbk')`。
- 厂家例程的 `test/3.测试电容触摸.cpp` 里触摸引脚写的是 SDA=1、INT=2，和屏幕数据线 D0、D1 冲突，那是旧的普通 ESP32 板的，**S3 上别用**；以 `lv_port_indev.h` 的 42/41/40/39 为准。
- 厂家 `lib/TFT_eSPI` 就是上游 2.4.71（和 2.4.72 只差一行 `writecommand(0x00)` 和一些 S2/S3 的 SPI 端口宏，对并口无关），所以我们直接用上游，不把整个库复制进仓库。

## 出厂固件备份 / 还原

备份在 `esp32s3/backup/factory_0x0_2MB.bin`（只在 Darin 电脑上，没进 git）。

```bash
uvx --from esptool esptool --port /dev/cu.usbmodem101 flash-id                              # 看芯片
uvx --from esptool esptool --port /dev/cu.usbmodem101 read-flash 0 0x200000 backup/factory_0x0_2MB.bin
uvx --from esptool esptool --port /dev/cu.usbmodem101 write-flash 0 backup/factory_0x0_2MB.bin   # 还原出厂 demo
```

## 固件 v2：联网的脸（10-31）

`bringup/` 现在会连 `NAMI-guest`，用 UDP 广播找到中枢，用令牌握手后接收 `face` 指令。

```bash
./hub/run.sh                      # 先起中枢，生成 hub/.token
python3 config/build_net.py       # 生成 config/deskbot_net_local.h（带令牌，已 gitignore）
uvx --python 3.12 --from platformio pio run -d esp32s3/bringup -t upload --upload-port /dev/cu.usbmodem101
```

状态：`idle blink happy listening thinking ok stealth play sleep`；安静 25 秒玩球，玩 12 秒后睡觉，摸一下就醒；连点两下 = 老板键。文字屏（今天 / 天气 / 行情）还要 CJK 字体，目前显示待机脸。

串口会打印 `[wifi]`、`[hub]`、`[ws]`。找不到 SSID（状态 1）时 12 秒后会扫描并列出板子看到的网络；信号 -70 dBm 偏弱，展台上把板子放在靠近路由的一侧。

## 外设接线（10-31 晚）

| 外设 | 信号 | GPIO |
|---|---|---|
| MAX98357A 喇叭功放 | BCLK / LRC / DIN | 12 / 13 / 11（和麦克风共用 BCLK、WS） |
| INMP441 麦克风 | SCK / WS / SD | 12 / 13 / 38（L/R 接地，VDD 3.3 V） |
| 飞特 STS3215-12V × 2（串联） | TX / RX | 21 / 47（经 ~3.3 kΩ / ~5 kΩ 接 DATA；**115200 波特**；ID1 偏航、ID2 俯仰） |

分区：`partitions.csv`（4 MB 程序，没有 OTA；`fonts` 分区 0x410000 起约 11.9 MB 放中文字体，固件 mmap 成数组读）。屏幕颜色有一层校正（`src/palette.h`）。

完整说明（接线、排针位置、舵机基准、语音、网络）见仓库根目录 [《开发交接》](../开发交接.md)。
