// DeskBot 的身体 · ESP32 + 两个飞特 ST3215。
// 连 WiFi → 找中枢 → hello(role=body) → 收 pose / gesture / torque，上报 head_press / state。
// 脸在另一块板（esp32s3/bringup），两块板各自连中枢，互相不直接通信。

#include <Arduino.h>

#include "motion.h"
#include "net.h"

static void onMessage(JsonDocument &d) {
  const char *t = d["t"] | "";
  if (!strcmp(t, "pose")) {
    motion::pose(d["yaw"] | 0.0f, d["pitch"] | 0.0f, d["ms"] | 500);
  } else if (!strcmp(t, "gesture")) {
    const char *name = d["name"] | "";
    if (!motion::gesture(name, d["times"] | 1)) net::log("warn", "GESTURE_UNKNOWN", name);
  } else if (!strcmp(t, "torque")) {
    motion::torque(d["pct"] | 50);
  }
  // 其他消息（face / audio / peers / notice / logs…）和身体无关，忽略
}

void setup() {
  Serial.begin(115200);
  delay(400);
  Serial.println("\n[body] 启动");
  net::begin(onMessage);
  motion::begin();
  char m[64];
  snprintf(m, sizeof m, "开机 fw " FW_VERSION " · 复位原因 %d", (int)esp_reset_reason());
  net::log("info", "BOOT", m);
}

void loop() {
  const uint32_t now = millis();
  net::loop();
  motion::tick(now);
}
