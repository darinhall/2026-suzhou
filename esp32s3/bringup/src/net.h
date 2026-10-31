// WiFi → UDP 发现中枢 → WebSocket（第一条 hello 带令牌）。协议见《双板方案》。
#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>

namespace net {

using MessageCb = void (*)(JsonDocument &doc);

void begin(MessageCb onMessage);
void loop();
bool connected();
void sendTouch(int x, int y);
void sendBoss(bool on);
// 日志：连着中枢就立刻发；没连上先存在环形缓冲里（最近 16 条），连上后补发。lvl: info / warn / error
void log(const char *lvl, const char *code, const char *msg);

}  // namespace net
