// 舵机自检：ping ID1 / ID2，读位置、电压、温度，然后每个舵机在当前位置附近 ±10° 小幅度来回一次，最后放松扭矩。
// 接线：TX GPIO21 → 约 3.3 kΩ → DATA；RX GPIO47 → 约 5 kΩ → DATA；舵机 12 V 单独供电，和板子共地。
#pragma once
#include <stdint.h>

namespace servotest {
void run();
// 舵机允许的单边摆幅（步数）：ID1 ±20°，ID2 ±10°。所有动作都不能超出开机摆动的范围
int amp(uint8_t id);
// 只让一个舵机在当前位置附近来回摆 times 次（±10°），方便肉眼确认是哪一个在动
void wiggle(uint8_t id, int times);   // 摆幅 = amp(id)
// 点一下头：俯仰舵机（ID2）往下 ~8° 再回来，约 0.6 秒；30% 扭矩，点完放松
void nod();
// 重新定基准：ID2 先把当前位置校正成 2048，往「开机摆动第一下的反方向」（位置增大）转 10°，再把那里校正成 2048。
// 只需要做一次（舵机把偏移存在自己的 EEPROM 里）；开机时用 NVS 记一下做过没有
void rebasePitch(float deg = 10);   // deg：往位置增大的方向转多少度（负数 = 和开机第一下同方向），再把那里定为 2048
}
