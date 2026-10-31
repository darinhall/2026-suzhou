#include "net.h"

#include <Preferences.h>
#include <WebSocketsClient.h>
#include <WiFi.h>
#include <WiFiUdp.h>

#include "deskbot_net.h"   // WiFi 名 / 密码、端口、发现协议、令牌（config/build_net.py 生成）

#ifndef DB_ROLE
#define DB_ROLE "face"     // 固件在 platformio.ini 里用 -DDB_ROLE=\"body\" 换身份
#endif
#ifndef FW_VERSION
#define FW_VERSION "0.2.0"
#endif

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

#ifndef DB_AP_SSID
#define DB_AP_SSID "DeskBot-Demo"     // 最后的退路：板子自己开一个热点，Mac 直接连它（不依赖场馆 Wi-Fi / 手机热点）
#define DB_AP_PASS "deskbot1234"
#endif
static bool apMode = false;
static bool linkUp() { return WiFi.status() == WL_CONNECTED || (apMode && WiFi.softAPgetStationNum() > 0); }


// ---------- 日志 ----------
struct LogItem { char lvl[6], code[24], msg[96]; uint32_t up; };
static LogItem pend[16];
static int pendN = 0;

static void sendLog(const LogItem &it) {
  JsonDocument d;
  d["t"] = "log";
  d["lvl"] = it.lvl;
  d["src"] = DB_ROLE;
  d["code"] = it.code;
  d["msg"] = it.msg;
  d["up"] = it.up;   // 开机后的毫秒数：补发的旧日志靠它排先后
  String out;
  serializeJson(d, out);
  ws.sendTXT(out);
}

void log(const char *lvl, const char *code, const char *msg) {
  Serial.printf("[%s] %s %s\n", lvl, code, msg);
  LogItem it;
  strlcpy(it.lvl, lvl, sizeof it.lvl);
  strlcpy(it.code, code, sizeof it.code);
  strlcpy(it.msg, msg, sizeof it.msg);
  it.up = millis();
  if (wsUp) { sendLog(it); return; }
  if (pendN == 16) { memmove(pend, pend + 1, sizeof(LogItem) * 15); pendN = 15; }   // 满了丢最旧的
  pend[pendN++] = it;
}

static void flushLogs() {
  for (int i = 0; i < pendN; i++) sendLog(pend[i]);
  pendN = 0;
}

static void onWsEvent(WStype_t type, uint8_t *payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED: {
      wsUp = true;
      wsFails = 0;
      ws.setReconnectInterval(2000);
      JsonDocument d;   // 第一条必须是 hello，5 秒内
      d["t"] = "hello";
      d["role"] = DB_ROLE;
      d["fw"] = FW_VERSION;
      if (strlen(DB_HUB_TOKEN)) d["token"] = DB_HUB_TOKEN;
      String out;
      serializeJson(d, out);
      ws.sendTXT(out);
      Serial.printf("[ws] 已连上中枢 %s:%u\n", hubHost.c_str(), hubPort);
      flushLogs();
      { char m[64]; snprintf(m, sizeof m, "已连上中枢 %s:%u", hubHost.c_str(), hubPort); log("info", "WS_UP", m); }
      break;
    }
    case WStype_DISCONNECTED:
      if (wsUp) {
        wsUp = false;
        char m[96];
        snprintf(m, sizeof m, "和中枢的连接断了，自动重连（WiFi %s，%d dBm，空闲堆 %u KB）", WiFi.status() == WL_CONNECTED ? "在线" : "已断", (int)WiFi.RSSI(), ESP.getFreeHeap() / 1024);
        log("warn", "WS_DOWN", m);
      }
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
#ifdef DB_HUB_CLOUD_HOST
  ws.beginSSL(hubHost.c_str(), hubPort, hubPath.c_str());   // 云端中枢走 wss（nginx + Let's Encrypt）；不校验证书，只要加密
#else
  ws.begin(hubHost.c_str(), hubPort, hubPath.c_str());
#endif
  ws.onEvent(onWsEvent);
  ws.setReconnectInterval(2000);
  ws.enableHeartbeat(20000, 15000, 3);   // 弱信号下回包慢：15 秒内没收到 pong 才算一次失败，连续 3 次才断
  phase = Phase::Ws;
  wsFails = 0;
}

// 广播 {"t":"deskbot?"}，等回复；回复包的源 IP 就是中枢的地址
static bool discoverOnce() {
  const bool viaAp = apMode && WiFi.status() != WL_CONNECTED;
  const IPAddress targets[2] = {viaAp ? IPAddress((uint32_t)WiFi.softAPIP() | ~(uint32_t)WiFi.softAPSubnetMask()) : IPAddress((uint32_t)WiFi.localIP() | ~(uint32_t)WiFi.subnetMask()),   // 子网广播（有 VPN 的 Mac 上只有它能出去）
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

// 现场同一个 SSID 有很多 AP，板子天线又弱：自己扫一遍（每个信道多停一会儿，不漏 beacon），
// 挑信号最强的那个，按信道 + BSSID 去连，比让系统"边扫边连"快得多也稳得多。
static bool scanning = false;

// 异步扫描：扫的时候主循环照常跑（触摸、动画不能被 5 秒的阻塞扫描卡住）
static void startScan() {
  WiFi.scanDelete();
  WiFi.scanNetworks(true, true, false, 350);
  scanning = true;
}

static void joinBest(int n) {
  for (int i = 0; i < n && i < 40; i++) {   // 调试：信号 > -50 dBm 的 AP，连 SSID 的原始字节一起打出来（热点名字对不上时看这个）
    if (WiFi.RSSI(i) < -50) continue;
    String ss = WiFi.SSID(i), hx;
    for (size_t k = 0; k < ss.length() && k < 20; k++) { char b[4]; snprintf(b, sizeof b, "%02X", (uint8_t)ss[k]); hx += b; }
    Serial.printf("[scan] ch%d %d dBm len=%u hex=%s\n", (int)WiFi.channel(i), (int)WiFi.RSSI(i), (unsigned)ss.length(), hx.c_str());
  }
  // 配了备用热点（你自己的手机）且扫得到，就优先连它：现场 NAMI-guest 在 2.4 GHz 上又弱又不稳
  bool fbAvailable = false;
#ifdef DB_WIFI_FB1_SSID
  for (int i = 0; i < n; i++) fbAvailable |= WiFi.SSID(i) == DB_WIFI_FB1_SSID;
#endif
  int best = -1;
  for (int i = 0; i < n; i++)
    if (WiFi.SSID(i) == DB_WIFI_SSID && (best < 0 || WiFi.RSSI(i) > WiFi.RSSI(best))) best = i;
  if (best >= 0 && !fbAvailable) {
    char m[80];
    snprintf(m, sizeof m, "扫到 %d 个 AP，选信道 %d 信号 %d dBm 的", n, (int)WiFi.channel(best), (int)WiFi.RSSI(best));
    Serial.printf("[wifi] %s\n", m);
    WiFi.begin(DB_WIFI_SSID, DB_WIFI_PASS, WiFi.channel(best), WiFi.BSSID(best));
  } else {
    const char *fbSsid[2] = {
#ifdef DB_WIFI_FB1_SSID
      DB_WIFI_FB1_SSID,
#else
      nullptr,
#endif
#ifdef DB_WIFI_FB2_SSID
      DB_WIFI_FB2_SSID,
#else
      nullptr,
#endif
    };
    const char *fbPass[2] = {
#ifdef DB_WIFI_FB1_PASS
      DB_WIFI_FB1_PASS,
#else
      "",
#endif
#ifdef DB_WIFI_FB2_PASS
      DB_WIFI_FB2_PASS,
#else
      "",
#endif
    };
    for (int k = 0; k < 2; k++) {   // 主 WiFi 扫不到：试备用热点
      if (!fbSsid[k]) continue;
      for (int i = 0; i < n; i++)
        if (WiFi.SSID(i) == fbSsid[k]) {
          char m[80];
          snprintf(m, sizeof m, "连备用热点 %s（%d dBm）", fbSsid[k], (int)WiFi.RSSI(i));
          log("warn", "WIFI_FALLBACK", m);
          WiFi.begin(fbSsid[k], fbPass[k], WiFi.channel(i), WiFi.BSSID(i));
          WiFi.scanDelete();
          return;
        }
    }
    Serial.printf("[wifi] 扫到 %d 个 AP，没有 %s：\n", n, DB_WIFI_SSID);
    for (int i = 0; i < n && i < 10; i++) Serial.printf("  %-24s ch%-2d %d dBm\n", WiFi.SSID(i).c_str(), (int)WiFi.channel(i), (int)WiFi.RSSI(i));
    static uint32_t lastWarn = 0;
    if (!lastWarn || millis() - lastWarn > 60000) {
      lastWarn = millis();
      log("warn", "WIFI_NOT_FOUND", "扫描不到 " DB_WIFI_SSID "（只支持 2.4 GHz，离路由近一点）");
    }
    // 扫描里哪个都没匹配上：热点可能是隐藏的 / 刚好没扫到。交替直接按名字连（定向探测，隐藏 SSID 也连得上）
    static bool tryFallback = true;
    if (fbSsid[0] && tryFallback) {
      // 手机热点有时 SSID 不广播（扫出来是空名字）：挑信号最强的"空名字"AP，用它的信道 + BSSID + 备用热点的名字去连
      int hidden = -1;
      for (int i = 0; i < n; i++)
        if (WiFi.SSID(i).length() == 0 && (hidden < 0 || WiFi.RSSI(i) > WiFi.RSSI(hidden))) hidden = i;
      if (hidden >= 0) {
        Serial.printf("[wifi] 扫描没看到名字，试最强的隐藏 AP（信道 %d，%d dBm）按备用热点 %s 连\n", (int)WiFi.channel(hidden), (int)WiFi.RSSI(hidden), fbSsid[0]);
        WiFi.begin(fbSsid[0], fbPass[0], WiFi.channel(hidden), WiFi.BSSID(hidden));
      } else {
        Serial.printf("[wifi] 扫描没看到，直接按名字连备用热点 %s\n", fbSsid[0]);
        WiFi.begin(fbSsid[0], fbPass[0]);
      }
    } else {
      WiFi.begin(DB_WIFI_SSID, DB_WIFI_PASS);
    }
    tryFallback = !tryFallback;
  }
  WiFi.scanDelete();
}

void begin(MessageCb cb) {
  onMsg = cb;
  prefs.begin("deskbot", false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);   // 不省电，换低延迟
  WiFi.setTxPower(WIFI_POWER_19_5dBm);   // 发射功率拉满：信号弱的地方，上行也是瓶颈
  WiFi.setScanMethod(WIFI_ALL_CHANNEL_SCAN);          // 现场同一个 SSID 有很多个 AP：扫完所有信道，挑信号最强的，
  WiFi.setSortMethod(WIFI_CONNECT_AP_BY_SIGNAL);      // 而不是连上第一个扫到的（可能是远处那个，连得慢甚至连不上）
  WiFi.setAutoReconnect(true);
  Serial.printf("[wifi] 连接 %s …\n", DB_WIFI_SSID);
  startScan();
}

void loop() {
  const uint32_t now = millis();

  if (scanning) {   // 扫完了就挑最强的 AP 去连
    const int n = WiFi.scanComplete();
    if (n != WIFI_SCAN_RUNNING) { scanning = false; lastTry = now; joinBest(n < 0 ? 0 : n); }
  }

  if (!apMode && now > 45000 && WiFi.status() != WL_CONNECTED) {   // 开机 45 秒还没连上任何 Wi-Fi：自己开热点
    apMode = true;
    WiFi.mode(WIFI_AP_STA);
    WiFi.softAP(DB_AP_SSID, DB_AP_PASS, 6, 0, 4);
    Serial.printf("[wifi] 没连上任何 Wi-Fi，板子自己开了热点 %s（密码 %s），把 Mac 连上去\n", DB_AP_SSID, DB_AP_PASS);
    log("warn", "WIFI_AP_ON", "没连上任何 Wi-Fi，已开热点 " DB_AP_SSID "：Mac 连它，中枢在 192.168.4.2");
  }

  if (!linkUp()) {
    if (phase != Phase::Wifi) {
      phase = Phase::Wifi;
      wsUp = false;
      ws.disconnect();
      log("warn", "WIFI_LOST", "WiFi 断了，重新连接");
    }
    static uint32_t lastLog = 0;
    if (now - lastLog > 5000) {
      lastLog = now;
      Serial.printf("[wifi] 状态 %d（1=没找到 4=连接失败 6=断开）\n", (int)WiFi.status());
    }
    if (now - lastTry > (apMode ? 40000 : 12000)) {   // 12 秒还没连上就重来一次（开了自己的热点后放慢：扫描会打断热点上的客户端）
      lastTry = now;
      WiFi.disconnect();
      if (!scanning) startScan();
    }
    return;
  }

  if (phase == Phase::Wifi) {
    phase = Phase::Discover;
    tries = 0;
    lastTry = 0;
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("[wifi] 已连接 · IP %s · 信号 %d dBm · 网关 %s\n", WiFi.localIP().toString().c_str(), WiFi.RSSI(), WiFi.gatewayIP().toString().c_str());
      { char m[80]; snprintf(m, sizeof m, "WiFi 已连接 IP %s，信号 %d dBm", WiFi.localIP().toString().c_str(), WiFi.RSSI()); log("info", "WIFI_OK", m); }
    } else {
      Serial.println("[wifi] 热点上有客户端了（直连模式）");
    }
    configTime(8 * 3600, 0, "ntp.aliyun.com", "pool.ntp.org");   // 老板键的时钟要用
#ifdef DB_HUB_CLOUD_HOST
    hubHost = DB_HUB_CLOUD_HOST;   // 只用云端中枢：不广播、不找局域网里的电脑
    hubPort = DB_HUB_CLOUD_PORT;
    hubPath = DB_HUB_WS_PATH;
    Serial.printf("[hub] 连云端 wss://%s:%u%s\n", hubHost.c_str(), hubPort, hubPath.c_str());
    startWs();
#else
    udp.begin(DB_DISCOVERY_PORT + 1);
#endif
  }

  if (phase == Phase::Discover && now - lastTry > 1000) {
    lastTry = now;
    tries++;
    if (discoverOnce()) {
      { char m[64]; snprintf(m, sizeof m, "发现中枢 %s:%u", hubHost.c_str(), hubPort); log("info", "HUB_FOUND", m); }
      prefs.putString("hub", hubHost);
      startWs();
    } else if (tries == 3 && apMode && WiFi.status() != WL_CONNECTED) {
      hubHost = "192.168.4.2";   // 板子自己的热点里，第一个连上来的客户端就是 192.168.4.2（Mac）
      Serial.println("[hub] 直连模式：直接试 192.168.4.2");
      startWs();
    } else if (tries == 5) {
      const String saved = prefs.getString("hub", "");
      if (saved.length()) {
        Serial.printf("[hub] 广播没人应，试上次的 %s\n", saved.c_str());
        hubHost = saved;
        startWs();
      }
    } else if (tries % 10 == 0) {
      log("warn", "HUB_NOT_FOUND", "还在找中枢：电脑上起了 ./hub/run.sh 吗？同一个 WiFi 吗？");
    }
  }

  if (phase == Phase::Ws) {
    ws.loop();
#ifndef DB_HUB_CLOUD_HOST   // 云端地址固定：WebSocketsClient 自己会一直重连，不用回去重新发现
    if (!wsUp && wsFails >= 3 && now - lastTry > 5000) {   // 连不上：中枢可能换了地址，回去重新发现
      lastTry = now;
      phase = Phase::Discover;
      tries = 0;
      ws.disconnect();
      log("warn", "WS_DOWN", "连不上中枢，重新发现（令牌不对会被锁 30 秒）");
    }
#endif
  }
}

bool connected() { return wsUp; }

void send(const JsonDocument &d) {
  if (!wsUp) return;
  String out;
  serializeJson(d, out);
  ws.sendTXT(out);
}

static void sendJson(const JsonDocument &d) { send(d); }

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
