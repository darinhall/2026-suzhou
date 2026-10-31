#include "servo.h"

namespace servo {

static HardwareSerial bus(1);
static int dir = -1;
static const uint32_t BAUD = 1000000;

static void txBegin() { if (dir >= 0) digitalWrite(dir, HIGH); }

static void send(uint8_t id, uint8_t inst, const uint8_t *p, uint8_t n) {
  uint8_t buf[40];
  uint8_t len = n + 2, sum = id + len + inst;
  buf[0] = buf[1] = 0xFF; buf[2] = id; buf[3] = len; buf[4] = inst;
  for (uint8_t i = 0; i < n; i++) { buf[5 + i] = p[i]; sum += p[i]; }
  buf[5 + n] = ~sum;
  const uint8_t total = 6 + n;
  while (bus.available()) bus.read();   // 先清掉上次剩下的
  txBegin();
  bus.write(buf, total);
  bus.flush();
  if (dir >= 0) digitalWrite(dir, LOW);
  else {   // 单线 + 电阻：发出去的字节会原样回显，丢掉
    for (uint32_t t = micros(); bus.available() < total && micros() - t < 3000;) {}
    for (uint8_t i = 0; i < total && bus.available(); i++) bus.read();
  }
}

// 读应答：FF FF ID LEN ERR [data…] CHK；成功返回数据长度，失败 -1
static int readReply(uint8_t id, uint8_t *data, uint8_t max, uint32_t timeoutUs = 6000) {
  uint8_t b[16];
  uint8_t n = 0;
  for (uint32_t t = micros(); micros() - t < timeoutUs && n < sizeof b;) {
    if (bus.available()) b[n++] = bus.read();
    if (n >= 4 && n >= (uint8_t)(b[3] + 4)) break;
  }
  if (n < 6 || b[0] != 0xFF || b[1] != 0xFF || b[2] != id) return -1;
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

bool setTorqueEnable(uint8_t id, bool on) {
  const uint8_t v = on ? 1 : 0;
  return writeRegs(id, 40, &v, 1);
}

bool setTorqueLimit(uint8_t id, int permille) {
  permille = constrain(permille, 0, 1000);
  const uint8_t v[2] = {(uint8_t)(permille & 255), (uint8_t)(permille >> 8)};
  return writeRegs(id, 48, v, 2);
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
