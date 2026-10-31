// 屏幕上画的东西：设计系统（light）的表情和几种不需要中文的屏。尺寸照 sim/screen.css 的 3.5″ 480×320。
// 文字屏（消息、行情、今天、天气）要中文字体，下一步用 LVGL 做；现在遇到就画待机脸 + 状态名。
#pragma once
#include <Arduino.h>
#include <TFT_eSPI.h>

namespace ui {

enum class State { Idle, Blink, Happy, Listening, Thinking, Ok, Stealth, Play, Sleep, Unsupported };

void begin(TFT_eSPI *tft);
void set(State s, int count = 0, float pct = 0, float vol = 0.3f, bool alert = false, const char *label = nullptr);
void status(const char *line);      // 屏幕底部一行小字（只给启动阶段用：wifi… / hub…），"" 清掉
void tick(uint32_t now);            // 眨眼、波形、点点的动画
void setLink(bool ok);              // 右上角连接图标：连上中枢 = 实心，没连上 = 淡色 + 斜线
void poke();                        // 有人动过它：待机计时重新开始
void wake();                        // 摸一下：玩球 / 睡觉都醒过来（睡着的会被吓一跳）
void setBoss(bool on);              // 老板键：伪装成办公助手的时钟
bool boss();

}  // namespace ui
