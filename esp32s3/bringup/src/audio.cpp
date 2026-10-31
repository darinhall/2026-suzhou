#include "audio.h"

#include <driver/i2s.h>

#include <algorithm>

#include "net.h"
#include "voice_hello.h"

namespace audio {

static const i2s_port_t PORT = I2S_NUM_0;
static const int RATE = 16000;
static const int PIN_BCLK = 12, PIN_WS = 13, PIN_DOUT = 11, PIN_DIN = 38;
static bool ok = false;
static volatile bool playing = false;   // 自己在放音时不听（喇叭会把自己"吵醒"）

bool begin() {
  i2s_config_t c = {};
  c.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX | I2S_MODE_RX);   // 全双工：放音和收音同时进行，时钟共用
  c.sample_rate = RATE;
  c.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;   // INMP441 是 24 位放在 32 位槽里
  c.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  c.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  c.dma_buf_count = 6;
  c.dma_buf_len = 256;
  c.tx_desc_auto_clear = true;   // 没有数据时输出静音，不会"嗡嗡"重复最后一段
  if (i2s_driver_install(PORT, &c, 0, nullptr) != ESP_OK) { Serial.println("[audio] I2S 驱动安装失败"); return false; }
  i2s_pin_config_t p = {};
  p.mck_io_num = I2S_PIN_NO_CHANGE;
  p.bck_io_num = PIN_BCLK;
  p.ws_io_num = PIN_WS;
  p.data_out_num = PIN_DOUT;
  p.data_in_num = PIN_DIN;
  if (i2s_set_pin(PORT, &p) != ESP_OK) { Serial.println("[audio] I2S 引脚设置失败"); return false; }
  i2s_zero_dma_buffer(PORT);
  ok = true;
  Serial.println("[audio] I2S 就绪：BCLK 12 · WS 13 · 喇叭 11 · 麦克风 38 · 16 kHz");
  return true;
}

// 读一块麦克风数据，累加左右声道的统计（INMP441 的 L/R 接地 = 左声道，但两个都算，免得接反看不出）
struct Stat { double g1[2] = {0, 0}, g2[2] = {0, 0}; double sum[2] = {0, 0}, sq[2] = {0, 0}; int32_t pk[2] = {0, 0}; long n = 0; int32_t first[2] = {0, 0}; bool varies[2] = {false, false}; };

static void readInto(Stat &s, int frames) {
  static int32_t buf[256 * 2];
  while (frames > 0) {
    size_t got = 0;
    const int want = min(frames, 256);
    i2s_read(PORT, buf, want * 8, &got, pdMS_TO_TICKS(100));
    const int fr = got / 8;
    for (int i = 0; i < fr; i++)
      for (int ch = 0; ch < 2; ch++) {
        const int32_t v = buf[i * 2 + ch] >> 8;   // 24 位有效
        if (s.n == 0 && i == 0) s.first[ch] = v;
        if (v != s.first[ch]) s.varies[ch] = true;
        s.sum[ch] += v; s.sq[ch] += (double)v * v;
        s.pk[ch] = max(s.pk[ch], abs(v));
        // Goertzel @1 kHz：只看 1 kHz 这一个频率的能量，现场人声再吵也不影响判断
        static const double K = 2 * cos(2 * PI * 1000.0 / RATE);
        const double g0 = v + K * s.g1[ch] - s.g2[ch];
        s.g2[ch] = s.g1[ch]; s.g1[ch] = g0;
      }
    s.n += fr;
    frames -= max(fr, 1);
  }
}

static double tonePower(const Stat &s, int ch) {   // 1 kHz 分量的幅度（按样本数归一）
  if (!s.n) return 0;
  const double K = 2 * cos(2 * PI * 1000.0 / RATE);
  const double p = s.g1[ch] * s.g1[ch] + s.g2[ch] * s.g2[ch] - K * s.g1[ch] * s.g2[ch];
  return sqrt(max(0.0, p)) / s.n;
}

static float rmsOf(const Stat &s, int ch) {
  if (!s.n) return 0;
  const double m = s.sum[ch] / s.n;
  return sqrt(max(0.0, s.sq[ch] / s.n - m * m));
}

float micRms(int ms, float *peak) {
  if (!ok) return -1;
  Stat s;
  readInto(s, RATE * ms / 1000);
  const int ch = rmsOf(s, 0) >= rmsOf(s, 1) ? 0 : 1;
  if (peak) *peak = s.pk[ch];
  return rmsOf(s, ch);
}

// 一边放音一边收音：返回放音期间的麦克风统计
static Stat playAndListen(float freq, int ms, float vol) {
  playing = true;
  Stat s;
  static int32_t out[256 * 2];
  const int total = RATE * ms / 1000;
  const float amp = constrain(vol, 0.0f, 0.3f) * 2147483647.0f;   // 上限 0.3：1 W 喇叭别推太狠
  float ph = 0;
  const float step = 2 * PI * freq / RATE;
  for (int done = 0; done < total; done += 256) {
    const int n = min(256, total - done);
    for (int i = 0; i < n; i++) {
      // 前后 10 ms 淡入淡出，免得"啪"一声
      const int t = done + i, fade = RATE / 100;
      const float env = min(1.0f, min((float)t / fade, (float)(total - t) / fade));
      const int32_t v = (int32_t)(amp * env * sinf(ph));
      ph += step;
      if (ph > 2 * PI) ph -= 2 * PI;
      out[i * 2] = out[i * 2 + 1] = v;
    }
    size_t w = 0;
    i2s_write(PORT, out, n * 8, &w, pdMS_TO_TICKS(200));
    readInto(s, n);
  }
  playing = false;
  return s;
}

// 写一段立体声帧（两个声道相同），顺便把麦克风缓冲读掉（全双工：不读会溢出）
static void writeFrames(const int32_t *frames, int n) {
  size_t w = 0;
  i2s_write(PORT, frames, n * 8, &w, pdMS_TO_TICKS(200));
  static int32_t sink[256 * 2];
  size_t got = 0;
  i2s_read(PORT, sink, n * 8, &got, 0);
}

void playPcm(const int16_t *pcm, int n, float vol) {
  if (!ok) return;
  playing = true;
  static int32_t out[256 * 2];
  const float g = constrain(vol, 0.0f, 0.3f);
  for (int done = 0; done < n; done += 256) {
    const int k = min(256, n - done);
    for (int i = 0; i < k; i++) out[i * 2] = out[i * 2 + 1] = (int32_t)(pcm[done + i] * g * 65536.0f);
    writeFrames(out, k);
  }
  playing = false;
}

// 一个"拨弦"音：基频 + 一点二次谐波，快起慢落，比纯正弦好听
static void pluck(float freq, int ms, float vol) {
  static int32_t out[256 * 2];
  const int total = RATE * ms / 1000;
  const float amp = constrain(vol, 0.0f, 0.3f) * 2147483647.0f;
  for (int done = 0; done < total; done += 256) {
    const int k = min(256, total - done);
    for (int i = 0; i < k; i++) {
      const float t = (float)(done + i) / RATE;
      const float env = min(1.0f, t * 200) * expf(-t * 6.0f) * min(1.0f, (float)(total - done - i) / (RATE / 200));
      const float v = sinf(2 * PI * freq * t) + 0.3f * sinf(4 * PI * freq * t);
      out[i * 2] = out[i * 2 + 1] = (int32_t)(amp * env * v / 1.3f);
    }
    writeFrames(out, k);
  }
}

void chime(float vol) {   // 开机小旋律：C5 E5 G5 C6，G5 C6（自己编的，不是任何现成曲子）
  if (!ok) return;
  playing = true;
  const float notes[] = {523.25f, 659.25f, 783.99f, 1046.5f, 783.99f, 1046.5f};
  const int lens[] = {120, 120, 120, 220, 110, 380};
  for (int i = 0; i < 6; i++) pluck(notes[i], lens[i], vol);
  playing = false;
}

void hello(float vol) { playPcm(VOICE_HELLO, VOICE_HELLO_LEN, vol); }

void tone(float freq, int ms, float vol) {
  if (!ok) return;
  playAndListen(freq, ms, vol);
}

void selfTest() {
  if (!ok) { net::log("error", "AUDIO_I2S_FAIL", "I2S 没起来，检查引脚"); return; }
  hello(0.15f);   // 先说一句话、弹一段小旋律：人耳确认喇叭
  delay(150);
  chime(0.08f);
  Stat quiet;
  readInto(quiet, RATE / 2);   // 先丢掉开头，再量 0.5 秒底噪
  quiet = Stat();
  readInto(quiet, RATE / 2);
  const int ch = rmsOf(quiet, 0) >= rmsOf(quiet, 1) ? 0 : 1;
  const bool micAlive = quiet.varies[ch];
  const float q = rmsOf(quiet, ch);

  Stat beep = playAndListen(1000, 600, 0.08f);   // 1 kHz，低音量
  const float b = rmsOf(beep, ch);
  playAndListen(1319, 120, 0.06f);               // 再"叮"一下，好听一点
  playAndListen(1760, 160, 0.06f);

  const double tq = tonePower(quiet, ch), tb = tonePower(beep, ch);
  const bool heard = tb > tq * 5 && tb > 20;
  char m[180];
  snprintf(m, sizeof m, "麦克风 %s（%s声道，底噪 RMS %.0f）· 1 kHz 分量：安静 %.1f → 放音 %.1f（%.0f 倍）→ %s",
           micAlive ? "有数据" : "没数据", ch == 0 ? "左" : "右", q, tq, tb, tq > 0 ? tb / tq : 0,
           !micAlive ? "麦克风没接好" : heard ? "喇叭和麦克风都正常（麦克风听到了喇叭的 1 kHz）" : "麦克风正常，但没听到喇叭的 1 kHz：检查功放接线 / 5V / 喇叭");
  (void)b;
  Serial.printf("[audio] %s\n", m);
  // 实时电平表 20 秒：拍手 / 说话时数值应该明显变大（调试接线用）
  for (int i = 0; i < 80; i++) {
    float pk = 0;
    const float r = micRms(250, &pk);
    Serial.printf("[audio] 电平 %5.0f  峰值 %7.0f  %.*s\n", r, pk, (int)min(40.0f, r / 2000), "########################################");
  }
  playAndListen(880, 300, 0.08f);   // 自检结束再响一声
  net::log(micAlive && heard ? "info" : "warn", "AUDIO_SELFTEST", m);
}

// ================= 语音检测 =================
static const float VOICE_RATIO = 4.0f;          // 超过背景 4 倍才算说话
static const int WIN = RATE / 20;               // 50 ms 一个窗口
static const int START_WINS = 6, END_WINS = 12; // 连续 300 ms 超过 = 开始（短于这个的敲桌子、拍手不算）；连续 600 ms 低于 = 结束
static float bg = 0;
static bool talking = false;
static int above = 0, below = 0;
static uint32_t talkStart = 0;
static float talkPeak = 0, lastRms = 0;

static float windowRms(const int32_t *buf, int frames) {   // 只算左声道（INMP441 的 L/R 接地）
  double sum = 0, sq = 0;
  for (int i = 0; i < frames; i++) { const double v = buf[i * 2] >> 8; sum += v; sq += v * v; }
  const double m = sum / frames;
  return sqrt(max(0.0, sq / frames - m * m));
}

float calibrate(int ms) {
  if (!ok) return 0;
  static int32_t buf[WIN * 2];
  size_t got = 0;
  for (int i = 0; i < 4; i++) i2s_read(PORT, buf, sizeof buf, &got, pdMS_TO_TICKS(100));   // 先丢掉 200 ms
  const int n = max(5, ms / 50);
  float *v = (float *)malloc(n * sizeof(float));
  for (int i = 0; i < n; i++) { i2s_read(PORT, buf, sizeof buf, &got, pdMS_TO_TICKS(100)); v[i] = windowRms(buf, got / 8); }
  std::sort(v, v + n);
  bg = max(1.0f, v[n / 2]);   // 中位数
  char m[120];
  snprintf(m, sizeof m, "背景音量 RMS %ld（%d 个 50 ms 窗口的中位数，最小 %ld / 最大 %ld）· 说话阈值 = %ld（%d 倍）",
           (long)bg, n, (long)v[0], (long)v[n - 1], (long)(bg * VOICE_RATIO), (int)VOICE_RATIO);
  free(v);
  Serial.printf("[voice] %s\n", m);
  net::log("info", "VOICE_BG", m);
  talking = false; above = below = 0;
  return bg;
}

float background() { return bg; }
bool speaking() { return talking; }

float level() { return lastRms; }

int listenTick() {
  if (!ok || bg <= 0 || playing) return 0;
  static int32_t buf[WIN * 2];
  static int filled = 0;
  size_t got = 0;
  i2s_read(PORT, (uint8_t *)buf + filled * 8, (WIN - filled) * 8, &got, 0);   // 不等：有多少读多少
  filled += got / 8;
  if (filled < WIN) return 0;
  filled = 0;
  lastRms = windowRms(buf, WIN);
  const float ratio = lastRms / bg;
  if (!talking) {
    above = ratio >= VOICE_RATIO ? above + 1 : 0;
    if (above >= START_WINS) {
      talking = true; below = 0; talkStart = millis() - START_WINS * 50; talkPeak = ratio;
      Serial.printf("[voice] 有人说话（音量 %d.%d 倍背景）\n", (int)ratio, (int)(ratio * 10) % 10);
      return 1;
    }
  } else {
    talkPeak = max(talkPeak, ratio);
    below = ratio < VOICE_RATIO ? below + 1 : 0;
    if (below >= END_WINS) {
      talking = false; above = 0;
      const uint32_t dur = millis() - talkStart - END_WINS * 50;
      char m[96];
      // 这里只用整数格式化：开机时用 %f 打印后再画卡片会触发 newlib dtoa 的崩溃（10-31 实测），原因还没查清
      snprintf(m, sizeof m, "说完了：时长 %lu.%lu 秒，最大音量 %d.%d 倍背景", (unsigned long)(dur / 1000), (unsigned long)(dur % 1000 / 100), (int)talkPeak, (int)(talkPeak * 10) % 10);
      Serial.printf("[voice] %s\n", m);
      net::log("info", "VOICE_SEGMENT", m);
      return 2;
    }
  }
  return 0;
}

}  // namespace audio
