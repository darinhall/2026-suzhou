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

}  // namespace net
