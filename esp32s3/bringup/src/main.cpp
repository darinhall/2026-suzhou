// DeskBot 的脸 · 维可思 ESP32-S3 + 3.5″ 8 位并口屏（ST7796U）+ GT911
//
// 开机：画待机脸 → 连 WiFi → UDP 广播找中枢 → WebSocket（hello 带令牌）→ 按收到的 face 消息换表情。
// 触摸：连点两下 = 老板键（本地立即切换），其余触摸上报给中枢。串口 115200（板子下面那个 USB-C）。
// 文字屏（消息 / 行情 / 今天 / 天气）要中文字体，还没做：遇到会画待机脸 + 状态名。

#include <Arduino.h>
#include <Preferences.h>
#include <TAMC_GT911.h>
#include <TFT_eSPI.h>
#include <Wire.h>

#include "audio.h"
#include "demo_cards.h"
#include "net.h"
#include "screens.h"
#include "servotest.h"
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

// 中枢发来的消息：gesture 由这块板的两个舵机做；pose / torque 是旧的双板协议，忽略
static void onMessage(JsonDocument &d) {
  const char *t = d["t"] | "";
  if (!strcmp(t, "servo_rebase")) { servotest::rebaseYaw(d["deg"] | 10.0f); return; }   // 需要时再定一次基准
  if (!strcmp(t, "servo_test")) { servotest::run(); return; }
  if (!strcmp(t, "gesture")) {   // 中枢的提醒阶梯 / 问答表态：nod / shake / glance / look（不阻塞，loop() 里慢慢做）
    servotest::gesture(d["name"] | "", d["times"] | 1, d["amp"] | 0.0f, d["hold"] | 0.0f);
    return;
  }
  if (!strcmp(t, "servo_wiggle")) { servotest::wiggle(d["id"] | 1, d["times"] | 3); return; }
  if (!strcmp(t, "voice_calibrate")) { audio::calibrate(d["ms"] | 3000); return; }   // 换了环境：重新量背景音量
  if (!strcmp(t, "audio_test")) { audio::selfTest(); return; }   // 中枢 / 网页可以再跑一次音频自检
  if (!strcmp(t, "hello")) { audio::hello(d["vol"] | 0.15f); return; }
  if (!strcmp(t, "chime")) { audio::chime(d["vol"] | 0.08f); return; }
  if (!strcmp(t, "beep")) { audio::tone(d["freq"] | 880.0f, d["ms"] | 200, d["vol"] | 0.08f); return; }
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
  if (screens::handles(st)) {   // 文字屏
    const uint32_t t0 = millis();
    if (screens::show(st, card)) {
      ui::setText();
      Serial.printf("[face] %s 画好 %u ms（%s）\n", st, millis() - t0, screens::mode());
      JsonDocument sd;   // 告诉中枢（和模拟器）：我现在画的是什么，对不上时好排查
      sd["t"] = "shown";
      sd["state"] = st;
      sd["mode"] = screens::mode();
      sd["item"] = card["name"] | card["city"] | card["title"] | "";
      net::send(sd);
      return;
    }
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
  if (audio::begin()) audio::chime(0.08f);
  delay(1500);
  {   // 一次性：ID2（转头）重新定基准，做过就记在 NVS 里，以后开机不再做
    Preferences pr;
    pr.begin("deskbot", false);
    if (!pr.getBool("pitchBase", false)) { servotest::rebaseYaw(10); pr.putBool("pitchBase", true); }
    if (!pr.getBool("pitchBase3", false)) { servotest::rebaseYaw(3); pr.putBool("pitchBase3", true); }   // 10-31 再微调 +3°（同方向）
    if (!pr.getBool("pitchBaseM10", false)) { servotest::rebaseYaw(-10); pr.putBool("pitchBaseM10", true); }   // 11-01 往开机第一下的方向（位置减小）转 10°
    if (!pr.getBool("pitchBaseP20", false)) { servotest::rebaseYaw(20); pr.putBool("pitchBaseP20", true); }    // 11-01 方向反了：改往位置增大转 20°（相对 M10 之前净 +10°）
    pr.end();
  }
  servotest::wiggle(1, 1);   // 开机：两个舵机轮流在原位附近来回摆一下（ID1 ±20°、ID2 ±10°，30% 扭矩，摆完放松）
  servotest::wiggle(2, 1);
  delay(500);
  audio::calibrate(3000);   // 舵机和喇叭都停了以后，量 3 秒背景音量；之后超过它 4 倍才算有人说话

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
static uint32_t lastTouchAt = 0;   // 最近一次触摸：离线演示在触摸后让出 20 秒

static void offlineDemo(uint32_t now) {
  static uint32_t lastHub = 0, lastCard = 0;
  static int idx = 0;
  static bool running = false;
  if (net::connected()) { lastHub = now; running = false; return; }
  if (now - lastHub < 12000 || (lastTouchAt && now - lastTouchAt < 20000)) return;
  if (running && now - lastCard < 9000) return;
  running = true;
  lastCard = now;
  JsonDocument d;
  if (!deserializeJson(d, DEMO_CARDS[idx++ % DEMO_COUNT])) onMessage(d);
}

// 说话检测的反应：开始说话 → 点一下头 + 屏幕换成"在听"（紫色眼睛 + 声波）；说完 → 回到原来的屏
static void voiceTick(uint32_t now) {
  static ui::State before = ui::State::Idle;
  const int ev = audio::listenTick();
  if (ev == 1) {
    before = ui::current();
    ui::set(ui::State::Listening);
    servotest::nod();
  } else if (ev == 2) {
    if (before == ui::State::Text) { screens::redraw(); ui::setText(); }
    else ui::set(before == ui::State::Listening ? ui::State::Idle : before);
  }
  // 调试：右下角小条显示 背景 / 现在 / 倍数，每 200 ms 刷新（直接画在屏上，被整屏重画盖掉后下次再画）
  static uint32_t last = 0;
  if (now - last < 200 || audio::background() <= 0) return;
  last = now;
  const float bg = audio::background(), lv = audio::level(), r = lv / bg;
  const int x = 330, y = 303, w = 150, h = 17;
  tft.fillRect(x, y, w, h, TFT_BLACK);
  const int bw = 54, filled = min(bw, (int)(r / 8.0f * bw));   // 条：0–8 倍；白线 = 4 倍阈值
  tft.fillRect(x + 92, y + 5, filled, 7, r >= 4 ? TFT_ORANGE : TFT_DARKGREY);
  tft.drawFastVLine(x + 92 + bw / 2, y + 2, 13, TFT_WHITE);
  char b[24];
  snprintf(b, sizeof b, "%ldk %ldk x%d.%d", (long)(bg / 1000), (long)(lv / 1000), (int)r, (int)(r * 10) % 10);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.drawString(b, x + 3, y + 5, 1);
}

void loop() {
  const uint32_t now = millis();
  offlineDemo(now);
  serialInject();
  voiceTick(now);   // 按音量检测有没有人说话：说话时换"在听"的表情 + 点头；右下角显示实时音量
  net::loop();
  servotest::tick();   // 动作队列：到点就发下一步

  static bool wasTouched = false;
  static uint32_t lastRead = 0;
  static bool touchedNow = false;
  if (now - lastRead >= 20) { lastRead = now; tp.read(); touchedNow = tp.isTouched && tp.touches > 0; }   // 每 20 ms 读一次，不要空转刷 I2C
  const bool touched = touchedNow;
  if (touched && !wasTouched) {   // 刚按下
    lastTouchAt = now;
    ui::wake();                   // 玩球 / 睡觉时摸一下就醒
    int x, y;
    mapTouch(tp.points[0].x, tp.points[0].y, x, y);
    Serial.printf("[touch] 原始 %d,%d → 屏幕 %d,%d\n", tp.points[0].x, tp.points[0].y, x, y);
    JsonDocument detail;
    char code[16];
    if (screens::openRowAt(x, y, detail, code, sizeof code)) {   // 盯盘列表里点了一只股票：打开它的详情
      if (net::connected()) {   // 连着中枢：让中枢发带完整数据的详情（成交量、涨跌停价、20 日区间…），12 秒后自动回来
        JsonDocument od;
        od["t"] = "open";
        od["code"] = code;
        net::send(od);
      } else {
        onMessage(detail);      // 离线演示：用这一行自带的数据拼一张详情
      }
    } else net::sendTouch(x, y);   // 其他单击：上报中枢（场景里 = 下一项）
  }
  // 手势：单击 = 下一项；点自选里的一只股票 = 看详情；长按右上角 0.7 秒 = 简洁 ↔ 专业
  static uint32_t pressAt = 0;
  static bool fired = false;
  if (touched && !wasTouched) { pressAt = now; fired = false; }
  if (touched && !fired && pressAt && now - pressAt > 1200) {   // 长按左上角 1.2 秒 = 音频自检（响一声 + 20 秒麦克风电平表）
    int lx, ly;
    mapTouch(tp.points[0].x, tp.points[0].y, lx, ly);
    if (lx < 110 && ly < 70) { fired = true; Serial.println("[audio] 长按左上角：开始音频自检"); audio::selfTest(); }
  }
  if (touched && !fired && pressAt && now - pressAt > 700 && ui::isText()) {
    int lx, ly;
    mapTouch(tp.points[0].x, tp.points[0].y, lx, ly);
    if (lx > 380 && ly < 60) {
      fired = true;
      const char *next = !strcmp(screens::mode(), "simple") ? "pro" : "simple";
      screens::setMode(next);
      JsonDocument dd;
      dd["t"] = "display";
      dd["mode"] = next;
      net::send(dd);
      Serial.printf("[display] 长按右上角 → %s\n", next);
    }
  }
  wasTouched = touched;

  probeTouch(now);
  ui::tick(now);
}
