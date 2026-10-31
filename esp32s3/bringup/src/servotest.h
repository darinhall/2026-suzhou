// 舵机自检：ping ID1 / ID2，读位置、电压、温度，然后每个舵机在当前位置附近 ±10° 小幅度来回一次，最后放松扭矩。
// 接线：TX GPIO21 → 约 3.3 kΩ → DATA；RX GPIO47 → 约 5 kΩ → DATA；舵机 12 V 单独供电，和板子共地。
#pragma once
#include <stdint.h>

namespace servotest {
void run();
// 只让一个舵机在当前位置附近来回摆 times 次（±10°），方便肉眼确认是哪一个在动
void wiggle(uint8_t id, int times);
// 点一下头：俯仰舵机（ID2）往下 ~8° 再回来，约 0.6 秒；30% 扭矩，点完放松
void nod();
}
