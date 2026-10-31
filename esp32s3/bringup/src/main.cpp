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

// 语音状态（voiceTick / onMessage 都要用）
static ui::State voiceBefore = ui::State::Idle;
static uint32_t waitReplyUntil = 0;   // 等中枢回话：超时就自己回到原来的屏

static void restoreFace() {
  waitReplyUntil = 0;
  if (voiceBefore == ui::State::Text) { screens::redraw(); ui::setText(); }
  else ui::set(voiceBefore == ui::State::Listening || voiceBefore == ui::State::Thinking ? ui::State::Idle : voiceBefore);
}

// 喇叭：中枢发 spk_start → 若干二进制帧（μ-law）→ spk_end。边收边放：攒够 0.4 秒就开始放，loop() 里一点点往 I2S 塞
static int16_t *spkBuf = nullptr;
static size_t spkN = 0, spkPos = 0, spkCap = 0;
static bool spkOn = false, spkEnded = false, spkPlaying = false, spkUlaw = true;
static float spkVol = 0.4f;   // 11-01：0.2 → 0.4（音量翻倍）
static const size_t SPK_PREROLL = 16000 * 4 / 10;
static bool micStreaming = false;   // 正在边说边传

// 中枢发来的消息：gesture 由这块板的两个舵机做；pose / torque 是旧的双板协议，忽略
static void onBinary(const uint8_t *data, size_t n);

static void onMessage(JsonDocument &d) {
  const char *t = d["t"] | "";
  if (!strcmp(t, "face")) waitReplyUntil = 0;   // 中枢的回答（卡片）到了：不再等，别被超时改回去
  if (!strcmp(t, "servo_rebase")) { servotest::rebaseYaw(d["deg"] | 10.0f); return; }   // 需要时再定一次基准
  if (!strcmp(t, "servo_test")) { servotest::run(); return; }
  if (!strcmp(t, "servo_pos")) { servotest::reportPos(); return; }          // 只读：现在的位置和基准
  if (!strcmp(t, "servo_home_set")) { servotest::setHomeHere(); return; }   // 现在的位置 = 新基准
  if (!strcmp(t, "servo_home")) { servotest::goHome(); return; }            // 走回基准
  if (!strcmp(t, "gesture")) {   // 中枢的提醒阶梯 / 问答表态：nod / shake / glance / look（不阻塞，loop() 里慢慢做）
    servotest::gesture(d["name"] | "", d["times"] | 1, d["amp"] | 0.0f, d["hold"] | 0.0f);
    return;
  }
  if (!strcmp(t, "servo_wiggle")) { servotest::wiggle(d["id"] | 1, d["times"] | 3); return; }
  if (!strcmp(t, "voice_calibrate")) { audio::calibrate(d["ms"] | 3000); return; }   // 换了环境：重新量背景音量
  if (!strcmp(t, "audio_test")) { audio::selfTest(); return; }   // 中枢 / 网页可以再跑一次音频自检
  if (!strcmp(t, "hello")) { audio::hello(d["vol"] | 0.15f); return; }
  if (!strcmp(t, "spk_start")) {   // 中枢要说话：准备收音频（边收边放）
    if (!spkBuf) { spkCap = 16000 * 20; spkBuf = (int16_t *)ps_malloc(spkCap * 2); }   // 最长 20 秒
    spkN = spkPos = 0; spkOn = spkBuf != nullptr; spkEnded = spkPlaying = false;
    spkVol = d["vol"] | 0.4f;
    spkUlaw = !strcmp(d["fmt"] | "ulaw", "ulaw");
    waitReplyUntil = 0;
    return;
  }
  if (!strcmp(t, "spk_end")) { spkEnded = true; return; }   // 收齐了：放完剩下的就结束
  if (!strcmp(t, "spk_stop")) { spkEnded = true; spkN = spkPos; return; }
  if (!strcmp(t, "listen_done")) { restoreFace(); return; }   // 没听清 / 不是对我说的：回到原来的屏，不动
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
    if (!pr.getBool("yawBaseM20", false)) { servotest::rebaseYaw(-20); pr.putBool("yawBaseM20", true); }        // 11-01 ID2 是横向转头：归位 −20°（相对今天早上净 −10°）
    pr.end();
  }
  servotest::wiggle(1, 1);   // 开机：两个舵机轮流在原位附近来回摆一下（ID1 ±20°、ID2 ±10°，30% 扭矩，摆完放松）
  servotest::wiggle(2, 1);
  delay(500);
  audio::calibrate(3000);   // 舵机和喇叭都停了以后，量 3 秒背景音量；之后超过它 4 倍才算有人说话

  tp.begin();
  tp.setRotation(ROTATION_NORMAL);

  net::begin(onMessage);
  net::onBinary(onBinary);   // 中枢下发的语音
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

// ---------- 语音 ----------
// 说话：确认是一句话（有声 ≥ 0.6 秒）→ 屏幕换"在听"（不动）；说完 → 整句传给中枢（mic_start + 二进制 + mic_end）→ "想一想"。
// 中枢识别出一句完整的命令才会回卡片、动作、语音；没听清 / 不是对我说的 → listen_done，回到原来的屏。噪音不会让它动。
// 边说边传：确认是一句话后发 mic_start，之后每攒够 4000 个样本（0.25 秒，μ-law 4000 字节）发一帧，说完把剩下的发掉
static void micPump(bool final) {
  static uint8_t chunk[4000];
  static int have = 0;
  for (;;) {
    have += audio::takeUlaw(chunk + have, sizeof chunk - have);
    if (have == (int)sizeof chunk || (final && have > 0)) { net::sendBin(chunk, have); have = 0; continue; }
    break;
  }
}

static void onBinary(const uint8_t *data, size_t n) {
  if (!spkOn || !spkBuf) return;
  if (spkUlaw) {
    const size_t k = min(n, spkCap - spkN);
    for (size_t i = 0; i < k; i++) spkBuf[spkN + i] = audio::ulawDec(data[i]);
    spkN += k;
  } else {
    const size_t k = min(n / 2, spkCap - spkN);
    memcpy(spkBuf + spkN, data, k * 2);
    spkN += k;
  }
}

static void speakerTick() {
  if (!spkOn) return;
  if (!spkPlaying) {
    if (spkN - spkPos < SPK_PREROLL && !spkEnded) return;   // 先攒 0.4 秒，网络慢也不断断续续
    spkPlaying = true;
    audio::streamBegin();
    Serial.printf("[spk] 开始放（已收到 %u ms）\n", (unsigned)(spkN / 16));
  }
  for (int i = 0; i < 4 && spkPos < spkN; i++) spkPos += audio::streamWrite(spkBuf + spkPos, spkN - spkPos, spkVol);
  if (spkEnded && spkPos >= spkN) {
    spkOn = spkPlaying = false;
    audio::streamEnd();
    Serial.printf("[spk] 放完 %u ms\n", (unsigned)(spkN / 16));
  }
}

static void voiceTick(uint32_t now) {
  if (waitReplyUntil && (int32_t)(now - waitReplyUntil) > 0) restoreFace();
  const int ev = audio::listenTick();
  if (ev == 1) {   // 确认是一句话：换"在听"，开始边说边传
    if (!waitReplyUntil) voiceBefore = ui::current();
    ui::set(ui::State::Listening);
    micStreaming = net::connected();
    if (micStreaming) {
      JsonDocument d;
      d["t"] = "mic_start"; d["sr"] = 16000; d["fmt"] = "ulaw"; d["trigger"] = "vad";
      net::send(d);
    }
  } else if (ev == 2) {   // 说完了：发剩下的 + mic_end，换"想一想"，一直等到中枢回话
    if (micStreaming) {
      micPump(true);
      JsonDocument e;
      e["t"] = "mic_end";
      net::send(e);
      ui::set(ui::State::Thinking);
      waitReplyUntil = millis() + 15000;
    } else {
      restoreFace();
    }
    micStreaming = false;
  }
  if (micStreaming) micPump(false);
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
  voiceTick(now);   // 按音量检测一句话：边说边传给中枢；右下角显示实时音量
  speakerTick();    // 中枢下发的语音：边收边放
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
