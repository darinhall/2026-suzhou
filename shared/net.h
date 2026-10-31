// 脸（esp32s3/bringup）和身体（body）共用。DB_ROLE 决定 hello 里报的身份。
// WiFi → UDP 发现中枢 → WebSocket（第一条 hello 带令牌）。协议见《双板方案》。
#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>

namespace net {

using MessageCb = void (*)(JsonDocument &doc);
using BinaryCb = void (*)(const uint8_t *data, size_t n);

void begin(MessageCb onMessage);
void loop();
bool connected();
void send(const JsonDocument &doc);   // 任意上行消息（没连上就丢）
bool sendBin(const uint8_t *data, size_t n);   // 二进制帧（麦克风音频）
void onBinary(BinaryCb cb);                    // 收到二进制帧（喇叭音频）
void sendTouch(int x, int y);
void sendBoss(bool on);
// 日志：连着中枢就立刻发；没连上先存在环形缓冲里（最近 16 条），连上后补发。lvl: info / warn / error
void log(const char *lvl, const char *code, const char *msg);

}  // namespace net
