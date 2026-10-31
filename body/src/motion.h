// 身体的运动层：pose / gesture / torque 指令 → 舵机；检测"按头"；中枢掉线就慢慢回正。
// 协议见《双板方案》，每个动作的用意见《动作对照》。
#pragma once
#include <Arduino.h>

namespace motion {

void begin();
void tick(uint32_t now);                          // 每圈 loop 调一次
void pose(float yaw, float pitch, int ms);        // 打断正在做的手势
bool gesture(const char *name, int times);        // nod / shake / look_up / look_down / home / startle；不认识返回 false
void torque(int pct);                             // 0–100
bool servosOk();

}  // namespace motion
