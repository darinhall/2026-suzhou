// 舵机自检：ping ID1 / ID2，读位置、电压、温度，然后每个舵机在当前位置附近 ±10° 小幅度来回一次，最后放松扭矩。
// 接线：TX GPIO21 → 约 3.3 kΩ → DATA；RX GPIO47 → 约 5 kΩ → DATA；舵机 12 V 单独供电，和板子共地。
#pragma once
#include <stdint.h>

namespace servotest {
void run();
// 舵机允许的单边摆幅（步数）：ID1（点头）±20°，ID2（转头）±10°
int amp(uint8_t id);
// ID1 = 点头（俯仰，±20°），ID2 = 横向转头（偏航，±10°）。所有动作都夹在开机摆动走过的范围里
// 只让一个舵机在当前位置附近来回摆 times 次（摆幅 = amp(id)），顺便记下这个舵机允许的范围；开机时调
void wiggle(uint8_t id, int times);
// 动作（不阻塞，loop() 里要调 tick()）：nod 点头（ID1）/ shake 摇头（ID2）/ glance 瞥一眼 / look 转头看你（停 holdS 秒）
// ampDeg <= 0 用默认幅度；都不会超过 amp(id)。上一个动作没做完时新的直接丢掉
void gesture(const char *name, int times = 1, float ampDeg = 0, float holdS = 0);
void tick();
bool busy();
void nod();   // = gesture("nod", 1, 8)
// 重新定基准：ID2（转头）先把当前位置校正成 2048，转 deg 度，再把那里校正成 2048。
// 只需要做一次（舵机把偏移存在自己的 EEPROM 里）；开机时用 NVS 记一下做过没有
void rebaseYaw(float deg = 10);   // deg > 0：位置增大；deg < 0：位置减小（开机第一下的方向）
}
