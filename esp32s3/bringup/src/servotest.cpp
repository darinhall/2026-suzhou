#include "servotest.h"

#include <Arduino.h>

#include "net.h"
#include "servo.h"

namespace servotest {

static const int RX = 47, TX = 21;
static const int STEPS_10DEG = 114;   // 4096 步 = 360°，10° ≈ 114 步

static const uint8_t PITCH = 1, YAW = 2;
static const int LOOK_DIR = 1;   // 「转头看你」往哪边转：+1 = 位置增大。装好后如果转反了改成 -1   // 11-01 实测：ID1 = 点头（俯仰），ID2 = 横向转头（偏航）

// 每个舵机允许的摆幅（单边，步数）。连线复杂：所有动作都不能超出开机摆动的范围。
// 11-01：ID1（点头）±20°；ID2（转头）±10°
int amp(uint8_t id) { return id == PITCH ? 2 * STEPS_10DEG : STEPS_10DEG; }

// 开机摆动实际走过的范围 [lo, hi] 和原位：之后所有动作都夹在这里面
static int lo[3] = {0, -1, -1}, hi[3] = {0, -1, -1}, rest[3] = {0, -1, -1};

static void report(const char *lvl, const char *code, const char *fmt, ...) {
  char m[160];
  va_list ap; va_start(ap, fmt); vsnprintf(m, sizeof m, fmt, ap); va_end(ap);
  Serial.printf("[servo] %s\n", m);
  net::log(lvl, code, m);
}

static bool pingRetry(uint8_t id) {
  for (int i = 0; i < 3; i++) { if (servo::ping(id)) return true; delay(20); }
  return false;
}

static bool readPosRetry(uint8_t id, int &pos) {
  for (int i = 0; i < 3; i++) { if (servo::readPos(id, pos)) return true; delay(10); }
  return false;
}

// 走到 target，等它到位，返回实际位置（读不到返回 -1）
static int goAndRead(uint8_t id, int target) {
  int from = -1;
  readPosRetry(id, from);
  servo::move(id, target, 400, 20);   // 400 步/秒 ≈ 35°/秒，慢慢走
  delay(from < 0 ? 1500 : 300 + abs(target - from) * 1000 / 400);   // 按距离等：±20° 一趟要 1 秒多
  int p = -1;
  readPosRetry(id, p);
  return p;
}

void wiggle(uint8_t id, int times) {
  servo::begin(RX, TX, -1);
  delay(100);
  int p0 = -1;
  if (!pingRetry(id) || !readPosRetry(id, p0)) { report("error", "SERVO_TIMEOUT", "ID%d 没应答", id); return; }
  const int a = amp(id);
  const int c0 = constrain(p0, a + 10, 4095 - a - 10);
  lo[id] = c0 - a; hi[id] = c0 + a; rest[id] = p0;
  servo::setTorqueLimit(id, 300);
  servo::setTorqueEnable(id, true);
  for (int i = 0; i < times; i++) { goAndRead(id, c0 - a); goAndRead(id, c0 + a); }
  const int end = goAndRead(id, p0);
  servo::setTorqueEnable(id, false);
  report("info", "SERVO_WIGGLE", "ID%d 来回摆了 %d 次（±%d°），回到 %d（原位 %d）", id, times, (int)lroundf(a * 360.0f / 4096), end, p0);
}

// ---------- 动作（不阻塞）：排成一串步骤，loop() 里的 tick() 按时间一步步发 ----------
struct Step { uint8_t id; int target; uint16_t speed; uint16_t waitMs; };
static Step q[16];
static int qn = 0, qi = 0;
static uint32_t nextAt = 0;
static bool torqueOn[3] = {false, false, false};

static int clampT(uint8_t id, int target) { return lo[id] < 0 ? rest[id] : constrain(target, lo[id], hi[id]); }

static void push(uint8_t id, int offset, uint16_t speed, uint16_t extraMs = 60) {
  if (qn >= 16 || rest[id] < 0) return;
  const int t = clampT(id, rest[id] + offset);
  const int prev = qn > 0 && q[qn - 1].id == id ? q[qn - 1].target : rest[id];
  q[qn++] = {id, t, speed, (uint16_t)(abs(t - prev) * 1000 / speed + extraMs)};
}

bool busy() { return qi < qn; }

void gesture(const char *name, int times, float ampDeg, float holdS) {
  if (busy()) return;   // 上一个动作还没做完：丢掉，不排队（提醒连着来也不会抽搐）
  qn = qi = 0;
  times = constrain(times, 1, 3);
  const auto steps = [](float deg) { return (int)lroundf(deg * 4096.0f / 360.0f); };
  if (!strcmp(name, "nod")) {   // 点头：ID1 往下再回来
    const int d = min(steps(ampDeg > 0 ? ampDeg : 12), amp(PITCH));
    for (int i = 0; i < times; i++) { push(PITCH, -d, 900); push(PITCH, 0, 900); }
  } else if (!strcmp(name, "shake")) {   // 摇头：ID2 左右
    const int d = min(steps(ampDeg > 0 ? ampDeg : 8), amp(YAW));
    for (int i = 0; i < times; i++) { push(YAW, -d, 700); push(YAW, d, 700); }
    push(YAW, 0, 700);
  } else if (!strcmp(name, "glance")) {   // 瞥一眼：ID2 转一点马上回来
    push(YAW, LOOK_DIR * min(steps(ampDeg > 0 ? ampDeg : 6), amp(YAW)), 500, 400);
    push(YAW, 0, 500);
  } else if (!strcmp(name, "look")) {   // 转头看你：ID2 转到头，停 hold 秒，抬一下头，再回来
    push(YAW, LOOK_DIR * amp(YAW), 400, (uint16_t)(constrain(holdS > 0 ? holdS : 2, 0.5f, 5.0f) * 1000));
    push(YAW, 0, 400);
  } else {
    Serial.printf("[servo] 不认识的动作 %s\n", name);
    return;
  }
  nextAt = millis();
}

void tick() {
  if (!busy() || (int32_t)(millis() - nextAt) < 0) {
    if (!busy() && qn) {   // 做完了：放松扭矩（手还能拧动，也不发热）
      for (uint8_t id = 1; id <= 2; id++) if (torqueOn[id]) { servo::setTorqueEnable(id, false); torqueOn[id] = false; }
      qn = qi = 0;
    }
    return;
  }
  const Step &s = q[qi++];
  if (!torqueOn[s.id]) { servo::setTorqueLimit(s.id, 300); servo::setTorqueEnable(s.id, true); torqueOn[s.id] = true; }
  servo::move(s.id, s.target, s.speed, 40);
  nextAt = millis() + s.waitMs;
}

void nod() { gesture("nod", 1, 8, 0); }

// STS 系列：往寄存器 40（扭矩开关）写 128 = 把当前位置校正为 2048（中位）。要先解锁 EEPROM（55 = 0）
static bool setCenterHere(uint8_t id) {
  servo::writeByte(id, 55, 0);
  delay(5);
  const bool ok = servo::writeByte(id, 40, 128);
  delay(50);
  servo::writeByte(id, 55, 1);
  delay(20);
  return ok;
}

void rebaseYaw(float deg) {
  servo::begin(RX, TX, -1);
  delay(50);
  const uint8_t id = YAW;
  int p0 = -1, p1 = -1, p2 = -1, p3 = -1;
  if (!pingRetry(id) || !readPosRetry(id, p0)) { report("error", "SERVO_TIMEOUT", "ID2 没应答，没法定基准"); return; }
  setCenterHere(id);                 // 先把当前位置变成 2048，离量程两头都远，才能往任一方向转
  readPosRetry(id, p1);
  servo::setTorqueLimit(id, 300);
  servo::setTorqueEnable(id, true);
  const int steps = (int)lroundf(deg * 4096.0f / 360.0f);
  servo::move(id, p1 + steps, 300, 20);   // deg > 0：位置增大（开机摆动第一下的反方向）；deg < 0：和开机第一下同方向
  delay(900);
  readPosRetry(id, p2);
  setCenterHere(id);                 // 新位置定为基准（2048）
  readPosRetry(id, p3);
  servo::setTorqueEnable(id, false);
  report("info", "SERVO_REBASE", "ID2 定基准：原来 %d → 校正后 %d → 转 %+d 步（约 %+d°）到 %d → 新基准 %d（应接近 2048）", p0, p1, steps, (int)lroundf(deg), p2, p3);
}

void run() {
  servo::begin(RX, TX, -1);   // 没有方向脚：TX、RX 都经电阻接 DATA，发出的字节会回显，驱动里会丢掉
  delay(200);
  // 舵机已经改成 115200（写在舵机 EEPROM 里）。万一换了一个还是出厂 1 Mbps 的舵机，就提示一下（不自动改）
  if (!pingRetry(1) && !pingRetry(2)) {
    servo::setBaud(1000000);
    const bool at1M = pingRetry(1) || pingRetry(2);
    servo::setBaud(115200);
    if (at1M) report("warn", "SERVO_BAUD", "舵机还是 1 Mbps：需要改成 115200（写寄存器 55=0 → 6=4 → 55=1）");
  }
  int okCount = 0;
  for (uint8_t id = 1; id <= 2; id++) {
    if (!pingRetry(id)) { report("error", "SERVO_TIMEOUT", "ID%d 没应答（检查 DATA 接线、12V、共地；电阻太大也可能让信号太弱）", id); continue; }
    int p0 = -1, temp = 0;
    float volt = 0;
    readPosRetry(id, p0);
    servo::readVoltTemp(id, volt, temp);
    report("info", "SERVO_OK", "ID%d 应答 · 位置 %d（%.1f°）· 电压 %.1f V · 温度 %d ℃", id, p0, p0 >= 0 ? (p0 - 2048) * 360.0f / 4096 : 0.0f, volt, temp);
    if (p0 < 0) continue;
    okCount++;
    servo::setTorqueLimit(id, 300);   // 30% 扭矩：卡住也不会太猛
    servo::setTorqueEnable(id, true);
    // 位置在 0 / 4095 边上时不能跨过去：中心点往里收一点，保证摆幅都在 0–4095 里
    const int c0 = constrain(p0, amp(id) + 10, 4095 - amp(id) - 10);
    const int t1 = c0 + amp(id), t2 = c0 - amp(id);
    const int a = goAndRead(id, t1);
    const int b = goAndRead(id, t2);
    const int c = goAndRead(id, p0);
    const bool moved = a > 0 && b > 0 && abs(a - t1) < 25 && abs(b - t2) < 25;
    report(moved ? "info" : "warn", moved ? "SERVO_MOVE_OK" : "SERVO_MOVE_BAD", "ID%d 小幅度测试 → %d，→ %d，回原位 → %d（目标 %d / %d / %d）%s",
           id, a, b, c, t1, t2, p0, moved ? "：动作正常" : "：没走到目标（看是否卡住、扭矩不够或没收到指令）");
    servo::setTorqueEnable(id, false);   // 测完放松，手可以拧动
  }
  report(okCount == 2 ? "info" : "warn", "SERVO_SELFTEST", "舵机自检结束：%d / 2 个正常", okCount);
}

}  // namespace servotest
