// 音频：MAX98357A 功放（喇叭）+ INMP441 麦克风，共用一个 I2S（全双工，16 kHz）。
// 引脚（共用时钟）：BCLK 12 · WS/LRC 13 · 喇叭 DIN 11 · 麦克风 SD 38。喇叭是 1 W / 8 Ω，音量默认压得很低。
#pragma once
#include <Arduino.h>

namespace audio {

bool begin();
// 播放一个正弦音；vol 0–1（相对满幅）。默认 0.08 ≈ 十几毫瓦，对 1 W 喇叭很安全
void tone(float freq, int ms, float vol = 0.08f);
// 播一段 16 kHz 单声道 16 位 PCM（vol 0–0.3）
void playPcm(const int16_t *pcm, int n, float vol = 0.15f);
// 开机小旋律（拨弦音）
void chime(float vol = 0.08f);
// 测试语音：「你好，我是 DeskBot，喇叭测试成功。」
void hello(float vol = 0.15f);
// 读 ms 毫秒麦克风，返回去掉直流后的 RMS（24 位采样的计数）；peak 可选
float micRms(int ms, float *peak = nullptr);
// 开机自检：静音时的底噪 → 播一声 → 播放时麦克风有没有"听到"；结果写串口和日志
void selfTest();

}  // namespace audio
