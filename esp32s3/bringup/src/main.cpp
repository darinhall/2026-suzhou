// DeskBot 的脸 · 维可思 ESP32-S3 + 3.5″ 8 位并口屏（ST7796U）+ GT911
//
// 开机：画待机脸 → 连 WiFi → UDP 广播找中枢 → WebSocket（hello 带令牌）→ 按收到的 face 消息换表情。
// 触摸：连点两下 = 老板键（本地立即切换），其余触摸上报给中枢。串口 115200（板子下面那个 USB-C）。
// 文字屏（消息 / 行情 / 今天 / 天气）要中文字体，还没做：遇到会画待机脸 + 状态名。

#include <Arduino.h>
#include <TAMC_GT911.h>
#include <TFT_eSPI.h>
#include <Wire.h>

#include "demo_cards.h"
#include "net.h"
#include "screens.h"
#include "ui.h"

#ifndef SCREEN_ROTATION
#define SCREEN_ROTATION 1
#endif

// 触摸引脚来自厂家 lv_port_indev.h。GT911 的坐标系是竖屏 320×480
#define TOUCH_SDA 42
#define TOUCH_SCL 41
#define TOUCH_INT 40
#define TOUCH_RST 39

TFT_eSPI tft;
TAMC_GT911 tp(TOUCH_SDA, TOUCH_SCL, TOUCH_INT, TOUCH_RST, 320, 480);

// 横屏时的坐标换算：rotation 1 = 厂家 rotation 3 转 180°（真机验证过，手指和位置对得上）
static void mapTouch(int rx, int ry, int &x, int &y) {
#if SCREEN_ROTATION == 3
  x = ry;
  y = 319 - rx;
#else
  x = 479 - ry;
  y = rx;
#endif
}

// 中枢发来的消息：这块板只管脸，pose / gesture / torque 之类给身体的直接忽略
static void onMessage(JsonDocument &d) {
  const char *t = d["t"] | "";
  if (!strcmp(t, "display")) {   // 显示模式：简洁 / 紧凑 / 专业（中枢存着，新连上也会收到一条）
    screens::setMode(d["mode"] | "pro");
    return;
  }
  if (!strcmp(t, "scene_state")) {   // 状态条右边的页码点和回放时钟
    screens::setScene(d["name"] | "", d["page"] | 0, d["of"] | 0, d["clock"] | "");
    return;
  }
  if (strcmp(t, "face") != 0) return;
  const char *st = d["state"] | "idle";
  JsonVariantConst card = d["card"];
  if (screens::handles(st)) {   // 盯盘 / 单股 / 起床后：整屏文字屏
    const uint32_t t0 = millis();
    if (screens::show(st, card)) { ui::setText(); Serial.printf("[face] %s 画好 %u ms\n", st, millis() - t0); return; }
  }
  Serial.printf("[face] %s\n", st);

  if (!strcmp(st, "idle")) ui::set(ui::State::Idle);
  else if (!strcmp(st, "blink")) ui::set(ui::State::Blink, card["count"] | 1);
  else if (!strcmp(st, "happy")) ui::set(ui::State::Happy);
  else if (!strcmp(st, "listening")) ui::set(ui::State::Listening);
  else if (!strcmp(st, "thinking")) ui::set(ui::State::Thinking);
  else if (!strcmp(st, "ok")) ui::set(ui::State::Ok);
  else if (!strcmp(st, "stealth")) ui::set(ui::State::Stealth, 0, card["pct"] | 0.0f, card["vol"] | 0.3f, card["alert"] | false);
  else if (!strcmp(st, "play")) ui::set(ui::State::Play);
  else if (!strcmp(st, "sleep")) ui::set(ui::State::Sleep);
  else if (!strcmp(st, "decoy")) ui::setBoss(true);
  else ui::set(ui::State::Unsupported, 0, 0, 0, false, st);
}

void setup() {
  Serial.setRxBufferSize(8192);   // 串口注入整张卡片（1–3 KB）；默认只有 256 字节
  Serial.begin(115200);
  delay(400);
  Serial.printf("\n[deskbot] 启动 · PSRAM %u KB · 空闲堆 %u KB\n", ESP.getPsramSize() / 1024, ESP.getFreeHeap() / 1024);

  tft.init();
  tft.setRotation(SCREEN_ROTATION);
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, LOW);   // 背光低电平点亮
  ui::begin(&tft);
  screens::begin(&tft);

  tp.begin();
  tp.setRotation(ROTATION_NORMAL);

  net::begin(onMessage);
  const esp_reset_reason_t rr = esp_reset_reason();
  char bm[64];
  snprintf(bm, sizeof bm, "开机 fw 0.2.0 · PSRAM %u KB · 复位原因 %d", ESP.getPsramSize() / 1024, (int)rr);
  net::log("info", "BOOT", bm);
}

// 触摸屏每 10 秒探一次 I2C：没应答 = 排线松了 / 屏坏了
static void probeTouch(uint32_t now) {
  static uint32_t last = 0;
  static bool ok = true;
  if (now - last < 10000) return;
  last = now;
  Wire.beginTransmission(0x5D);
  const bool alive = Wire.endTransmission() == 0;
  if (alive != ok) {
    ok = alive;
    if (!alive) net::log("error", "TOUCH_I2C_ERR", "触摸芯片 GT911 没有应答：检查屏幕排线");
    else net::log("info", "TOUCH_OK", "触摸芯片恢复应答");
  }
}

// 串口里发一行 JSON（和中枢发来的消息一样）也能让屏幕换内容：没有 WiFi 时调试 / 现场备用
static void serialInject() {
  static String line;
  while (Serial.available()) {
    const char ch = Serial.read();
    if (ch == '\n') {
      JsonDocument d;
      const auto err = line.length() > 1 ? deserializeJson(d, line) : DeserializationError::EmptyInput;
      Serial.printf("[serial] 收到 %u 字节：%s\n", (unsigned)line.length(), err.c_str());
      if (!err) onMessage(d);
      line = "";
    } else if (line.length() < 6000) line += ch;
  }
}

// 离线演示：开机 25 秒还没连上中枢（或之后断线 25 秒），就循环显示内置的示例卡片（带「示例」标记），连上中枢后立刻让位
static void offlineDemo(uint32_t now) {
  static uint32_t lastHub = 0, lastCard = 0;
  static int idx = 0;
  static bool running = false;
  if (net::connected()) { lastHub = now; running = false; return; }
  if (now - lastHub < 25000 || ui::boss()) return;
  if (running && now - lastCard < 9000) return;
  running = true;
  lastCard = now;
  JsonDocument d;
  if (!deserializeJson(d, DEMO_CARDS[idx++ % DEMO_COUNT])) onMessage(d);
}

void loop() {
  const uint32_t now = millis();
  offlineDemo(now);
  serialInject();
  net::loop();

  static bool wasTouched = false;
  static uint32_t lastTap = 0;
  static uint32_t lastRead = 0;
  static bool touchedNow = false;
  if (now - lastRead >= 20) { lastRead = now; tp.read(); touchedNow = tp.isTouched && tp.touches > 0; }   // 每 20 ms 读一次，不要空转刷 I2C
  const bool touched = touchedNow;
  if (touched && !wasTouched) {   // 刚按下
    ui::wake();                   // 玩球 / 睡觉时摸一下就醒
    int x, y;
    mapTouch(tp.points[0].x, tp.points[0].y, x, y);
    if (now - lastTap < 350) {    // 连点两下：老板键
      ui::setBoss(!ui::boss());
      net::sendBoss(ui::boss());
      Serial.printf("[boss] %s\n", ui::boss() ? "开" : "关");
    } else if (x > 380 && y < 44 && ui::isText()) {   // 点右上角：简洁 ↔ 专业
      const char *next = !strcmp(screens::mode(), "simple") ? "pro" : "simple";
      screens::setMode(next);
      JsonDocument dd;
      dd["t"] = "display";
      dd["mode"] = next;
      net::send(dd);
    } else {
      net::sendTouch(x, y);
    }
    lastTap = now;
  }
  wasTouched = touched;

  probeTouch(now);
  ui::tick(now);
}
