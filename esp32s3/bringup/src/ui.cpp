#include "ui.h"
#include <time.h>

namespace ui {

static TFT_eSPI *T;

// 设计系统 light 色板
static const uint32_t GROUND = 0xE9E9E6, INK = 0x121212, MUTED = 0x5F5F5C, ACCENT = 0xFF5B14, LILAC = 0x9B7EF0, UPC = 0xC8281E, ON_INK = 0xF5F5F3;
static const uint32_t SURFACE = 0xF5F5F3, RULE = 0xC9C9C4;
static const int EYE_W = 64, EYE_H = 112, EYE_GAP = 104, MOUTH_W = 28, MOUTH_H = 7;
static const uint32_t IDLE_AFTER = 25000, PLAY_FOR = 12000;   // 安静 25 秒玩球，玩 12 秒去睡（和 sim 一样）

static uint16_t C(uint32_t h) { return T->color565((h >> 16) & 255, (h >> 8) & 255, h & 255); }
static uint16_t mix(uint32_t a, uint32_t b, float t) {   // a → b，t 0..1（TFT 读不了像素，没法做半透明，所以预先混好）
  auto ch = [&](int sh) { return (int)(((a >> sh) & 255) * (1 - t) + ((b >> sh) & 255) * t); };
  return T->color565(ch(16), ch(8), ch(0));
}

static State cur = State::Idle;
static int cnt = 0;
static float pct = 0, vol = 0.3f;
static bool alertFlag = false, bossOn = false;
static char label[24] = "";
static uint32_t nextBlink = 3000, lastAnim = 0, winkUntil = 0, lastClock = 0, lastActive = 0, stateSince = 0;

static int W() { return T->width(); }
static int H() { return T->height(); }
static int cy() { return H() / 2 - 4; }

// ---------- 基本部件 ----------
static void eyesPill(uint32_t color, int eh, int dx = 0, int dy = 0, bool rightOnly = false) {
  const int cx = W() / 2 + dx, y = cy() + dy;
  const int r = min(EYE_W / 2, eh / 2);
  if (!rightOnly) T->fillRoundRect(cx - EYE_GAP / 2 - EYE_W, y - eh / 2, EYE_W, eh, r, C(color));
  T->fillRoundRect(cx + EYE_GAP / 2, y - eh / 2, EYE_W, eh, r, C(color));
}

static void eyesArc(uint32_t color) {   // 眯眼笑：上半圈
  const int cx = W() / 2, top = cy() - 21;
  for (int i = 0; i < 2; i++) {
    const int x = i == 0 ? cx - EYE_GAP / 2 - EYE_W : cx + EYE_GAP / 2;
    T->fillRoundRect(x, top, EYE_W, 72, 32, C(color));
    T->fillRoundRect(x + 14, top + 14, EYE_W - 28, 60, 18, C(GROUND));
    T->fillRect(x - 1, top + 42, EYE_W + 2, 40, C(GROUND));   // 切掉下半
  }
}

static void eyeBand() { T->fillRect(0, cy() - EYE_H / 2 - 6, W(), EYE_H + 12, C(GROUND)); }
static void mouth() { T->fillRoundRect(W() / 2 - MOUTH_W / 2, 242, MOUTH_W, MOUTH_H, 3, C(ACCENT)); }

static void waves(uint32_t now) {
  T->fillRect(W() / 2 - 70, H() - 62, 140, 44, C(GROUND));
  for (int i = 0; i < 6; i++) {
    const float h = 8 + 26 * (0.5f + 0.5f * sinf(now / 170.0f + i * 0.9f));
    T->fillRoundRect(W() / 2 - 66 + i * 24, H() - 40 - (int)h / 2, 12, (int)h, 5, C(LILAC));
  }
}

static void dots(uint32_t now) {
  T->fillRect(W() / 2 - 40, H() - 56, 80, 24, C(GROUND));
  for (int i = 0; i < 3; i++) {
    const float a = 0.25f + 0.75f * (0.5f + 0.5f * sinf(now / 190.0f - i * 1.1f));
    T->fillCircle(W() / 2 - 26 + i * 26, H() - 44, 6, mix(GROUND, LILAC, a));
  }
}

static void badge() {
  const int x = W() - 40, y = 40;
  T->fillCircle(x, y, 24, C(ACCENT));
  T->setTextColor(C(INK), C(ACCENT));
  T->drawCentreString(String(cnt), x, y - 13, 4);
}

static void check() {
  const int cx = W() / 2, y = cy() - 6;
  T->fillCircle(cx, y, 56, C(INK));
  for (int o = -4; o <= 4; o++) {   // 粗线：多画几条平行线
    T->drawLine(cx - 26, y - 2 + o, cx - 8, y + 18 + o, C(ON_INK));
    T->drawLine(cx - 8, y + 18 + o, cx + 28, y - 24 + o, C(ON_INK));
    T->drawLine(cx - 26 + o, y - 2, cx - 8 + o, y + 18, C(ON_INK));
    T->drawLine(cx - 8 + o, y + 18, cx + 28 + o, y - 24, C(ON_INK));
  }
}

// ---------- 摸鱼模式：只有眼睛，涨跌用眼皮和脸红表示（和 sim 的 updateStealth 一致） ----------
static void stealth() {
  const float lid = pct <= -2 ? 0.45f : pct < -0.5f ? 0.25f : 0;
  const float blush = pct >= 2 ? 1.0f : pct > 0.5f ? (pct - 0.5f) / 1.5f * 0.6f : 0;
  eyeBand();
  if (pct >= 2) {
    eyesArc(INK);
  } else {
    eyesPill(INK, EYE_H);
    if (lid > 0) {   // 眼皮：盖住眼睛上面一截
      const int cx = W() / 2, top = cy() - EYE_H / 2, lh = (int)(EYE_H * lid);
      T->fillRect(cx - EYE_GAP / 2 - EYE_W - 2, top - 2, EYE_W + 4, lh + 2, C(GROUND));
      T->fillRect(cx + EYE_GAP / 2 - 2, top - 2, EYE_W + 4, lh + 2, C(GROUND));
    }
  }
  const uint16_t b = mix(GROUND, UPC, 0.45f * blush);
  T->fillRect(0, 205, W(), 40, C(GROUND));
  if (blush > 0.02f) {
    T->fillEllipse(144, 223, 32, 9, b);
    T->fillEllipse(W() - 144, 223, 32, 9, b);
  }
}

// ---------- 老板键：办公助手时钟 ----------
static int clockMin = -1;   // 屏幕上现在显示的分钟；-1 = 还没画

// 只有分钟变了才重画，而且只重画数字那一块；以前每秒整屏清一次，所以每秒闪一下
static void clockFace(bool full) {
  struct tm tm;
  char hh[3] = "--", mm[4] = ":--";
  int minute = -2;
  if (getLocalTime(&tm, 0) && tm.tm_year > 120) { snprintf(hh, sizeof hh, "%02d", tm.tm_hour); snprintf(mm, sizeof mm, ":%02d", tm.tm_min); minute = tm.tm_hour * 60 + tm.tm_min; }
  if (!full && minute == clockMin) return;
  clockMin = minute;
  if (full) T->fillScreen(C(GROUND));
  T->setTextDatum(TL_DATUM);
  const int wh = T->textWidth("00", 8), wm = T->textWidth(":00", 8), x0 = (W() - wh - wm) / 2, y0 = H() / 2 - 38;   // 用固定宽度排版，数字变了位置也不动
  if (!full) T->fillRect(x0 - 4, y0 - 4, wh + wm + 8, 8 * 8 + 24, C(GROUND));
  T->setTextColor(C(INK), C(GROUND));
  T->drawString(hh, x0, y0, 8);
  T->setTextColor(C(MUTED), C(GROUND));
  T->drawString(mm, x0 + wh, y0, 8);
}

// ---------- 待机小动画 ----------
// 玩球：橙色小球重力 + 反弹，眼睛跟着它（小球是这一屏的 accent，所以不画嘴）
static const int BALL_R = 20;
static float bx, by, bvx, bvy, bsq;
static uint32_t bLast;
static int gazeX = 0, gazeY = 0;

// 不直接在屏幕上"擦了再画"（会闪）：每帧把球附近的一块方形区域在 sprite 里画好（底色、眼睛、图标、球），一次推上屏。
static TFT_eSprite *ballSpr = nullptr, *eyeSpr = nullptr;
static const int BS = 128;                 // 球的 sprite 边长：装得下球（压扁时宽 54）加一帧的位移
static const int EW = 144, EH = 192;       // 单只眼睛的 sprite
static int obx, oby;                       // 上一帧球心

static int eyeBoxX(int i) { return W() / 2 + (i == 0 ? -EYE_GAP / 2 - EYE_W : EYE_GAP / 2) - (EW - EYE_W) / 2; }
static int eyeBoxY() { return cy() - EH / 2; }

static void drawEyesInto(TFT_eSPI &g, int ox, int oy) {
  const int r = EYE_W / 2;
  for (int i = 0; i < 2; i++) {
    const int x = W() / 2 + gazeX + (i == 0 ? -EYE_GAP / 2 - EYE_W : EYE_GAP / 2);
    g.fillRoundRect(x - ox, cy() + gazeY - EYE_H / 2 - oy, EYE_W, EYE_H, r, C(INK));
  }
}

static void drawBallInto(TFT_eSPI &g, int ox, int oy) {
  const float sx = 1 + 0.35f * bsq, sy = 1 - 0.35f * bsq;
  const int rx = (int)(BALL_R * sx), ry = (int)(BALL_R * sy);
  g.fillEllipse((int)bx - ox, (int)by + (BALL_R - ry) - oy, rx, ry, C(ACCENT));
}

static void composeAndPush(TFT_eSprite *sp, int x, int y, int w, int h, bool withBall) {
  sp->fillSprite(C(GROUND));
  drawEyesInto(*sp, x, y);
  if (withBall) drawBallInto(*sp, x, y);
  sp->pushSprite(x, y);
}

static void pushBall() {
  const int cxm = ((int)bx + obx) / 2, cym = ((int)by + oby) / 2;
  const int x = constrain(cxm - BS / 2, 0, W() - BS), y = constrain(cym - BS / 2, 0, H() - BS);
  composeAndPush(ballSpr, x, y, BS, BS, true);
  obx = (int)bx; oby = (int)by;
}

static void pushEyes(bool withBall = true) {
  for (int i = 0; i < 2; i++) composeAndPush(eyeSpr, eyeBoxX(i), eyeBoxY(), EW, EH, withBall);
}

static void ensureSprites() {
  if (ballSpr) return;
  ballSpr = new TFT_eSprite(T); ballSpr->setColorDepth(16); ballSpr->createSprite(BS, BS);
  eyeSpr = new TFT_eSprite(T); eyeSpr->setColorDepth(16); eyeSpr->createSprite(EW, EH);
}

// 眼睛"变形"的一帧：两只眼睛都画成高 h、中心在 cy+off 的胶囊，在 sprite 里画好一次推上屏（所以不闪）
static void morphEyes(int h, int off) {
  for (int i = 0; i < 2; i++) {
    const int bx0 = eyeBoxX(i), by0 = eyeBoxY();
    eyeSpr->fillSprite(C(GROUND));
    const int x = W() / 2 + (i == 0 ? -EYE_GAP / 2 - EYE_W : EYE_GAP / 2);
    eyeSpr->fillRoundRect(x - bx0, cy() + off - h / 2 - by0, EYE_W, h, min(EYE_W / 2, h / 2), C(INK));
    eyeSpr->pushSprite(bx0, by0);
  }
}

// 闭着的眼睛（U 形，和 sleepEyes 画的一样）：画进 sprite
static void sleepEyesPush() {
  const int ytop = cy() + 16;
  for (int i = 0; i < 2; i++) {
    const int bx0 = eyeBoxX(i), by0 = eyeBoxY();
    const int x = W() / 2 + (i == 0 ? -EYE_GAP / 2 - EYE_W : EYE_GAP / 2) - bx0, yt = ytop - by0;
    eyeSpr->fillSprite(C(GROUND));
    eyeSpr->fillRoundRect(x, yt - 40, EYE_W, 40 + 34, 32, C(INK));
    eyeSpr->fillRoundRect(x + 14, yt - 70, EYE_W - 28, 70 + 34 - 14, 18, C(GROUND));
    eyeSpr->fillRect(x - 1, yt - 44, EYE_W + 2, 44, C(GROUND));
    eyeSpr->pushSprite(bx0, by0);
  }
}

static void eraseBall() {   // 球所在的方块重画一遍（不带球）
  const int x = constrain((int)bx - BS / 2, 0, W() - BS), y = constrain((int)by - BS / 2, 0, H() - BS);
  composeAndPush(ballSpr, x, y, BS, BS, false);
}

static void playStart(bool fresh = true) {
  ensureSprites();
  bx = W() * (0.15f + random(0, 20) / 100.0f);
  by = H() * 0.3f;
  bvx = (random(2) ? 1 : -1) * W() * 0.3f;
  bvy = 0;
  bsq = 0;
  bLast = millis();
  gazeX = gazeY = 0;
  obx = (int)bx; oby = (int)by;
  if (fresh) T->fillScreen(C(GROUND));
  pushEyes();
  pushBall();
}

static void playStep(uint32_t now) {
  const float dt = min(0.04f, (now - bLast) / 1000.0f), G = H() * 2.6f;
  bLast = now;
  bvy += G * dt; bx += bvx * dt; by += bvy * dt;
  if (bx < BALL_R) { bx = BALL_R; bvx = fabsf(bvx); }
  if (bx > W() - BALL_R) { bx = W() - BALL_R; bvx = -fabsf(bvx); }
  if (by > H() - BALL_R) { by = H() - BALL_R; bvy = -max(fabsf(bvy) * 0.9f, H() * 1.25f); bsq = 1; }   // 落地反弹，永远弹得起来
  if (by < BALL_R) { by = BALL_R; bvy = fabsf(bvy) * 0.5f; }
  bsq = max(0.0f, bsq - dt * 6);

  // 眼睛跟着球；4 px 一档，免得每帧都重推眼睛
  const int tgx = constrain((int)((bx - W() / 2) * 0.14f), -34, 34) / 4 * 4, tgy = constrain((int)((by - H() / 2) * 0.12f), -18, 18) / 4 * 4;
  pushBall();
  if (tgx != gazeX || tgy != gazeY) { gazeX = tgx; gazeY = tgy; pushEyes(); pushBall(); }
}

// 睡觉：向下弯的两条线（闭眼）、飘上去的 z、左上角的梦泡泡（轮流梦到金币、涨停、往上的线）
static void sleepEyes() {
  const int cx = W() / 2, ytop = cy() + 16;
  for (int i = 0; i < 2; i++) {
    const int x = i == 0 ? cx - EYE_GAP / 2 - EYE_W : cx + EYE_GAP / 2;
    T->fillRoundRect(x, ytop - 40, EYE_W, 40 + 34, 32, C(INK));                  // 外圈（下半是圆的）
    T->fillRoundRect(x + 14, ytop - 70, EYE_W - 28, 70 + 34 - 14, 18, C(GROUND));  // 掏掉里面，剩下 14 px 粗的 U 形
    T->fillRect(x - 1, ytop - 44, EYE_W + 2, 44, C(GROUND));                       // 切掉上面，只留 U
  }
}

static void zzz(uint32_t now) {
  T->fillRect(366, 24, 114, 150, C(GROUND));
  for (int i = 0; i < 3; i++) {
    const float ph = fmodf(now / 1000.0f + i * 1.2f, 3.6f) / 3.6f;
    const float a = ph < 0.22f ? ph / 0.22f : ph > 0.8f ? (1 - ph) / 0.2f : 1;
    T->setTextColor(mix(GROUND, MUTED, a), C(GROUND));
    T->drawString(i == 0 ? "z" : "Z", 392 + (int)(ph * 36), 122 - (int)(ph * 64), i == 0 ? 2 : 4);
  }
}

static void sleepStart() {
  T->fillScreen(C(GROUND));
  sleepEyes();
}

// ---------- 状态之间的过渡（都是 sprite 里画好再推，不整屏重画，所以不闪）----------
static void clearMouth() { T->fillRect(W() / 2 - MOUTH_W / 2 - 3, 242 - 3, MOUTH_W + 6, MOUTH_H + 6, C(GROUND)); }

static void idleToPlay() {   // 嘴消失，球从上面掉下来
  clearMouth();
  cur = State::Play;
  stateSince = millis();
  playStart(false);
}

// 玩球 → 睡觉：球先收掉，眼睛慢慢眯成一条线，再变成闭眼的弧线
static void playToSleep() {
  ensureSprites();
  eraseBall();
  gazeX = gazeY = 0;
  pushEyes(false);
  const int hs[] = {104, 92, 78, 62, 48, 38, 32};
  for (int i = 0; i < 7; i++) { morphEyes(hs[i], 33 * (i + 1) / 7); delay(45); }
  sleepEyesPush();
  cur = State::Sleep;
  stateSince = millis();
}

// 睡觉 / 玩球 → 醒：眼睛从闭着一下睁开，过一点头再回来，然后小嘴出现
static void wakeUp(bool fromSleep) {
  ensureSprites();
  if (fromSleep) {
    T->fillRect(366, 24, 114, 150, C(GROUND));   // z 擦掉
    const int hs[] = {20, 52, 92, 126, 134, 122, 112};
    for (int i = 0; i < 7; i++) { morphEyes(hs[i], 33 * (6 - i) / 6); delay(34); }
  } else {
    eraseBall();
    gazeX = gazeY = 0;
    pushEyes(false);
  }
  mouth();
  nextBlink = millis() + 2500;
}

// ---------- 整屏重画 ----------
static void render() {
  if (bossOn) return clockFace(true);
  T->fillScreen(C(GROUND));
  switch (cur) {
    case State::Idle: eyesPill(INK, EYE_H); mouth(); break;
    case State::Blink: eyesPill(INK, EYE_H); mouth(); badge(); break;
    case State::Happy: eyesArc(INK); mouth(); break;
    case State::Listening: eyesPill(LILAC, EYE_H); waves(millis()); break;
    case State::Thinking: eyesPill(LILAC, EYE_H, EYE_GAP / 4, -EYE_H / 3); dots(millis()); break;
    case State::Ok: check(); break;
    case State::Stealth: stealth(); break;
    case State::Play: playStart(); break;
    case State::Sleep: sleepStart(); break;
    case State::Unsupported:
      eyesPill(INK, EYE_H); mouth();
      T->setTextColor(C(MUTED), C(GROUND));
      T->drawCentreString(String("[") + label + "]  text screens: next step", W() / 2, H() - 22, 2);
      break;
  }
}

void begin(TFT_eSPI *tft) {
  T = tft;
  lastActive = stateSince = millis();
  render();
}

static void apply(State s, int c, float p, float v, bool a, const char *l) {
  cur = s; cnt = c; pct = p; vol = v; alertFlag = a;
  strlcpy(label, l ? l : "", sizeof label);
  stateSince = millis();
  if (alertFlag && s == State::Stealth) winkUntil = millis() + 450;   // 异动：眨一下右眼
  if (!bossOn) render();
}

void set(State s, int c, float p, float v, bool a, const char *l) {   // 外面（中枢）来的指令：算"有人动过它"
  lastActive = millis();
  apply(s, c, p, v, a, l);
}

void poke() { lastActive = millis(); }

void wake() {
  lastActive = millis();
  if (bossOn || (cur != State::Play && cur != State::Sleep)) return;
  const bool wasSleep = cur == State::Sleep;
  cur = State::Idle;
  cnt = 0; alertFlag = false;
  stateSince = millis();
  wakeUp(wasSleep);
}

void setBoss(bool on) {
  bossOn = on;
  lastClock = 0;
  clockMin = -1;
  render();
}

bool boss() { return bossOn; }

void tick(uint32_t now) {
  if (bossOn) {   // 每秒刷新一次时钟
    if (now - lastClock > 1000) { lastClock = now; clockFace(false); }
    return;
  }
  // 待机导演：idle 安静一阵 → 玩球 → 睡觉，直到有人动它
  if (cur == State::Idle && now - lastActive > IDLE_AFTER) { idleToPlay(); return; }
  if (cur == State::Play && now - stateSince > PLAY_FOR) { playToSleep(); return; }
  if (cur == State::Play && now - lastAnim > 28) { lastAnim = now; playStep(now); return; }
  if (cur == State::Sleep && now - lastAnim > 100) {
    lastAnim = now;
    zzz(now);
    return;
  }
  if (cur == State::Listening && now - lastAnim > 70) { lastAnim = now; waves(now); }
  if (cur == State::Thinking && now - lastAnim > 140) { lastAnim = now; dots(now); }

  if (cur == State::Stealth && winkUntil) {
    if (now < winkUntil) {
      const int cx = W() / 2, top = cy() - EYE_H / 2;   // 右眼眯成一条线
      T->fillRect(cx + EYE_GAP / 2 - 2, top - 2, EYE_W + 4, EYE_H + 4, C(GROUND));
      T->fillRoundRect(cx + EYE_GAP / 2, cy() - 4, EYE_W, 8, 4, C(INK));
    } else { winkUntil = 0; stealth(); }
    return;
  }

  const bool blinkable = cur == State::Idle || cur == State::Blink || cur == State::Unsupported || (cur == State::Stealth && pct < 2);
  if (blinkable && now >= nextBlink) {
    eyeBand(); eyesPill(INK, 8);
    delay(110);
    eyeBand(); eyesPill(INK, EYE_H);
    if (cur == State::Stealth) stealth();
    nextBlink = millis() + 2500 + random(0, 3500);
  }
}

}  // namespace ui
