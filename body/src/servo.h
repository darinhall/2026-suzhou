// 飞特 ST3215（STS 协议）的最小驱动：只做固件用得到的几条指令，不依赖 SCServo 库。
// 寄存器（STS 内存表）：40 扭矩开关 · 41 加速度 · 42 目标位置 · 44 运行时间 · 46 速度 · 48 扭矩限制 · 56 当前位置 · 62 电压 · 63 温度
// 位置 0–4095 = 360°，2048 = 中位；双字节都是低字节在前。
#pragma once
#include <Arduino.h>

namespace servo {

void begin(int rxPin, int txPin, int dirPin);
bool ping(uint8_t id);
bool readPos(uint8_t id, int &pos);                       // 当前位置，步
bool readVoltTemp(uint8_t id, float &volt, int &temp);    // V、℃
bool setTorqueEnable(uint8_t id, bool on);
bool setTorqueLimit(uint8_t id, int permille);            // 0–1000
// 两个舵机一个包同时动（SYNC WRITE），省掉先后到位的错位感
void syncMove(uint8_t id1, int pos1, int speed1, uint8_t id2, int pos2, int speed2, uint8_t acc);

}  // namespace servo
