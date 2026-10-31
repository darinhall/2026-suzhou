#include "servo.h"

namespace servo {

static HardwareSerial bus(1);
static uint8_t stash[64];   // send() 之后先收进来的字节（可能是回显，也可能已经是舵机的应答）
static int stashN = 0, stashPos = 0;

static int nextByte() {   // 先从 stash 里取，取完再读串口
  if (stashPos < stashN) return stash[stashPos++];
  return bus.available() ? bus.read() : -1;
}
static int dir = -1;
#ifndef SERVO_BAUD
#define SERVO_BAUD 115200   // 10-31 起两个舵机都改成了 115200：大电阻 + 30 cm 线在 1 Mbps 下波形不够陡，字节会坏
#endif
static const uint32_t BAUD = SERVO_BAUD;

static void txBegin() { if (dir >= 0) digitalWrite(dir, HIGH); }

static void send(uint8_t id, uint8_t inst, const uint8_t *p, uint8_t n) {
  uint8_t buf[40];
  uint8_t len = n + 2, sum = id + len + inst;
  buf[0] = buf[1] = 0xFF; buf[2] = id; buf[3] = len; buf[4] = inst;
  for (uint8_t i = 0; i < n; i++) { buf[5 + i] = p[i]; sum += p[i]; }
  buf[5 + n] = ~sum;
  const uint8_t total = 6 + n;
  while (bus.available()) bus.read();   // 先清掉上次剩下的
  stashN = stashPos = 0;
  txBegin();
  bus.write(buf, total);
  bus.flush();
  if (dir >= 0) digitalWrite(dir, LOW);
  else {   // 单线 + 电阻：有的接法会把发出去的字节原样回显，有的不会（电阻大时 RX 看不到自己的 TX）。
    // 所以不盲目丢掉 total 个字节：收进来先比对，和发出去的一模一样才当回显丢掉，否则留给 readReply（那其实是舵机的应答）
    stashN = stashPos = 0;
    for (uint32_t t = micros(); stashN < (int)sizeof stash && micros() - t < 3000;)
      if (bus.available()) stash[stashN++] = bus.read();
    if (stashN >= total && !memcmp(stash, buf, total)) stashPos = total;
  }
}

// 读应答：FF FF ID LEN ERR [data…] CHK；成功返回数据长度，失败 -1。
// 前面可能夹着自己发出去、被电阻削坏了的回显（比如 20 A0 FB），所以先在字节流里找 "FF FF ID" 这个开头再往下读
static int readReply(uint8_t id, uint8_t *data, uint8_t max, uint32_t timeoutUs = 15000) {
  uint8_t b[16];
  int n = 0, synced = 0;   // synced：已经对上 FF / FF FF / FF FF ID 的个数
  for (uint32_t t = micros(); micros() - t < timeoutUs;) {
    const int v = nextByte();
    if (v < 0) continue;
    if (synced < 3) {
      const uint8_t want = synced < 2 ? 0xFF : id;
      if (v == want) synced++;
      else if (v == 0xFF) synced = synced == 2 ? 2 : 1;   // 多出来的 FF 不算错，继续当开头
      else synced = 0;
      if (synced == 3) { b[0] = b[1] = 0xFF; b[2] = id; n = 3; }
      continue;
    }
    if (n < (int)sizeof b) b[n++] = (uint8_t)v;
    if (n >= 4 && n >= b[3] + 4) break;
  }
  if (synced < 3 || n < 6) return -1;
  const uint8_t len = b[3];
  if (n < len + 4) return -1;
  uint8_t sum = 0;
  for (uint8_t i = 2; i < len + 3; i++) sum += b[i];
  if ((uint8_t)~sum != b[len + 3]) return -1;
  const int dn = len - 2;
  for (int i = 0; i < dn && i < max; i++) data[i] = b[5 + i];
  return dn;
}

void begin(int rxPin, int txPin, int dirPin) {
  dir = dirPin;
  if (dir >= 0) { pinMode(dir, OUTPUT); digitalWrite(dir, LOW); }
  bus.begin(BAUD, SERIAL_8N1, rxPin, txPin);
}

void setBaud(uint32_t baud) { bus.updateBaudRate(baud); delay(5); while (bus.available()) bus.read(); }

bool ping(uint8_t id) {
  send(id, 0x01, nullptr, 0);
  uint8_t d[1];
  return readReply(id, d, 1) >= 0;
}

static bool readRegs(uint8_t id, uint8_t addr, uint8_t n, uint8_t *out) {
  const uint8_t p[2] = {addr, n};
  send(id, 0x02, p, 2);
  return readReply(id, out, n) == n;
}

bool readPos(uint8_t id, int &pos) {
  uint8_t d[2];
  if (!readRegs(id, 56, 2, d)) return false;
  pos = d[0] | (d[1] << 8);
  return true;
}

bool readVoltTemp(uint8_t id, float &volt, int &temp) {
  uint8_t d[2];
  if (!readRegs(id, 62, 2, d)) return false;
  volt = d[0] / 10.0f;
  temp = d[1];
  return true;
}

static bool writeRegs(uint8_t id, uint8_t addr, const uint8_t *v, uint8_t n) {
  uint8_t p[8];
  p[0] = addr;
  for (uint8_t i = 0; i < n; i++) p[1 + i] = v[i];
  send(id, 0x03, p, n + 1);
  uint8_t d[1];
  return readReply(id, d, 1) >= 0;
}

bool writeByte(uint8_t id, uint8_t addr, uint8_t v) { return writeRegs(id, addr, &v, 1); }

bool setTorqueEnable(uint8_t id, bool on) {
  const uint8_t v = on ? 1 : 0;
  return writeRegs(id, 40, &v, 1);
}

bool setTorqueLimit(uint8_t id, int permille) {
  permille = constrain(permille, 0, 1000);
  const uint8_t v[2] = {(uint8_t)(permille & 255), (uint8_t)(permille >> 8)};
  return writeRegs(id, 48, v, 2);
}

int debugPing(uint8_t id, uint8_t *out, int max) {
  const uint8_t pkt[6] = {0xFF, 0xFF, id, 2, 0x01, (uint8_t)~(id + 2 + 1)};
  while (bus.available()) bus.read();
  bus.write(pkt, 6);
  bus.flush();
  int n = 0;
  for (uint32_t t = micros(); micros() - t < 15000;)
    if (bus.available() && n < max) out[n++] = bus.read();
  return n;
}

bool move(uint8_t id, int pos, int speed, uint8_t acc) {
  pos = constrain(pos, 0, 4095);
  const uint8_t v[7] = {acc, (uint8_t)(pos & 255), (uint8_t)(pos >> 8), 0, 0, (uint8_t)(speed & 255), (uint8_t)(speed >> 8)};
  return writeRegs(id, 41, v, 7);
}

void syncMove(uint8_t id1, int pos1, int speed1, uint8_t id2, int pos2, int speed2, uint8_t acc) {
  // SYNC WRITE（0x83）：从寄存器 41 起写 7 字节 = 加速度、位置(2)、运行时间(2, 填 0 = 按速度走)、速度(2)
  uint8_t p[2 + 2 * 8];
  uint8_t n = 0;
  p[n++] = 41; p[n++] = 7;
  const int ids[2] = {id1, id2}, pos[2] = {pos1, pos2}, spd[2] = {speed1, speed2};
  for (int i = 0; i < 2; i++) {
    p[n++] = ids[i];
    p[n++] = acc;
    p[n++] = pos[i] & 255; p[n++] = pos[i] >> 8;
    p[n++] = 0; p[n++] = 0;
    p[n++] = spd[i] & 255; p[n++] = spd[i] >> 8;
  }
  send(0xFE, 0x83, p, n);
}

}  // namespace servo
