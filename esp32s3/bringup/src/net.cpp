#include "net.h"

#include <Preferences.h>
#include <WebSocketsClient.h>
#include <WiFi.h>
#include <WiFiUdp.h>

#include "deskbot_net.h"   // WiFi 名 / 密码、端口、发现协议、令牌（config/build_net.py 生成）
#include "ui.h"

#define FW_VERSION "0.2.0"

namespace net {

static WebSocketsClient ws;
static WiFiUDP udp;
static Preferences prefs;
static MessageCb onMsg = nullptr;

enum class Phase { Wifi, Discover, Ws };
static Phase phase = Phase::Wifi;
static String hubHost, hubPath = DB_HUB_WS_PATH;
static uint16_t hubPort = DB_HUB_WS_PORT;
static uint32_t lastTry = 0;
static int tries = 0, wsFails = 0;
static bool wsUp = false;

static void onWsEvent(WStype_t type, uint8_t *payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED: {
      wsUp = true;
      wsFails = 0;
      ws.setReconnectInterval(2000);
      JsonDocument d;   // 第一条必须是 hello，5 秒内
      d["t"] = "hello";
      d["role"] = "face";
      d["fw"] = FW_VERSION;
      if (strlen(DB_HUB_TOKEN)) d["token"] = DB_HUB_TOKEN;
      String out;
      serializeJson(d, out);
      ws.sendTXT(out);
      ui::status("");
      Serial.printf("[ws] 已连上中枢 %s:%u\n", hubHost.c_str(), hubPort);
      break;
    }
    case WStype_DISCONNECTED:
      if (wsUp) Serial.println("[ws] 断开");
      wsUp = false;
      wsFails++;
      // 令牌错误连续 5 次会被中枢锁 30 秒：失败几次之后放慢重连，别去撞
      if (wsFails == 3) ws.setReconnectInterval(31000);
      break;
    case WStype_TEXT: {
      JsonDocument d;
      if (!deserializeJson(d, payload, length) && onMsg) onMsg(d);
      break;
    }
    default: break;
  }
}

static void startWs() {
  ws.disconnect();
  ws.begin(hubHost.c_str(), hubPort, hubPath.c_str());
  ws.onEvent(onWsEvent);
  ws.setReconnectInterval(2000);
  ws.enableHeartbeat(15000, 4000, 2);
  phase = Phase::Ws;
  wsFails = 0;
}

// 广播 {"t":"deskbot?"}，等回复；回复包的源 IP 就是中枢的地址
static bool discoverOnce() {
  const IPAddress targets[2] = {IPAddress((uint32_t)WiFi.localIP() | ~(uint32_t)WiFi.subnetMask()),   // 子网广播（有 VPN 的 Mac 上只有它能出去）
                                IPAddress(255, 255, 255, 255)};
  for (const IPAddress &t : targets) {
    udp.beginPacket(t, DB_DISCOVERY_PORT);
    udp.print(DB_DISCOVERY_QUERY);
    udp.endPacket();
  }
  for (uint32_t until = millis() + 900; millis() < until; delay(10)) {
    const int n = udp.parsePacket();
    if (n <= 0) continue;
    char buf[256];
    const int r = udp.read(buf, min(n, 255));
    buf[r] = 0;
    JsonDocument d;
    if (deserializeJson(d, buf) == DeserializationError::Ok && String(d["t"] | "") == "hub") {
      hubHost = udp.remoteIP().toString();
      hubPort = d["ws_port"] | DB_HUB_WS_PORT;
      hubPath = String(d["path"] | DB_HUB_WS_PATH);
      return true;
    }
  }
  return false;
}

void begin(MessageCb cb) {
  onMsg = cb;
  prefs.begin("deskbot", false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);   // 不省电，换低延迟
  WiFi.setAutoReconnect(true);
  WiFi.begin(DB_WIFI_SSID, DB_WIFI_PASS);
  Serial.printf("[wifi] 连接 %s …\n", DB_WIFI_SSID);
  ui::status("wifi...");
}

void loop() {
  const uint32_t now = millis();

  if (WiFi.status() != WL_CONNECTED) {
    if (phase != Phase::Wifi) {
      phase = Phase::Wifi;
      wsUp = false;
      ws.disconnect();
      ui::status("wifi...");
      Serial.println("[wifi] 断了");
    }
    static uint32_t lastLog = 0;
    if (now - lastLog > 5000) {
      lastLog = now;
      Serial.printf("[wifi] 状态 %d（1=没找到 4=连接失败 6=断开）\n", (int)WiFi.status());
      static bool scanned = false;
      if (!scanned && now > 12000) {   // 一直找不到：扫一遍，看板子到底看见了什么
        scanned = true;
        const int n = WiFi.scanNetworks();
        Serial.printf("[wifi] 扫到 %d 个：\n", n);
        for (int i = 0; i < n && i < 12; i++) Serial.printf("  %-24s ch%-2d %d dBm\n", WiFi.SSID(i).c_str(), WiFi.channel(i), WiFi.RSSI(i));
      }
    }
    if (now - lastTry > 20000) {   // 20 秒还没连上就重来一次
      lastTry = now;
      WiFi.disconnect();
      WiFi.begin(DB_WIFI_SSID, DB_WIFI_PASS);
    }
    return;
  }

  if (phase == Phase::Wifi) {
    phase = Phase::Discover;
    tries = 0;
    lastTry = 0;
    Serial.printf("[wifi] 已连接 · IP %s · 信号 %d dBm · 网关 %s\n", WiFi.localIP().toString().c_str(), WiFi.RSSI(), WiFi.gatewayIP().toString().c_str());
    ui::status("hub...");
    udp.begin(DB_DISCOVERY_PORT + 1);
    configTime(8 * 3600, 0, "ntp.aliyun.com", "pool.ntp.org");   // 老板键的时钟要用
  }

  if (phase == Phase::Discover && now - lastTry > 1000) {
    lastTry = now;
    tries++;
    if (discoverOnce()) {
      Serial.printf("[hub] 发现 %s:%u%s\n", hubHost.c_str(), hubPort, hubPath.c_str());
      prefs.putString("hub", hubHost);
      startWs();
    } else if (tries == 5) {
      const String saved = prefs.getString("hub", "");
      if (saved.length()) {
        Serial.printf("[hub] 广播没人应，试上次的 %s\n", saved.c_str());
        hubHost = saved;
        startWs();
      }
    } else if (tries % 10 == 0) {
      Serial.println("[hub] 还在找中枢…（电脑上起了 ./hub/run.sh 吗？同一个 WiFi 吗？）");
    }
  }

  if (phase == Phase::Ws) {
    ws.loop();
    if (!wsUp && wsFails >= 3 && now - lastTry > 5000) {   // 连不上：中枢可能换了地址，回去重新发现
      lastTry = now;
      phase = Phase::Discover;
      tries = 0;
      ws.disconnect();
      Serial.println("[ws] 连不上，重新发现中枢");
    }
  }
}

bool connected() { return wsUp; }

static void sendJson(const JsonDocument &d) {
  String out;
  serializeJson(d, out);
  ws.sendTXT(out);
}

void sendTouch(int x, int y) {
  if (!wsUp) return;
  JsonDocument d;
  d["t"] = "touch";
  d["x"] = x;
  d["y"] = y;
  sendJson(d);
}

void sendBoss(bool on) {
  if (!wsUp) return;
  JsonDocument d;
  d["t"] = "boss";
  d["on"] = on;
  sendJson(d);
}

}  // namespace net
