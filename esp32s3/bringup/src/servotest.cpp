#include "servotest.h"

#include <Arduino.h>

#include "net.h"
#include "servo.h"

namespace servotest {

static const int RX = 47, TX = 21;
static const int STEPS_10DEG = 114;   // 4096 步 = 360°，10° ≈ 114 步

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
  servo::move(id, target, 400, 20);   // 400 步/秒 ≈ 35°/秒，慢慢走
  delay(700);
  int p = -1;
  readPosRetry(id, p);
  return p;
}

void wiggle(uint8_t id, int times) {
  servo::begin(RX, TX, -1);
  delay(100);
  int p0 = -1;
  if (!pingRetry(id) || !readPosRetry(id, p0)) { report("error", "SERVO_TIMEOUT", "ID%d 没应答", id); return; }
  const int c0 = constrain(p0, STEPS_10DEG + 10, 4095 - STEPS_10DEG - 10);
  servo::setTorqueLimit(id, 300);
  servo::setTorqueEnable(id, true);
  for (int i = 0; i < times; i++) { goAndRead(id, c0 - STEPS_10DEG); goAndRead(id, c0 + STEPS_10DEG); }
  const int end = goAndRead(id, p0);
  servo::setTorqueEnable(id, false);
  report("info", "SERVO_WIGGLE", "ID%d 来回摆了 %d 次（±10°），回到 %d（原位 %d）", id, times, end, p0);
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
    // 位置在 0 / 4095 边上时不能跨过去：中心点往里收一点，保证 ±10° 都在 0–4095 里（离原位最多 ~10°）
    const int c0 = constrain(p0, STEPS_10DEG + 10, 4095 - STEPS_10DEG - 10);
    const int t1 = c0 + STEPS_10DEG, t2 = c0 - STEPS_10DEG;
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
