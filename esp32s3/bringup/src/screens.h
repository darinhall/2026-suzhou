// 文字屏（盯盘 watch、单股 mkt、起床后 today）：按设计系统 C 专业密度，先整屏画进 PSRAM 里的 sprite，再一次推上屏，不闪。
// 版面坐标来自 数据清单.md §5；颜色来自 design/deskbot_tokens.h（米黄）。
#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>

namespace screens {

bool begin(TFT_eSPI *tft);                              // 映射 fonts 分区 + 分配整屏 sprite
bool handles(const char *state);                        // watch / mkt / today
bool show(const char *state, JsonVariantConst card);    // 画并推上屏；不认识的状态返回 false
void setMode(const char *mode, bool save = true);   // simple / compact / pro，存进 NVS，重画当前卡片
const char *mode();
// 触摸：盯盘列表里点了哪一行？返回那只股票的 mkt 详情卡（用这一行自带的数据拼成；没点中行返回 false）
bool openRowAt(int x, int y, JsonDocument &outCard, char *code, size_t codeLen);
void store(const char *state, JsonVariantConst card);   // 只记下，不画（老板键开着时）
void redraw();                                          // 上一张卡片重画（老板键退出后用）
void setScene(const char *name, int page, int of, const char *clock);   // 状态条右边的页码点、回放时钟
// 在别的 sprite 上用中文字体写一行（熊猫脸"想一想"时显示听到的话）。居中在 cx，顶在 y
void caption(TFT_eSprite *spr, const char *text, int cx, int y, uint32_t fg, uint32_t bg);

}  // namespace screens
