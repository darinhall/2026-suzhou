// 这块 3.5″ 屏的白点偏冷：设计系统的米黄（#F1E8D2）显示出来发蓝。拍照对比 8 个候选后，#F7E2A8 最像模拟器里的米黄。
// 所以所有颜色在画出去之前统一做一次校正：红 ×1.025、绿 ×0.982、蓝 ×0.80（黑色仍是黑色，设计系统 tokens 不动）。
#pragma once
#include <stdint.h>

static inline uint32_t devColor(uint32_t h) {
  const uint32_t r = min<uint32_t>(255, ((h >> 16) & 255) * 1025 / 1000);
  const uint32_t g = ((h >> 8) & 255) * 982 / 1000;
  const uint32_t b = (h & 255) * 800 / 1000;
  return (r << 16) | (g << 8) | b;
}
