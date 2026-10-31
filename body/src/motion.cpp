#include "motion.h"

#include "net.h"
#include "servo.h"

#ifndef SERVO_YAW_ID
#define SERVO_YAW_ID 1
#define SERVO_PITCH_ID 2
#define SERVO_YAW_SIGN 1
#define SERVO_PITCH_SIGN 1
#endif

namespace motion {

// 软件限位（和 sim/body.js 的 LIMITS 一致）：偏航 ±150°，俯仰 ±25°
static const float YAW_MAX = 150, PITCH_MAX = 25;
static const float STEPS_PER_DEG = 4096.0f / 360.0f;
static const int MID = 2048;

static float cmdYaw = 0, cmdPitch = 0;   // 最近一次下发的目标（度）
static uint32_t moveDoneAt = 0;          // 当前这一段大概什么时候到位
static int torquePct = 50;
static bool ok = false;

// ---------- 手势 = 一串关键帧 ----------
struct Key { float yaw, pitch; int ms, hold; };
static Key queue[24];
static int qn = 0, qi = 0;
static uint32_t nextKeyAt = 0;

static int toSteps(float deg, int sign) { return MID + sign * (int)lroundf(deg * STEPS_PER_DEG); }

static void drive(float yaw, float pitch, int ms) {
  yaw = constrain(yaw, -YAW_MAX, YAW_MAX);
  pitch = constrain(pitch, -PITCH_MAX, PITCH_MAX);
  ms = max(ms, 60);
  // 速度 = 距离 / 时间（步/秒），ST3215 速度上限约 3400
  const auto speed = [&](float from, float to) { return constrain((int)(fabsf(to - from) * STEPS_PER_DEG * 1000.0f / ms), 80, 3400); };
  servo::syncMove(SERVO_YAW_ID, toSteps(yaw, SERVO_YAW_SIGN), speed(cmdYaw, yaw), SERVO_PITCH_ID, toSteps(pitch, SERVO_PITCH_SIGN), speed(cmdPitch, pitch), 30);
  cmdYaw = yaw;
  cmdPitch = pitch;
  moveDoneAt = millis() + ms;
}

static void clearQueue() { qn = qi = 0; }
static void push(float yaw, float pitch, int ms, int hold = 0) { if (qn < 24) queue[qn++] = {yaw, pitch, ms, hold}; }

void pose(float yaw, float pitch, int ms) {
  clearQueue();
  drive(yaw, pitch, ms);
}

bool gesture(const char *name, int times) {
  times = constrain(times, 1, 5);
  const float y = cmdYaw, p = cmdPitch;
  clearQueue();
  if (!strcmp(name, "nod")) { for (int i = 0; i < times; i++) { push(y, p - 15, 180); push(y, p, 180, 60); } }
  else if (!strcmp(name, "shake")) { for (int i = 0; i < times; i++) { push(y - 15, p, 150); push(y + 15, p, 250); push(y, p, 150, 60); } }
  else if (!strcmp(name, "look_up")) push(y, 20, 400);
  else if (!strcmp(name, "look_down")) push(y, -18, 400);
  else if (!strcmp(name, "home")) push(0, 0, 600);
  else if (!strcmp(name, "startle")) { push(y, 8, 140); push(y - 6, 8, 100); push(y + 6, 6, 120); push(y, 0, 260); }   // 惊醒：猛抬头 + 小摇
  else return false;
  qi = 0;
  nextKeyAt = 0;
  return true;
}

void torque(int pct) {
  torquePct = constrain(pct, 0, 100);
  servo::setTorqueLimit(SERVO_YAW_ID, torquePct * 10);
  servo::setTorqueLimit(SERVO_PITCH_ID, torquePct * 10);
}

bool servosOk() { return ok; }

// ---------- 启动 / 自检 ----------
static void checkServos(bool boot) {
  const bool a = servo::ping(SERVO_YAW_ID), b = servo::ping(SERVO_PITCH_ID);
  const bool now = a && b;
  if (now && !ok) {
    ok = true;
    for (int id : {SERVO_YAW_ID, SERVO_PITCH_ID}) servo::setTorqueEnable(id, true);
    torque(torquePct);
    cmdYaw = cmdPitch = 0;
    drive(0, 0, 800);
    net::log("info", "SERVO_OK", "两个舵机都应答了，已回正");
  } else if (!now) {
    ok = false;
    static uint32_t lastLog = 0;
    if (boot || millis() - lastLog > 30000) {
      lastLog = millis();
      char m[96];
      snprintf(m, sizeof m, "舵机没应答：偏航 ID%d %s，俯仰 ID%d %s。检查 7.4V 供电、总线接线和 ID", SERVO_YAW_ID, a ? "好" : "没响应", SERVO_PITCH_ID, b ? "好" : "没响应");
      net::log("error", "SERVO_TIMEOUT", m);
    }
  }
}

void begin() {
  servo::begin(SERVO_RX, SERVO_TX, SERVO_DIR);
  delay(300);   // 舵机上电要一会儿
  checkServos(true);
}

// ---------- 按头：目标没变、实际位置却被压低 >8° 持续 200 ms ----------
static void watchPress(uint32_t now) {
  static uint32_t lastRead = 0, since = 0, lockUntil = 0;
  if (now - lastRead < 30) return;
  lastRead = now;
  int pos;
  if (!servo::readPos(SERVO_PITCH_ID, pos)) return;
  const float actual = (pos - MID) * SERVO_PITCH_SIGN / STEPS_PER_DEG, dip = cmdPitch - actual;
  if (now < moveDoneAt + 150 || qi < qn) { since = 0; return; }   // 还在动的时候位置本来就对不上
  if (now < lockUntil) return;
  if (dip > 8) {
    if (!since) since = now;
    if (now - since >= 200) {
      JsonDocument d;
      d["t"] = "head_press";
      net::send(d);
      net::log("info", "HEAD_PRESS", "检测到按头");
      lockUntil = now + 1000;
      since = 0;
    }
  } else since = 0;
}

static void reportState(uint32_t now) {
  static uint32_t last = 0;
  if (now - last < 1000) return;
  last = now;
  int yp, pp, temp = 0;
  float volt = 0;
  if (!servo::readPos(SERVO_YAW_ID, yp) || !servo::readPos(SERVO_PITCH_ID, pp)) return;
  servo::readVoltTemp(SERVO_PITCH_ID, volt, temp);
  JsonDocument d;
  d["t"] = "state";
  d["yaw"] = roundf((yp - MID) * SERVO_YAW_SIGN / STEPS_PER_DEG * 10) / 10;
  d["pitch"] = roundf((pp - MID) * SERVO_PITCH_SIGN / STEPS_PER_DEG * 10) / 10;
  d["volt"] = volt;
  d["temp"] = temp;
  net::send(d);
  if (volt > 0 && volt < 6.0f) net::log("warn", "SERVO_LOW_VOLT", "舵机电压偏低，检查 LM2596 输出和适配器");
  if (temp >= 60) net::log("warn", "SERVO_HOT", "舵机温度偏高，让它歇一会儿");
}

void tick(uint32_t now) {
  if (!ok) {   // 舵机没起来：每 5 秒重试一次，其他功能（联网、日志）照常
    static uint32_t lastTry = 0;
    if (now - lastTry > 5000) { lastTry = now; checkServos(false); }
    return;
  }

  // 手势：到点就走下一帧
  if (qi < qn && now >= nextKeyAt) {
    const Key k = queue[qi++];
    drive(k.yaw, k.pitch, k.ms);
    nextKeyAt = now + k.ms + k.hold;
  }

  // 中枢掉线 2 秒还没回来：慢慢回正，别卡在最后一个姿势
  static uint32_t lostSince = 0;
  static bool homed = true;
  if (net::connected()) { lostSince = 0; homed = false; }
  else {
    if (!lostSince) lostSince = now;
    if (!homed && now - lostSince > 2000) {
      homed = true;
      pose(0, 0, 1500);
      net::log("warn", "HUB_LOST_HOME", "中枢掉线超过 2 秒，身体慢慢回正");
    }
  }

  watchPress(now);
  reportState(now);
}

}  // namespace motion
