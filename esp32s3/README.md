# 维可思 ESP32-S3 DEMO + 3.5″ 8 位并口屏（脸，备选方案）

| | |
|---|---|
| 主板 | 维可思 ESP32-S3 DEMO V3.2，ESP32-S3-WROOM-1 **N16R8**（16 MB Flash、8 MB PSRAM，rev v0.2） |
| 串口 | 下面那个 USB-C 是芯片自带 USB → Mac 上是 `/dev/cu.usbmodem*`；上面那个是 USB-TTL 烧录口 |
| 屏 | 「TFT 3.5寸彩屏 V2.0」，320×480 竖屏原生，**ST7796S**，**8 位并口**（模组上的电阻选择表：8BIT 电容触摸） |
| 触摸 | FT6336U，I2C 地址 0x38，SDA 42 / SCL 41 |
| 出厂固件 | PlatformIO + Arduino + TFT_eSPI + LVGL v8 Widgets demo，33 FPS |
| 安装方向 | **屏在头盒里装反了 180°**（出厂 demo 是倒着显示的）：TFT_eSPI 用 `setRotation(3)` 而不是 `1` |
| 屏幕引脚 | **还不知道**：在厂家资料包里（例程 `ESP32-LVGL-PIO-PROJECT-TFT3.5-ST7796S` 的 TFT_eSPI User_Setup） |
| 资料包 | 百度网盘 https://pan.baidu.com/s/1Fna4l82jTXC5Zeo87LtoWA 提取码 3333（wiki：http://wiki.waaax.cn/boards/ESP32/ESP32-LVGL%E5%BC%80%E5%8F%91%E6%9D%BF.html） |

## 出厂固件备份 / 还原

备份在 `esp32s3/backup/factory_0x0_2MB.bin`（只在 Darin 电脑上，没进 git）。

```bash
uvx --from esptool esptool --port /dev/cu.usbmodem1101 flash-id                              # 看芯片
uvx --from esptool esptool --port /dev/cu.usbmodem1101 read-flash 0 0x200000 backup/factory_0x0_2MB.bin
uvx --from esptool esptool --port /dev/cu.usbmodem1101 write-flash 0 backup/factory_0x0_2MB.bin   # 还原出厂 demo
```
