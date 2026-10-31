#include "ui.h"
#include "palette.h"
#include "screens.h"
#include "servotest.h"
#include <time.h>

namespace ui {

static TFT_eSPI *T;

// ---------- 招财熊猫（11-01）----------
// 整张脸每一帧都从参数重画进一个全屏 sprite（PSRAM）再推上屏，所以任何东西都能动、不闪：
// 脸的位置跟着舵机（点头 = 上下、转头 = 左右，servotest::offsetDeg）+ 呼吸起伏；眼睛会四处看、眨眼、眯眼笑；
// 时不时自己笑一下（眼睛弯成 ^ ^、张嘴、耳朵抖、腮红变深）；红项圈上挂一枚铜钱，跟着头晃。
// 颜色：脸是暖白，眼斑 / 耳朵墨黑，眼睛白色胶囊；招财的红和金只用在项圈和铜钱上。
static const uint32_t GROUND = 0xF4F1EA, PATCH = 0x161616, EYEC = 0xF7F4EC, MUTED = 0x625A47, LILAC = 0x9B7EF0,
                      RED = 0xD7262B, RED_D = 0xA81C20, GOLD = 0xF5B83D, GOLD_D = 0xB7791F, BLUSH = 0xF4B3AB, TONGUE = 0xE0605A, ON_INK = 0xF8F2E1;
static const int EYE_W = 54, EYE_H = 92, EYE_GAP = 122, CY = 150;
static const uint32_t IDLE_AFTER = 25000, PLAY_FOR = 12000;   // 安静 25 秒玩铜钱，玩 12 秒去睡
static const uint32_t FRAME_MS = 50;                          // 约 20 帧 / 秒

static uint16_t C(uint32_t h) { h = devColor(h); return T->color565((h >> 16) & 255, (h >> 8) & 255, h & 255); }
static uint16_t mix(uint32_t a, uint32_t b, float t) {
  a = devColor(a); b = devColor(b);
  t = t < 0 ? 0 : t > 1 ? 1 : t;
  auto ch = [&](int sh) { return (int)(((a >> sh) & 255) * (1 - t) + ((b >> sh) & 255) * t); };
  return T->color565(ch(16), ch(8), ch(0));
}

static State cur = State::Idle;
static int cnt = 0;
static float pct = 0, vol = 0.3f;
static bool alertFlag = false;
static char label[24] = "";
static uint32_t lastActive = 0, stateSince = 0, lastFrame = 0;
static TFT_eSprite *frm = nullptr;

// 表情参数（每帧往目标值缓动）
static float gx = 0, gy = 0, tgx = 0, tgy = 0;   // 眼睛看的方向（像素）
static uint32_t nextGaze = 2000, nextBlink = 3000, blinkStart = 0, smileUntil = 0, nextSmile = 9000, winkUntil = 0;
static float eyeOpen = 1, smileAmt = 0;           // 0..1
// 玩铜钱
static float bx, by, bvx, bvy, bsq;
static uint32_t bLast;
static const int BALL_R = 20;

static int W() { return T->width(); }
static int H() { return T->height(); }

// ---------- 画图小工具（都画进 frm）----------
static void fillRotEllipse(float cx, float cyy, float a, float b, float ang, uint16_t col) {
  const float c = cosf(ang), s = sinf(ang), A = c * c / (a * a) + s * s / (b * b), R = max(a, b);
  for (int y = (int)(cyy - R); y <= (int)(cyy + R); y++) {
    const float dy = y - cyy, B = 2 * dy * c * s * (1 / (a * a) - 1 / (b * b)), Cc = dy * dy * (s * s / (a * a) + c * c / (b * b)) - 1;
    const float disc = B * B - 4 * A * Cc;
    if (disc < 0) continue;
    const float r = sqrtf(disc), x0 = (-B - r) / (2 * A), x1 = (-B + r) / (2 * A);
    frm->drawFastHLine((int)(cx + x0), y, (int)(x1 - x0) + 1, col);
  }
}

static void arc(float cx, float cyy, float r, int a0, int a1, int thick, uint16_t col) {   // 粗弧线：沿弧画小圆
  for (int d = a0; d <= a1; d += 6) frm->fillCircle(cx + r * cosf(d * PI / 180), cyy + r * sinf(d * PI / 180), thick, col);
}

// ---------- 一帧 ----------
static void drawFrame(uint32_t now) {
  if (!frm) return;
  // 脸的位置：舵机（点头 / 转头）+ 呼吸
  const float yaw = servotest::offsetDeg(2), pitch = servotest::offsetDeg(1);
  const bool sleeping = cur == State::Sleep;
  const float breathe = sinf(now / (sleeping ? 1600.0f : 1100.0f)) * (sleeping ? 3 : 2);
  const float dx = yaw * 2.6f, dy = -pitch * 1.8f + breathe;
  const int ox = (int)dx, oy = (int)dy;

  frm->fillSprite(C(GROUND));
  // 耳朵：笑 / 在听的时候抖一抖
  const int earJ = (smileAmt > 0.5f || cur == State::Listening) ? (int)(sinf(now / 55.0f) * 3) : 0;
  frm->fillCircle(86 + ox, 20 + oy + earJ, 50, C(PATCH));
  frm->fillCircle(394 + ox, 20 + oy - earJ, 50, C(PATCH));

  // 眼斑 + 眼睛
  const bool happyEyes = smileAmt > 0.5f || (cur == State::Stealth && pct >= 2);
  const uint32_t ec = (cur == State::Listening || cur == State::Thinking) ? LILAC : EYEC;
  for (int s = -1; s <= 1; s += 2) {
    const int ecx = 240 + s * (EYE_GAP / 2 + EYE_W / 2) + ox;
    fillRotEllipse(ecx + s * 4, CY + 6 + oy, 56, 80, s * -0.42f, C(PATCH));
    const int ex = ecx + (int)gx, ey = CY + oy + (int)gy;
    if (sleeping) {
      arc(ex, ey - 6, 22, 20, 160, 5, C(EYEC));                          // 闭眼：向下弯
    } else if (happyEyes) {
      arc(ex, ey + 14, 22, 200, 340, 5, C(EYEC));                        // 笑眼：^ ^
    } else if (cur == State::Stealth && s > 0 && winkUntil && millis() < winkUntil) {
      frm->fillRoundRect(ex - EYE_W / 2, ey - 4, EYE_W, 8, 4, C(EYEC));  // 异动：眨一下右眼
    } else {
      float open = eyeOpen;
      if (cur == State::Stealth) open *= pct <= -2 ? 0.55f : pct < -0.5f ? 0.75f : 1;   // 跌了：眼皮耷拉
      const int h = max(8, (int)(EYE_H * open));
      frm->fillRoundRect(ex - EYE_W / 2, ey - h / 2, EYE_W, h, min(EYE_W / 2, h / 2), C(ec));
      if (h > 40) frm->fillCircle(ex + (int)(gx * 0.6f), ey + (int)(gy * 0.6f) - 6, 9, C(PATCH));   // 瞳孔：看哪边就偏哪边
    }
  }

  // 腮红：笑的时候更红；摸鱼模式里涨得多也脸红
  float blush = 0.55f + 0.45f * smileAmt;
  if (cur == State::Stealth) blush = pct >= 2 ? 1.0f : pct > 0.5f ? 0.55f + (pct - 0.5f) / 1.5f * 0.45f : 0.4f;
  for (int s = -1; s <= 1; s += 2) frm->fillEllipse(240 + s * 102 + ox, 256 + oy, 24 + (int)(4 * smileAmt), 10, mix(GROUND, BLUSH, blush * 1.4f));

  // 鼻子 + 嘴（ω；笑的时候张开，露出小舌头）
  frm->fillEllipse(240 + ox, 231 + oy, 14, 9, C(PATCH));
  if (cur != State::Listening) {
    arc(232 + ox, 241 + oy, 8, 20, 160, 2, C(PATCH));
    arc(248 + ox, 241 + oy, 8, 20, 160, 2, C(PATCH));
    if (smileAmt > 0.05f) {
      const int mh = (int)(14 * smileAmt);
      frm->fillEllipse(240 + ox, 252 + oy, 11, max(1, mh / 2 + 2), C(PATCH));
      frm->fillEllipse(240 + ox, 255 + oy + mh / 4, 7, max(1, mh / 3), C(TONGUE));
    }
  }

  // 红项圈 + 铜钱（身体不跟头走，铜钱跟着晃）
  frm->fillRect(0, 288, 480, 32, C(RED));
  frm->fillRect(0, 288, 480, 3, C(RED_D));
  const int coinX = 240 + (int)(dx * 0.35f + sinf(now / 420.0f) * (fabsf(yaw) > 0.5f ? 4 : 1));
  frm->fillCircle(coinX, 298, 23, C(GOLD_D));
  frm->fillCircle(coinX, 298, 20, C(GOLD));
  frm->fillRect(coinX - 6, 292, 12, 12, C(RED_D));

  // 状态叠加
  if (cur == State::Listening) {   // 在听：嘴的位置变成一条声波
    frm->fillRoundRect(170 + ox, 238 + oy, 140, 40, 20, C(PATCH));
    for (int i = 0; i < 6; i++) {
      const float h = 6 + 22 * (0.5f + 0.5f * sinf(now / 150.0f + i * 0.9f));
      frm->fillRoundRect(184 + i * 20 + ox, 258 + oy - (int)h / 2, 9, (int)h, 4, C(LILAC));
    }
  } else if (cur == State::Thinking) {   // 想一想：右上方冒三个思考泡泡
    for (int i = 0; i < 3; i++) {
      const float a = 0.3f + 0.7f * (0.5f + 0.5f * sinf(now / 200.0f - i * 1.1f));
      frm->fillCircle(318 + i * 26 + ox, 96 - i * 22 + oy, 6 + i * 4, mix(GROUND, LILAC, a));
    }
  } else if (sleeping) {   // z z z
    for (int i = 0; i < 3; i++) {
      const float ph = fmodf(now / 1000.0f + i * 1.2f, 3.6f) / 3.6f;
      const float a = ph < 0.22f ? ph / 0.22f : ph > 0.8f ? (1 - ph) / 0.2f : 1;
      frm->setTextColor(mix(GROUND, MUTED, a));
      frm->drawString(i == 0 ? "z" : "Z", 300 + (int)(ph * 34), 110 - (int)(ph * 64), i == 0 ? 2 : 4);
    }
  } else if (cur == State::Play) {   // 玩铜钱：弹来弹去，眼睛跟着它
    const float sx = 1 + 0.35f * bsq, sy = 1 - 0.35f * bsq;
    const int rx = (int)(BALL_R * sx), ry = (int)(BALL_R * sy), cx = (int)bx, cyy = (int)by + (BALL_R - ry);
    frm->fillEllipse(cx, cyy, rx, ry, C(GOLD_D));
    frm->fillEllipse(cx, cyy, max(1, rx - 3), max(1, ry - 3), C(GOLD));
    frm->fillRect(cx - 5, cyy - 5, 10, 10, C(GOLD_D));
  } else if (cur == State::Ok) {   // 对勾
    const int cx = 240, y = 60;
    frm->fillCircle(cx, y, 34, C(PATCH));
    for (int o = -3; o <= 3; o++) {
      frm->drawLine(cx - 16, y + o, cx - 5, y + 11 + o, C(ON_INK));
      frm->drawLine(cx - 5, y + 11 + o, cx + 17, y - 14 + o, C(ON_INK));
    }
  } else if (cur == State::Blink && cnt > 0) {   // 未读数
    frm->fillCircle(448, 112, 22, C(RED));
    frm->setTextColor(C(ON_INK));
    frm->drawCentreString(String(cnt), 448, 100, 4);
  }
  frm->pushSprite(0, 0);
}

// ---------- 每帧更新参数 ----------
static void startPlay(uint32_t now) {
  bx = W() * (0.15f + random(0, 20) / 100.0f); by = H() * 0.25f;
  bvx = (random(2) ? 1 : -1) * W() * 0.3f; bvy = 0; bsq = 0; bLast = now;
}

static void stepPlay(uint32_t now) {
  const float dt = min(0.06f, (now - bLast) / 1000.0f), G = H() * 2.6f;
  bLast = now;
  bvy += G * dt; bx += bvx * dt; by += bvy * dt;
  if (bx < BALL_R) { bx = BALL_R; bvx = fabsf(bvx); }
  if (bx > W() - BALL_R) { bx = W() - BALL_R; bvx = -fabsf(bvx); }
  if (by > 286 - BALL_R) { by = 286 - BALL_R; bvy = -max(fabsf(bvy) * 0.9f, H() * 1.2f); bsq = 1; }   // 落在项圈上弹起来
  if (by < BALL_R) { by = BALL_R; bvy = fabsf(bvy) * 0.5f; }
  bsq = max(0.0f, bsq - dt * 6);
  tgx = constrain((bx - W() / 2) * 0.12f, -12.0f, 12.0f);
  tgy = constrain((by - CY) * 0.1f, -10.0f, 10.0f);
}

static void update(uint32_t now) {
  // 待机导演：安静一阵 → 玩铜钱 → 睡觉，直到有人动它
  if (cur == State::Idle && now - lastActive > IDLE_AFTER) { cur = State::Play; stateSince = now; startPlay(now); }
  if (cur == State::Play && now - stateSince > PLAY_FOR) { cur = State::Sleep; stateSince = now; }
  if ((cur == State::Happy || cur == State::Ok) && now - stateSince > 2000) { cur = State::Idle; stateSince = now; }   // 笑完回到待机
  const bool awake = cur != State::Sleep;

  // 眼睛看的方向
  if (cur == State::Play) stepPlay(now);
  else if (cur == State::Thinking) { tgx = 10; tgy = -14; }
  else if (cur == State::Listening) { tgx = 0; tgy = 0; }
  else if (awake && now >= nextGaze) {   // 四处看看
    const bool center = random(0, 10) < 4;
    tgx = center ? 0 : random(-12, 13); tgy = center ? 0 : random(-8, 9);
    nextGaze = now + 1500 + random(0, 3000);
  }
  gx += (tgx - gx) * 0.25f; gy += (tgy - gy) * 0.25f;

  // 眨眼：约 180 ms 闭上再睁开
  if (awake && now >= nextBlink) { blinkStart = now; nextBlink = now + 2600 + random(0, 3400); }
  const uint32_t bt = now - blinkStart;
  eyeOpen = bt < 90 ? 1 - bt / 90.0f * 0.9f : bt < 180 ? 0.1f + (bt - 90) / 90.0f * 0.9f : 1;

  // 笑：开心状态 / 点头的时候 / 待机时偶尔自己笑一下
  const bool nodding = fabsf(servotest::offsetDeg(1)) > 1.0f;
  if (cur == State::Idle && now >= nextSmile) { smileUntil = now + 1600; nextSmile = now + 9000 + random(0, 7000); }
  const bool smiling = cur == State::Happy || cur == State::Ok || nodding || now < smileUntil;
  smileAmt += ((smiling ? 1.0f : 0.0f) - smileAmt) * 0.3f;
}

// ---------- 对外 ----------
void begin(TFT_eSPI *tft) {
  T = tft;
  frm = new TFT_eSprite(T);
  frm->setColorDepth(16);
  if (!frm->createSprite(W(), H())) { delete frm; frm = nullptr; Serial.println("[ui] 熊猫脸 sprite 分配失败"); }
  lastActive = stateSince = millis();
  smileUntil = millis() + 2500;   // 一开机先笑一下
  const uint32_t t0 = millis();
  drawFrame(millis());
  Serial.printf("[ui] 熊猫脸一帧 %lu ms（画 + 推屏）\n", (unsigned long)(millis() - t0));
}

static void apply(State s, int c, float p, float v, bool a, const char *l) {
  cur = s; cnt = c; pct = p; vol = v; alertFlag = a;
  strlcpy(label, l ? l : "", sizeof label);
  stateSince = millis();
  if (alertFlag && s == State::Stealth) winkUntil = millis() + 450;
  if (s == State::Happy) smileUntil = millis() + 1800;
  if (s == State::Text) { screens::redraw(); return; }
  drawFrame(millis());
}

void set(State s, int c, float p, float v, bool a, const char *l) {   // 外面（中枢）来的指令：算"有人动过它"
  lastActive = millis();
  apply(s, c, p, v, a, l);
}

void poke() { lastActive = millis(); }
bool isText() { return cur == State::Text; }
State current() { return cur; }

void setText() {
  lastActive = millis();
  cur = State::Text;
  stateSince = millis();
}

void wake() {
  lastActive = millis();
  if (cur != State::Play && cur != State::Sleep) return;
  cur = State::Idle;
  cnt = 0; alertFlag = false;
  stateSince = millis();
  smileUntil = millis() + 1200;   // 醒过来先笑一下
}

void tick(uint32_t now) {
  if (cur == State::Text) return;   // 卡片在屏上：脸不画
  // 一帧约 75 ms（画 + 推整屏）。在听的时候麦克风的 DMA 只有 96 ms 缓冲：放慢到 4 帧 / 秒，别把声音丢了
  if (now - lastFrame < (cur == State::Listening ? 250u : FRAME_MS)) return;
  lastFrame = now;
  update(now);
  drawFrame(now);
}

}  // namespace ui
