#include "screens.h"

#include <esp_partition.h>
#include <time.h>

#include <Preferences.h>

#include "deskbot_tokens.h"
#include "palette.h"

namespace screens {

static TFT_eSPI *T;
static TFT_eSprite *fb = nullptr;

// ---------- 字体：fonts 分区 mmap 成数组 ----------
enum Fnt { CJK12, CJK15, CJK17, M12, M15, M17, M44, MB15, CJK14, CJK18, CJK26, M14, M18, M26, M56, NFONT };
static const char *FONT_NAME[NFONT] = {"cjk12", "cjk15", "cjk17", "mono12", "mono15", "mono17", "mono44", "monob15", "cjk14", "cjk18", "cjk26", "mono14", "mono18", "mono26", "mono56"};
static const uint8_t *fontPtr[NFONT] = {};
struct FontEntry { char name[16]; uint32_t off, size; };

static void mapFonts() {
  const esp_partition_t *part = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_SPIFFS, "fonts");
  if (!part) { Serial.println("[font] 没有 fonts 分区"); return; }
  const void *ptr;
  spi_flash_mmap_handle_t h;
  if (esp_partition_mmap(part, 0, part->size, SPI_FLASH_MMAP_DATA, &ptr, &h) != ESP_OK) { Serial.println("[font] mmap 失败"); return; }
  const uint8_t *base = (const uint8_t *)ptr;
  if (memcmp(base, "DBF1", 4)) { Serial.println("[font] fonts 分区是空的：烧 fonts.bin（esp32s3/tools/pack_fonts.py）"); return; }
  const int n = *(const uint32_t *)(base + 4);
  for (int i = 0; i < n; i++) {
    const FontEntry *e = (const FontEntry *)(base + 8) + i;
    for (int f = 0; f < NFONT; f++)
      if (!strncmp(e->name, FONT_NAME[f], 16)) fontPtr[f] = base + e->off;
  }
  Serial.printf("[font] %d 个字体已映射\n", n);
}

// ---------- 颜色 ----------
static uint16_t C(uint32_t h) { h = devColor(h); return T->color565((h >> 16) & 255, (h >> 8) & 255, h & 255); }
static uint16_t mix(uint32_t a, uint32_t b, float t) {
  a = devColor(a); b = devColor(b);
  auto ch = [&](int sh) { return (int)(((a >> sh) & 255) * (1 - t) + ((b >> sh) & 255) * t); };
  return T->color565(ch(16), ch(8), ch(0));
}
#define GROUND DB_LIGHT_GROUND
#define SURFACE DB_LIGHT_SURFACE
#define INK DB_LIGHT_INK
#define MUTED DB_LIGHT_INK_MUTED
#define FAINT DB_LIGHT_INK_FAINT
#define RULE DB_LIGHT_RULE
#define ACCENT DB_LIGHT_ACCENT
#define CARD DB_LIGHT_CARD
#define ON_CARD DB_LIGHT_ON_CARD
#define ON_CARD_MUTED DB_LIGHT_ON_CARD_MUTED
#define UPC DB_LIGHT_UP
#define DOWNC DB_LIGHT_DOWN
#define UPC_ON_CARD DB_LIGHT_UP_ON_CARD
#define DOWNC_ON_CARD DB_LIGHT_DOWN_ON_CARD

static uint32_t dirColor(float pct, bool onCard = false) {
  if (pct > 0) return onCard ? UPC_ON_CARD : UPC;
  if (pct < 0) return onCard ? DOWNC_ON_CARD : DOWNC;
  return onCard ? ON_CARD_MUTED : MUTED;
}

// ---------- 文字操作队列：按字体分组画，每个字体只加载一次 ----------
struct Op { uint8_t f, datum; int16_t x, y; uint32_t fg, bg; char s[56]; };
static Op ops[200];
static int nops = 0;

static void txt(Fnt f, int x, int y, uint8_t datum, uint32_t fg, uint32_t bg, const char *s) {
  if (nops >= 200 || !s || !*s) return;
  Op &o = ops[nops++];
  o.f = f; o.x = x; o.y = y; o.datum = datum; o.fg = fg; o.bg = bg;
  strlcpy(o.s, s, sizeof o.s);
}
static void txtf(Fnt f, int x, int y, uint8_t datum, uint32_t fg, uint32_t bg, const char *fmt, ...) {
  char b[56];
  va_list ap; va_start(ap, fmt); vsnprintf(b, sizeof b, fmt, ap); va_end(ap);
  txt(f, x, y, datum, fg, bg, b);
}

static void flush() {
  for (int f = 0; f < NFONT; f++) {
    bool any = false;
    for (int i = 0; i < nops; i++) any |= ops[i].f == f;
    if (!any) continue;
    const bool loaded = fontPtr[f];
    if (loaded) fb->loadFont(fontPtr[f]);
    for (int i = 0; i < nops; i++) {
      if (ops[i].f != f) continue;
      fb->setTextDatum(ops[i].datum);
      fb->setTextColor(C(ops[i].fg), C(ops[i].bg));
      if (loaded) fb->drawString(ops[i].s, ops[i].x, ops[i].y);
      else fb->drawString(ops[i].s, ops[i].x, ops[i].y, 2);   // 字体没烧进去：退回内置字体，至少看得见
    }
    if (loaded) fb->unloadFont();
  }
  nops = 0;
}

// ---------- 小部件 ----------
static void tri(int x, int y, bool up, uint32_t color) {   // 8×7 的 ▲ / ▼，(x,y) 是左上角
  if (up) fb->fillTriangle(x, y + 7, x + 8, y + 7, x + 4, y, C(color));
  else fb->fillTriangle(x, y, x + 8, y, x + 4, y + 7, C(color));
}

static void chip(int x, int y, const char *s, int w, bool accent = false, Fnt f = CJK12, int h = 16) {   // 圆角描边标签
  fb->drawRoundRect(x, y, w, h, h / 2, C(accent ? ACCENT : RULE));
  if (accent) fb->fillRoundRect(x, y, w, h, h / 2, C(ACCENT));
  txt(f, x + w / 2, y + (h - (f == CJK14 ? 14 : 12)) / 2 - 1, TC_DATUM, accent ? DB_LIGHT_ON_ACCENT : INK, accent ? ACCENT : GROUND, s);
}

static void sampleTag(int x, int y) {   // 虚线框的「示例」：没有真实数据源的字段
  for (int i = 0; i < 26; i += 4) { fb->drawFastHLine(x + i, y, 2, C(FAINT)); fb->drawFastHLine(x + i, y + 11, 2, C(FAINT)); }
  for (int i = 0; i < 12; i += 4) { fb->drawFastVLine(x, y + i, 2, C(FAINT)); fb->drawFastVLine(x + 27, y + i, 2, C(FAINT)); }
  txt(CJK12, x + 14, y - 1, TC_DATUM, FAINT, GROUND, "示例");
}

static void spark(const JsonArrayConst &a, int x, int y, int w, int h, uint32_t color, float base, bool hasBase) {
  const int n = a.size();
  if (n < 2) return;
  float lo = 1e9f, hi = -1e9f;
  for (JsonVariantConst v : a) { const float f = v.as<float>(); lo = min(lo, f); hi = max(hi, f); }
  if (hasBase) { lo = min(lo, base); hi = max(hi, base); }
  const float span = hi - lo > 1e-6f ? hi - lo : 1;
  auto py = [&](float v) { return y + h - 1 - (int)((v - lo) / span * (h - 2)); };
  if (hasBase) for (int xx = x; xx < x + w; xx += 4) fb->drawPixel(xx, py(base), C(FAINT));   // 昨收虚线
  int px = x, pyv = py(a[0].as<float>());
  for (int i = 1; i < n; i++) {
    const int cx = x + (int)((long)i * (w - 1) / (n - 1)), cyv = py(a[i].as<float>());
    fb->drawLine(px, pyv, cx, cyv, C(color));
    px = cx; pyv = cyv;
  }
}

static const char *modeText(const char *m) {
  if (!strcmp(m, "replay")) return "回放";
  if (!strcmp(m, "live")) return "实时";
  if (!strcmp(m, "close")) return "收盘";
  if (!strcmp(m, "sample")) return "示例";
  return "";
}

// ---------- 状态条 0,0,480,19 ----------
static char sceneName[12] = "", sceneClock[8] = "";
static int scenePage = 0, sceneOf = 0;

static void statusBar(const char *mode, const char *asof) {
  const bool live = !strcmp(mode, "replay") || !strcmp(mode, "live");
  fb->fillCircle(15, 9, 3, C(live ? ACCENT : FAINT));
  txt(CJK12, 24, 3, TL_DATUM, INK, GROUND, modeText(mode));
  char clk[8] = "";
  if (sceneClock[0]) strlcpy(clk, sceneClock, sizeof clk);
  else { struct tm tm; if (getLocalTime(&tm, 0) && tm.tm_year > 120) snprintf(clk, sizeof clk, "%02d:%02d", tm.tm_hour, tm.tm_min); }
  txt(M12, 58, 3, TL_DATUM, INK, GROUND, clk);
  txt(CJK12, 104, 3, TL_DATUM, MUTED, GROUND, asof);
  for (int i = 0, n = min(sceneOf, 8), x = 470 - (n - 1) * 9 - 14; i < n; i++, x += 9) {   // 页码点
    if (i + 1 == scenePage) fb->fillRoundRect(x - 2, 7, 14, 5, 2, C(INK));
    else fb->drawCircle(x + 3 + (i + 1 > scenePage ? 7 : 0), 9, 2, C(RULE));
  }
  fb->drawFastHLine(0, 18, 480, C(RULE));
}

// ---------- 盯盘 ----------
static void drawWatch(JsonVariantConst c) {
  const char *mode = c["mode"] | "close";
  statusBar(mode, c["asof"] | "");

  // 指数条 10,24,460,38：最多 4 格
  JsonArrayConst idx = c["indices"];
  const int ni = idx.isNull() ? 0 : min((int)idx.size(), 4);
  for (int i = 0; i < ni; i++) {
    const int x = 10 + i * 115;
    const float pct = idx[i]["pct"] | 0.0f;
    if (i) fb->drawFastVLine(x - 4, 26, 34, C(RULE));
    txt(CJK12, x, 25, TL_DATUM, MUTED, GROUND, idx[i]["name"] | "");
    if (!idx[i]["value"].isNull()) txtf(M12, x, 43, TL_DATUM, INK, GROUND, "%.1f", idx[i]["value"].as<float>());
    tri(x + 56, 46, pct >= 0, dirColor(pct));
    txtf(M12, x + 66, 43, TL_DATUM, dirColor(pct), GROUND, "%.2f%%", fabsf(pct));
  }
  if (!ni && !c["index"].isNull()) {   // v1 兼容：只有一个指数
    const float pct = c["index"]["pct"] | 0.0f;
    txt(CJK12, 10, 25, TL_DATUM, MUTED, GROUND, c["index"]["name"] | "");
    tri(10, 46, pct >= 0, dirColor(pct));
    txtf(M12, 22, 43, TL_DATUM, dirColor(pct), GROUND, "%+.2f%%", pct);
  }
  fb->drawFastHLine(10, 63, 460, C(RULE));

  // 自选行：5 行时每行 45 px；少了就等分
  JsonArrayConst rows = c["rows"];
  const int n = min((int)rows.size(), 5);
  const int top = 67, rh = n ? min(75, 225 / n) : 45;
  float sum = 0;
  for (int i = 0; i < n; i++) {
    JsonVariantConst r = rows[i];
    const int y = top + i * rh;
    const float pct = r["pct"] | 0.0f;
    sum += pct;
    const bool alert = r["alert"] | false;
    const uint32_t bg = alert ? CARD : GROUND, fg = alert ? ON_CARD : INK, mu = alert ? ON_CARD_MUTED : MUTED, dc = dirColor(pct, alert);
    if (alert) fb->fillRoundRect(6, y + 1, 468, rh - 2, 8, C(CARD));
    else fb->drawFastHLine(10, y + rh - 1, 460, C(RULE));
    if (alert) fb->fillCircle(13, y + 11, 3, C(ACCENT));
    txt(CJK15, alert ? 20 : 10, y + 4, TL_DATUM, fg, bg, r["name"] | "");
    txt(M12, 10 + (alert ? 10 : 0), y + rh - 19, TL_DATUM, mu, bg, r["code"] | "");
    if (!r["vol_ratio"].isNull()) txtf(CJK12, 66 + (alert ? 10 : 0), y + rh - 20, TL_DATUM, mu, bg, "量比 %.1f", r["vol_ratio"].as<float>());
    if (!r["price"].isNull()) txtf(M17, 300, y + 3, TR_DATUM, fg, bg, "%.2f", r["price"].as<float>());
    if (!r["amount"].isNull()) txtf(CJK12, 300, y + rh - 20, TR_DATUM, mu, bg, "额 %.1f亿", r["amount"].as<float>());
    tri(322, y + 10, pct >= 0, dc);
    txtf(M17, 396, y + 3, TR_DATUM, dc, bg, "%+.2f%%", pct);
    if (!r["amp"].isNull()) txtf(CJK12, 396, y + rh - 20, TR_DATUM, mu, bg, alert ? "异动 · 振幅 %.1f%%" : "振幅 %.1f%%", r["amp"].as<float>());
    JsonArrayConst sp = r["spark"];
    const float prev = r["prev_close"] | (sp.size() ? sp[0].as<float>() : 0.0f);
    const int sh = min(30, rh - 12);
    spark(sp, 402, y + 4, 66, sh, dc, prev, true);
    // 当日区间条：高低之间画一条，开盘和现价各一个刻度
    if (!r["high"].isNull() && !r["low"].isNull() && rh >= 40) {
      const float lo = r["low"], hi = r["high"], span = hi - lo > 1e-6f ? hi - lo : 1;
      const int by = y + rh - 9;
      fb->fillRoundRect(402, by, 66, 4, 2, C(alert ? 0x4a4536 : RULE));
      auto mark = [&](float v, uint32_t col) { fb->fillRect(402 + (int)constrain((v - lo) / span, 0.0f, 1.0f) * 64, by - 2, 2, 8, C(col)); };
      if (!r["open"].isNull()) mark(r["open"], alert ? ON_CARD_MUTED : FAINT);
      if (!r["price"].isNull()) mark(r["price"], alert ? ON_CARD : INK);
    }
  }
  // 脚注 10,300
  const float avg = c["avg_pct"].isNull() ? (n ? sum / n : 0) : c["avg_pct"].as<float>();
  txt(CJK12, 10, 300, TL_DATUM, MUTED, GROUND, "自选均值");
  tri(62, 303, avg >= 0, dirColor(avg));
  txtf(M12, 74, 300, TL_DATUM, dirColor(avg), GROUND, "%+.2f%%", avg);
  txt(CJK12, 470, 300, TR_DATUM, MUTED, GROUND, !strcmp(mode, "sample") ? "示例数据 · 不构成投资建议" : "PandaAI · 不构成投资建议");
}

// ---------- 单股 ----------
static void drawMkt(JsonVariantConst c) {
  const char *mode = c["mode"] | "close";
  const float pct = c["pct"] | 0.0f;
  statusBar(mode, c["asof"] | "");
  const bool alert = c["alert"] | false;
  txt(CJK15, 10, 24, TL_DATUM, INK, GROUND, c["name"] | "");
  txt(M12, 10 + 15 * 5 + 6, 27, TL_DATUM, MUTED, GROUND, c["code"] | "");
  chip(alert ? 190 : 220, 24, alert ? "异动" : modeText(mode), 44, alert);

  // 大价格 + 涨跌额 / 涨跌幅
  const float price = c["price"] | 0.0f, prev = c["prev_close"] | 0.0f;
  txtf(M44, 10, 46, TL_DATUM, INK, GROUND, "%.2f", price);
  if (prev > 0) { tri(268 - 80, 50, pct >= 0, dirColor(pct)); txtf(M17, 271, 47, TR_DATUM, dirColor(pct), GROUND, "%+.2f", price - prev); }
  tri(268 - 80, 76, pct >= 0, dirColor(pct));
  txtf(M17, 271, 73, TR_DATUM, dirColor(pct), GROUND, "%+.2f%%", pct);

  // 5 分钟图 10,107,261,154：面积 + 线 + 昨收虚线
  JsonArrayConst sp = c["spark"];
  const int cx = 10, cyy = 108, cw = 261, ch = 140;
  if (sp.size() >= 2) {
    float lo = 1e9f, hi = -1e9f;
    for (JsonVariantConst v : sp) { lo = min(lo, v.as<float>()); hi = max(hi, v.as<float>()); }
    if (prev > 0) { lo = min(lo, prev); hi = max(hi, prev); }
    const float span = hi - lo > 1e-6f ? hi - lo : 1;
    const int n = sp.size();
    const uint16_t fill = mix(GROUND, dirColor(pct) , 0.14f);
    auto yOf = [&](float v) { return cyy + ch - 1 - (int)((v - lo) / span * (ch - 2)); };
    for (int x = 0; x < cw; x++) {   // 面积：每一列从线画到底
      const float pos = (float)x * (n - 1) / (cw - 1);
      const int i = min((int)pos, n - 2);
      const float v = sp[i].as<float>() + (sp[i + 1].as<float>() - sp[i].as<float>()) * (pos - i);
      fb->drawFastVLine(cx + x, yOf(v), cyy + ch - yOf(v), fill);
    }
    if (prev > 0) for (int x = 0; x < cw; x += 5) fb->drawPixel(cx + x, yOf(prev), C(FAINT));
    int px = cx, py = yOf(sp[0].as<float>());
    for (int i = 1; i < n; i++) {
      const int x = cx + (int)((long)i * (cw - 1) / (n - 1)), y = yOf(sp[i].as<float>());
      fb->drawLine(px, py, x, y, C(dirColor(pct)));
      fb->drawLine(px, py + 1, x, y + 1, C(dirColor(pct)));
      px = x; py = y;
    }
    txtf(M12, cx + 2, cyy + 1, TL_DATUM, MUTED, GROUND, "%.2f", hi);
    txtf(M12, cx + 2, cyy + ch - 14, TL_DATUM, MUTED, GROUND, "%.2f", lo);
  }
  txt(M12, cx, cyy + ch + 3, TL_DATUM, FAINT, GROUND, "09:30");
  txt(M12, cx + cw / 2, cyy + ch + 3, TC_DATUM, FAINT, GROUND, "11:30");
  txt(M12, cx + cw, cyy + ch + 3, TR_DATUM, FAINT, GROUND, "15:00");

  // 右栏统计表 281,24,189
  struct Row { const char *label, *key, *fmt; };
  static const Row R[] = {{"开盘", "open", "%.2f"}, {"最高", "high", "%.2f"}, {"最低", "low", "%.2f"}, {"昨收", "prev_close", "%.2f"},
                          {"成交量", "volume", "%.1f万手"}, {"成交额", "amount", "%.1f亿"}, {"振幅", "amp", "%.2f%%"},
                          {"涨停价", "limit_up", "%.2f"}, {"跌停价", "limit_down", "%.2f"}, {"量比", "vol_ratio", "%.2f"}};
  int row = 0;
  for (const Row &r : R) {
    if (c[r.key].isNull()) continue;
    const int y = 26 + row * 22;
    fb->drawFastHLine(281, y + 21, 189, C(RULE));
    txt(CJK12, 281, y + 4, TL_DATUM, MUTED, GROUND, r.label);
    // 高 / 低 / 涨停 / 跌停 用涨跌色，其余用墨色
    const uint32_t col = !strcmp(r.key, "high") || !strcmp(r.key, "limit_up") ? UPC : !strcmp(r.key, "low") || !strcmp(r.key, "limit_down") ? DOWNC : INK;
    char b[32];
    snprintf(b, sizeof b, r.fmt, c[r.key].as<float>());
    // 单位（万手 / 亿 / %）走中文字体，所以拆成数字 + 单位
    char *unit = b;
    while (*unit && (isdigit((unsigned char)*unit) || *unit == '.' || *unit == '-')) unit++;
    char num[24], un[12];
    strlcpy(un, unit, sizeof un);
    strlcpy(num, b, min((size_t)(unit - b + 1), sizeof num));
    if (un[0]) { txt(CJK12, 470, y + 4, TR_DATUM, MUTED, GROUND, un); }
    txt(M15, un[0] ? 470 - (strlen(un) > 2 ? 40 : 14) : 470, y + 3, TR_DATUM, col, GROUND, num);
    row++;
  }

  // 底部条 10,283：20 日区间
  JsonVariantConst r20 = c["range20"];
  if (!r20.isNull() && price > 0) {
    const float lo = r20["lo"], hi = r20["hi"], span = hi - lo > 1e-6f ? hi - lo : 1;
    txt(CJK12, 10, 285, TL_DATUM, MUTED, GROUND, "20 日区间");
    txtf(M12, 78, 286, TL_DATUM, MUTED, GROUND, "%.2f", lo);
    txtf(M12, 268, 286, TR_DATUM, MUTED, GROUND, "%.2f", hi);
    fb->fillRoundRect(130, 291, 100, 4, 2, C(RULE));
    fb->fillRect(130 + (int)(constrain((price - lo) / span, 0.0f, 1.0f) * 98), 287, 2, 12, C(INK));
  }
  txt(CJK12, 470, 300, TR_DATUM, MUTED, GROUND, !strcmp(mode, "sample") ? "示例数据 · 不构成投资建议" : "PandaAI · 不构成投资建议");
}



// ================= 简洁模式（密度 A：大字，一屏一件事）=================
static void bigTri(int x, int y, bool up, uint32_t color, int w = 16, int h = 13) {
  if (up) fb->fillTriangle(x, y + h, x + w, y + h, x + w / 2, y, C(color));
  else fb->fillTriangle(x, y, x + w, y, x + w / 2, y + h, C(color));
}

static void pageDots(int y) {   // 右下角的页码点（简洁模式没有状态条）
  for (int i = 0, n = min(sceneOf, 8), x = 466 - (n - 1) * 9; i < n; i++, x += 9)
    if (i + 1 == scenePage) fb->fillRoundRect(x - 5, y, 12, 5, 2, C(INK)); else fb->drawCircle(x, y + 2, 2, C(RULE));
}

static void drawWatchSimple(JsonVariantConst c) {
  const char *mode = c["mode"] | "close";
  JsonArrayConst rows = c["rows"];
  const int n = min((int)rows.size(), 3);
  // 顶部：标题 + 第一个指数 + 模式 chip
  txtf(CJK14, 14, 15, TL_DATUM, MUTED, GROUND, "自选 · %s", (const char *)(c["asof"] | ""));
  JsonVariantConst ix = c["indices"][0].isNull() ? c["index"] : c["indices"][0];
  if (!ix.isNull()) {
    const float p = ix["pct"] | 0.0f;
    txt(CJK14, 214, 15, TL_DATUM, MUTED, GROUND, ix["name"] | "");
    tri(262 + (int)strlen(ix["name"] | "") / 3 * 14 - 30, 19, p >= 0, dirColor(p));
    txtf(M14, 290, 15, TL_DATUM, dirColor(p), GROUND, "%+.2f%%", p);
  }
  chip(466 - 62, 10, modeText(mode), 62, false, CJK14, 24);
  // 最强的一行（|pct| 最大）反白
  int loud = 0;
  for (int i = 1; i < n; i++) if (fabsf(rows[i]["pct"] | 0.0f) > fabsf(rows[loud]["pct"] | 0.0f)) loud = i;
  for (int i = 0; i < n; i++) {
    JsonVariantConst r = rows[i];
    const int y = 44 + i * 82, h = 76;
    const float pct = r["pct"] | 0.0f;
    const bool L = i == loud;
    const uint32_t bg = L ? CARD : SURFACE, fg = L ? ON_CARD : INK, mu = L ? ON_CARD_MUTED : MUTED, dc = dirColor(pct, L);
    fb->fillRoundRect(14, y, 452, h, 14, C(bg));
    txt(CJK26, 28, y + 10, TL_DATUM, fg, bg, r["name"] | "");
    txt(M14, 28, y + 48, TL_DATUM, mu, bg, r["code"] | "");
    spark(r["spark"], 196, y + 26, 60, 28, dc, r["prev_close"] | 0.0f, !r["prev_close"].isNull());
    if (!r["price"].isNull()) txtf(M18, 338, y + 26, TR_DATUM, fg, bg, "%.2f", r["price"].as<float>());
    bigTri(350, y + 30, pct >= 0, dc, 12, 10);
    txtf(M26, 458, y + 22, TR_DATUM, dc, bg, "%+.2f%%", pct);
  }
  txt(CJK14, 14, 301, TL_DATUM, MUTED, GROUND, !strcmp(mode, "sample") ? "示例数据 · 不构成投资建议" : "行情数据仅供参考 · 不构成投资建议");
  pageDots(306);
}

static void drawMktSimple(JsonVariantConst c) {
  const char *mode = c["mode"] | "close";
  const float pct = c["pct"] | 0.0f, price = c["price"] | 0.0f, prev = c["prev_close"] | 0.0f;
  const bool alert = c["alert"] | false;
  txt(CJK26, 14, 12, TL_DATUM, INK, GROUND, c["name"] | "");
  txt(M14, 14 + 26 * 5 + 8, 22, TL_DATUM, MUTED, GROUND, c["code"] | "");
  if (alert) chip(466 - 70, 12, "异动", 70, true, CJK14, 26);
  else chip(466 - 70, 12, modeText(mode), 70, false, CJK14, 26);
  bigTri(14, 76, pct >= 0, dirColor(pct), 24, 20);
  txtf(M56, 46, 56, TL_DATUM, dirColor(pct), GROUND, "%+.2f%%", pct);
  JsonArrayConst sp = c["spark"];
  if (sp.size() >= 2) {
    const int cx = 14, cyy = 132, cw = 452, ch = 110;
    float lo = 1e9f, hi = -1e9f;
    for (JsonVariantConst v : sp) { lo = min(lo, v.as<float>()); hi = max(hi, v.as<float>()); }
    if (prev > 0) { lo = min(lo, prev); hi = max(hi, prev); }
    const float span = hi - lo > 1e-6f ? hi - lo : 1;
    const int n = sp.size();
    auto yOf = [&](float v) { return cyy + ch - 1 - (int)((v - lo) / span * (ch - 2)); };
    int px = cx, py = yOf(sp[0].as<float>());
    if (prev > 0) for (int x = 0; x < cw; x += 6) fb->drawPixel(cx + x, yOf(prev), C(FAINT));
    for (int i = 1; i < n; i++) {
      const int x = cx + (int)((long)i * (cw - 1) / (n - 1)), y = yOf(sp[i].as<float>());
      fb->drawLine(px, py, x, y, C(dirColor(pct))); fb->drawLine(px, py + 1, x, y + 1, C(dirColor(pct)));
      px = x; py = y;
    }
  }
  if (price > 0) {
    char b[48];
    snprintf(b, sizeof b, "¥%.2f · 昨收 %.2f · %s", price, prev, (const char *)(c["asof"] | ""));
    txt(CJK14, 14, 262, TL_DATUM, MUTED, GROUND, b);
  }
  txt(CJK18, 14, 280, TL_DATUM, INK, GROUND, c["hint"] | "");
  txt(CJK14, 14, 301, TL_DATUM, MUTED, GROUND, !strcmp(mode, "sample") ? "示例数据 · 不构成投资建议" : "行情数据仅供参考 · 不构成投资建议");
  pageDots(306);
}


// ================= 文字卡片：消息、护栏、角色、简报、市场天气、天气 =================
// 按像素宽度折行（CJK 占 px，ASCII 约 0.55 px），最多 maxLines 行；超出的丢掉
static int wrapPx(const char *text, int px, int maxw, char lines[][60], int maxLines) {
  int n = 0, w = 0;
  size_t len = 0;
  lines[0][0] = 0;
  for (const char *p = text; *p && n < maxLines;) {
    const int clen = (*p & 0x80) ? ((*p & 0xE0) == 0xC0 ? 2 : (*p & 0xF0) == 0xE0 ? 3 : 4) : 1;
    const int cw = (unsigned char)*p > 127 ? px : (int)(px * 0.55f);
    if (w + cw > maxw && len) { if (++n >= maxLines) break; lines[n][0] = 0; w = 0; len = 0; }
    if (len + clen < 59) { memcpy(lines[n] + len, p, clen); len += clen; lines[n][len] = 0; }
    w += cw; p += clen;
  }
  return min(n + 1, maxLines);
}

static void legalLine() { txt(CJK14, 466, 301, TR_DATUM, MUTED, GROUND, "示例数据 · 不构成投资建议"); }

static void drawMsg(JsonVariantConst c) {
  fb->fillRoundRect(14, 14, 452, 236, 18, C(CARD));
  txt(CJK14, 34, 32, TL_DATUM, ON_CARD_MUTED, CARD, c["title"] | "");
  if (!strcmp(c["level"] | "", "urgent")) chip(466 - 20 - 56, 28, "紧急", 56, true, CJK14, 24);
  char L[4][60];
  const int n = wrapPx(c["body"] | "", 26, 410, L, 3);
  for (int i = 0; i < n; i++) txt(CJK26, 34, 72 + i * 36, TL_DATUM, ON_CARD, CARD, L[i]);
  if (!c["meta"].isNull()) txt(CJK14, 34, 222, TL_DATUM, ON_CARD_MUTED, CARD, c["meta"]);
  txt(CJK18, 14, 266, TL_DATUM, INK, GROUND, c["hint"] | "");
}

static void drawAsk(JsonVariantConst c) {
  fb->fillRoundRect(14, 14, 452, 236, 18, C(CARD));
  txt(CJK14, 34, 32, TL_DATUM, ON_CARD_MUTED, CARD, c["why"] | "");
  char L[3][60];
  const int n = wrapPx(c["title"] | "确定吗？", 26, 410, L, 2);
  for (int i = 0; i < n; i++) txt(CJK26, 34, 84 + i * 40, TL_DATUM, ON_CARD, CARD, L[i]);
  if (!c["meta"].isNull()) txt(CJK14, 34, 222, TL_DATUM, ON_CARD_MUTED, CARD, c["meta"]);
  txt(CJK18, 14, 266, TL_DATUM, INK, GROUND, c["hint"] | "按头 = 确认 · 不动 = 算了");
}

static void drawAgent(JsonVariantConst c) {
  const char *name = c["name"] | "";
  fb->fillRoundRect(14, 14, 18 + (int)strlen(name) / 3 * 15 + 14, 26, 13, C(DB_LIGHT_LILAC));
  txt(CJK14, 14 + 12, 19, TL_DATUM, DB_LIGHT_ON_ACCENT, DB_LIGHT_LILAC, name);
  txt(CJK14, 466, 19, TR_DATUM, MUTED, GROUND, c["source"] | "A2A 办公室 · 盘前简报");
  char L[5][60];
  const int n = wrapPx(c["say"] | "", 26, 440, L, 4);
  for (int i = 0; i < n; i++) txt(CJK26, 14, 66 + i * 38, TL_DATUM, INK, GROUND, L[i]);
  const int of = c["of"] | 3, at = c["n"] | 1;
  for (int i = 0; i < of; i++) fb->fillRoundRect(14 + i * 30, 296, 24, 4, 2, C(i < at ? DB_LIGHT_LILAC : RULE));
  if (!(c["legal"].is<bool>() && !(bool)c["legal"])) legalLine();
}

static void drawBrief(JsonVariantConst c) {
  txt(CJK14, 14, 15, TL_DATUM, MUTED, GROUND, c["title"] | "盘前简报");
  JsonArrayConst it = c["items"];
  int y = 44;
  for (int i = 0; i < (int)min(it.size(), (size_t)3); i++) {
    char L[3][60];
    const int n = wrapPx(it[i] | "", 18, 420, L, 2);
    txtf(M14, 14, y + 3, TL_DATUM, MUTED, GROUND, "%d", i + 1);
    for (int k = 0; k < n; k++) txt(CJK18, 40, y + k * 26, TL_DATUM, INK, GROUND, L[k]);
    y += 26 * n + 18;
    if (i < 2) fb->drawFastHLine(14, y - 10, 452, C(RULE));
  }
  txt(CJK14, 14, 280, TL_DATUM, INK, GROUND, c["hint"] | "");
  if (!(c["legal"].is<bool>() && !(bool)c["legal"])) legalLine();
}

// 色板测试：这块屏的白点偏冷，设计系统的米黄在上面会发蓝。画一组更暖的候选色，拍照对比着挑
static void drawColorTest() {
  auto raw = [&](uint32_t h) { return T->color565((h >> 16) & 255, (h >> 8) & 255, h & 255); };   // 不经过校正
  const uint32_t base = DB_LIGHT_GROUND, picked = 0xF7E2A8, dev = devColor(base);
  struct Blk { uint16_t col; uint32_t hex; const char *label; } B[3] = {
      {raw(base), base, "1 uncorrected"}, {C(base), dev, "2 corrected"}, {raw(picked), picked, "3 your pick"}};
  fb->fillSprite(C(0xFFFFFF));
  for (int i = 0; i < 3; i++) {
    const int x = 10 + i * 155;
    fb->fillRect(x, 10, 145, 250, B[i].col);
    fb->drawRect(x, 10, 145, 250, C(INK));
    char b[32];
    snprintf(b, sizeof b, "%06X", (unsigned)B[i].hex);
    txt(M15, x + 72, 120, TC_DATUM, 0x000000, B[i].hex, b);
    txt(M12, x + 72, 150, TC_DATUM, 0x000000, B[i].hex, B[i].label);
  }
  txt(M12, 240, 280, TC_DATUM, 0x000000, 0xFFFFFF, "2 should look like 3");
}

// ---------- 入口 ----------
static JsonDocument lastCard;
static uint8_t dispMode = 2;   // 0 简洁 · 1 紧凑（真机暂时按专业画）· 2 专业
static char lastState[12] = "";

bool begin(TFT_eSPI *tft) {
  T = tft;
  mapFonts();
  Preferences pr;
  pr.begin("deskbot", true);
  dispMode = pr.getUChar("disp", 2);
  pr.end();
  fb = new TFT_eSprite(T);
  fb->setColorDepth(16);
  if (!fb->createSprite(T->width(), T->height())) { Serial.println("[screens] 整屏 sprite 分配失败（PSRAM？）"); delete fb; fb = nullptr; return false; }
  Serial.printf("[screens] 整屏 sprite %dx%d 就绪\n", T->width(), T->height());
  return true;
}

bool handles(const char *state) {
  static const char *const S[] = {"watch", "mkt", "brief", "msg", "ask", "agent", "colortest"};
  for (const char *x : S) if (!strcmp(state, x)) return true;
  return false;
}

static void paint() {
  if (!fb) return;
  nops = 0;
  fb->fillSprite(C(GROUND));
  JsonVariantConst c = lastCard.as<JsonVariantConst>();
  const bool simple = dispMode == 0;
  if (!strcmp(lastState, "watch")) simple ? drawWatchSimple(c) : drawWatch(c);
  else if (!strcmp(lastState, "mkt")) simple ? drawMktSimple(c) : drawMkt(c);
  else if (!strcmp(lastState, "brief")) drawBrief(c);
  else if (!strcmp(lastState, "msg")) drawMsg(c);
  else if (!strcmp(lastState, "ask")) drawAsk(c);
  else if (!strcmp(lastState, "agent")) drawAgent(c);
  else if (!strcmp(lastState, "colortest")) drawColorTest();
  flush();
  fb->pushSprite(0, 0);
}

bool show(const char *state, JsonVariantConst card) {
  if (!handles(state) || !fb) return false;
  lastCard.set(card);   // 深拷贝：回调里的 JsonDocument 马上会被释放
  strlcpy(lastState, state, sizeof lastState);
  paint();
  return true;
}

void setMode(const char *mode, bool save) {
  const uint8_t m = !strcmp(mode, "simple") ? 0 : !strcmp(mode, "compact") ? 1 : 2;
  if (m == dispMode) return;
  dispMode = m;
  if (save) { Preferences pr; pr.begin("deskbot", false); pr.putUChar("disp", m); pr.end(); }
  if (lastState[0]) paint();
}

const char *mode() { return dispMode == 0 ? "simple" : dispMode == 1 ? "compact" : "pro"; }

bool openRowAt(int px, int py, JsonDocument &out, char *code, size_t codeLen) {
  if (strcmp(lastState, "watch")) return false;
  JsonArrayConst rows = lastCard["rows"];
  const int n = dispMode == 0 ? min((int)rows.size(), 3) : min((int)rows.size(), 5);
  if (!n) return false;
  int idx;
  if (dispMode == 0) { idx = (py - 44) / 82; if (py < 44 || py - 44 - idx * 82 > 76) return false; }
  else { const int rh = min(75, 225 / n); if (py < 67) return false; idx = (py - 67) / rh; }
  if (idx < 0 || idx >= n) return false;
  JsonVariantConst r = rows[idx];
  strlcpy(code, r["code"] | "", codeLen);
  out.clear();
  JsonObject c = out["card"].to<JsonObject>();
  for (const char *k : {"name", "code", "pct", "price", "prev_close", "open", "high", "low", "amount", "amp", "vol_ratio", "spark"})
    if (!r[k].isNull()) c[k] = r[k];
  c["mode"] = lastCard["mode"] | "close";
  c["asof"] = lastCard["asof"] | "";
  out["t"] = "face";
  out["state"] = "mkt";
  return true;
}

void store(const char *state, JsonVariantConst card) { lastCard.set(card); strlcpy(lastState, state, sizeof lastState); }

void redraw() { if (lastState[0]) paint(); }

void setScene(const char *name, int page, int of, const char *clock) {
  strlcpy(sceneName, name ? name : "", sizeof sceneName);
  scenePage = page;
  sceneOf = of;
  strlcpy(sceneClock, clock ? clock : "", sizeof sceneClock);
}

}  // namespace screens
