// DeskBot · 维可思 ESP32-S3 + 3.5″ 8 位并口屏 · 点亮测试
//
// 开机依次：
//   1. 彩条 R G B W + 四角的方向标记（用来确认颜色没反、方向是正的）
//   2. 设计系统的待机表情：暖灰底、两只墨色胶囊眼睛（会眨）、橙色嘴
//   3. 触摸：串口打印 GT911 的原始坐标和换算后的屏幕坐标，屏幕上在触摸点画一个橙点
//
// 串口（板子下面那个 USB-C）：115200。尺寸和颜色照 sim/screen.css 的 3.5″ 480×320（light 主题）。

#include <Arduino.h>
#include <Wire.h>
#include <TFT_eSPI.h>
#include <TAMC_GT911.h>

#ifndef SCREEN_ROTATION
#define SCREEN_ROTATION 1
#endif

// 触摸引脚：厂家 lv_port_indev.h。GT911 的坐标系是竖屏 320×480
#define TOUCH_SDA 42
#define TOUCH_SCL 41
#define TOUCH_INT 40
#define TOUCH_RST 39

// 设计系统（light）
#define GROUND 0xE9E9E6
#define INK    0x121212
#define ACCENT 0xFF5B14

TFT_eSPI tft;
TAMC_GT911 tp(TOUCH_SDA, TOUCH_SCL, TOUCH_INT, TOUCH_RST, 320, 480);

static uint16_t C(uint32_t hex) { return tft.color565((hex >> 16) & 255, (hex >> 8) & 255, hex & 255); }

// ---------- 1. 测试图 ----------
static void testPattern() {
  const int w = tft.width(), h = tft.height();
  const uint16_t cols[4] = {TFT_RED, TFT_GREEN, TFT_BLUE, TFT_WHITE};
  const char *names[4] = {"R", "G", "B", "W"};
  for (int i = 0; i < 4; i++) {
    tft.fillRect(i * w / 4, 0, w / 4, h, cols[i]);
    tft.setTextColor(i == 3 ? TFT_BLACK : TFT_WHITE);
    tft.drawCentreString(names[i], i * w / 4 + w / 8, h / 2 - 13, 4);
  }
  tft.setTextColor(TFT_BLACK, TFT_WHITE);
  tft.drawString("TOP-LEFT", 6, 6, 2);                          // 倒着放的话这行字会是倒的
  tft.drawRightString("BOTTOM-RIGHT", w - 6, h - 22, 2);
  tft.drawString(String(w) + "x" + String(h) + " rot=" + String(SCREEN_ROTATION), 6, h - 22, 2);
}

// ---------- 2. 表情（3.5″ 的尺寸：眼睛 64×112，间距 104，嘴 28×7 在 y=242） ----------
static const int EYE_W = 64, EYE_H = 112, EYE_GAP = 104, MOUTH_W = 28, MOUTH_H = 7;

static void drawEyes(bool shut) {
  const int cx = tft.width() / 2, cy = tft.height() / 2 - 4;
  const int top = cy - EYE_H / 2;
  tft.fillRect(0, top - 4, tft.width(), EYE_H + 8, C(GROUND));   // 只擦眼睛那一条，眨眼不闪全屏
  const int eh = shut ? 8 : EYE_H;
  const int r = min(EYE_W / 2, eh / 2);
  tft.fillRoundRect(cx - EYE_GAP / 2 - EYE_W, cy - eh / 2, EYE_W, eh, r, C(INK));
  tft.fillRoundRect(cx + EYE_GAP / 2, cy - eh / 2, EYE_W, eh, r, C(INK));
}

static void drawFace() {
  tft.fillScreen(C(GROUND));
  drawEyes(false);
  tft.fillRoundRect(tft.width() / 2 - MOUTH_W / 2, 242, MOUTH_W, MOUTH_H, 3, C(ACCENT));
}

// ---------- 3. 触摸 ----------
// GT911 是竖屏 320×480；横屏时要换算。厂家在 rotation 3 的做法：x = 原始 y，y = 319 − 原始 x。
// rotation 1 是转 180°：x = 479 − 原始 y，y = 原始 x。如果触摸点和手指对不上，看串口里的原始值改这里。
static void mapTouch(int rx, int ry, int &x, int &y) {
#if SCREEN_ROTATION == 3
  x = ry;
  y = 319 - rx;
#else
  x = 479 - ry;
  y = rx;
#endif
}

static void i2cReport() {
  for (uint8_t addr : {0x5D, 0x14}) {
    Wire.beginTransmission(addr);
    Serial.printf("[touch] I2C 0x%02X: %s\n", addr, Wire.endTransmission() == 0 ? "有应答（GT911 在这）" : "没有");
  }
}

void setup() {
  Serial.begin(115200);
  delay(400);
  Serial.printf("\n[deskbot] 启动 · PSRAM %u KB · 空闲堆 %u KB · 屏幕方向 %d\n", ESP.getPsramSize() / 1024, ESP.getFreeHeap() / 1024, SCREEN_ROTATION);

  tft.init();
  tft.setRotation(SCREEN_ROTATION);
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, LOW);                     // 背光低电平点亮
  Serial.printf("[tft] 初始化完成：%d × %d\n", tft.width(), tft.height());

  testPattern();
  delay(2500);

  tp.begin();
  tp.setRotation(ROTATION_NORMAL);
  i2cReport();

  drawFace();
  Serial.println("[deskbot] 表情已画出；眨眼中，摸一下屏幕试试");
}

void loop() {
  static uint32_t nextBlink = 3000, dotClearAt = 0, lastPrint = 0;
  const uint32_t now = millis();

  if (now >= nextBlink) {
    drawEyes(true);
    delay(120);
    drawEyes(false);
    nextBlink = millis() + 2500 + random(0, 3500);
  }

  tp.read();
  if (tp.isTouched && tp.touches > 0) {
    int x, y;
    mapTouch(tp.points[0].x, tp.points[0].y, x, y);
    if (now - lastPrint > 150) {
      Serial.printf("[touch] 原始 (%d, %d) → 屏幕 (%d, %d)\n", tp.points[0].x, tp.points[0].y, x, y);
      lastPrint = now;
    }
    tft.fillCircle(x, y, 9, C(ACCENT));
    dotClearAt = now + 900;
  } else if (dotClearAt && now > dotClearAt) {
    dotClearAt = 0;
    drawFace();                                  // 擦掉触摸点
  }
}
