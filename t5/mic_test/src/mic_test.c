/**
 * @file mic_test.c
 * @brief NiceMCU T5 音频测试：开机喇叭响两声，然后每 100 ms 在串口打印一行麦克风音量条。
 *
 * 对着麦克风说话、拍手，条会变长；安静时应该很短但不为 0（底噪）。
 * 一直是 0：麦克风没采到数据（驱动 / 板级配置问题）。
 * 一直很满：可能增益太大，或者在录喇叭的声音。
 *
 * 用的是 TuyaOpen 的 tdl_audio（和 examples/multimedia/audio_vad 一样的接口），
 * 板子 NICEMCU_T5_2_8ISP 的 board_register_hardware() 会注册 16 kHz / 16 bit / 单声道的麦克风。
 */

#include "tuya_cloud_types.h"
#include "tal_api.h"
#include "tkl_output.h"
#include "tdl_audio_manage.h"
#include "board_com_api.h"

/* 回调在音频线程里累加，主循环每 100 ms 取一次并清零 */
static volatile uint64_t s_sum_sq = 0;
static volatile uint32_t s_count = 0;
static volatile uint32_t s_peak = 0;
static volatile uint32_t s_frames = 0;

static void __mic_cb(TDL_AUDIO_FRAME_FORMAT_E type, TDL_AUDIO_STATUS_E status, uint8_t *data, uint32_t len)
{
    if (type != TDL_AUDIO_FRAME_FORMAT_PCM || data == NULL) {
        return;
    }
    const int16_t *pcm = (const int16_t *)data;
    uint32_t n = len / 2;
    uint64_t sum = 0;
    uint32_t peak = s_peak;
    for (uint32_t i = 0; i < n; i++) {
        int32_t v = pcm[i];
        uint32_t a = (uint32_t)(v < 0 ? -v : v);
        sum += (uint64_t)a * a;
        if (a > peak) {
            peak = a;
        }
    }
    s_sum_sq += sum;
    s_count += n;
    s_peak = peak;
    s_frames++;
}

static uint32_t __isqrt(uint64_t x)
{
    uint64_t r = 0, bit = 1ULL << 62;
    while (bit > x) bit >>= 2;
    while (bit) {
        if (x >= r + bit) { x -= r + bit; r = (r >> 1) + bit; }
        else { r >>= 1; }
        bit >>= 2;
    }
    return (uint32_t)r;
}

/* 每一格是上一格的 2 倍（约 6 dB），20 格覆盖整个 16 bit 范围 */
static int __bars(uint32_t rms)
{
    int n = 0;
    for (uint32_t t = 16; t <= rms && n < 20; t <<= 1) {
        n++;
    }
    return n * 2 > 20 ? 20 : n * 2;
}

void user_main(void)
{
    tal_log_init(TAL_LOG_LEVEL_DEBUG, 1024, (TAL_LOG_OUTPUT_CB)tkl_log_output);
    PR_NOTICE("mic_test start · board %s", PLATFORM_BOARD);

    board_register_hardware();

    TDL_AUDIO_HANDLE_T audio = NULL;
    if (tdl_audio_find(AUDIO_CODEC_NAME, &audio) != OPRT_OK || tdl_audio_open(audio, __mic_cb) != OPRT_OK) {
        PR_ERR("audio open failed: 检查板子配置是否选了 NICEMCU_T5_2_8ISP");
        return;
    }
    TDL_AUDIO_INFO_T info = {0};
    tdl_audio_get_info(audio, &info);
    PR_NOTICE("mic open: %d Hz, %d ch, %d bit, frame %d ms", info.sample_rate, info.sample_ch_num, info.sample_bits,
              info.sample_tm_ms);

    /* 喇叭自检：开机响两声 1 kHz（三角波，0.25 秒），能听到就说明喇叭这条路也通 */
    static int16_t beep[16000 / 4];   /* 16 kHz × 0.25 s */
    for (uint32_t i = 0; i < sizeof(beep) / sizeof(beep[0]); i++) {
        int32_t phase = i % 16;   /* 16 kHz / 16 = 1 kHz */
        int32_t tri = phase < 8 ? phase * 2 - 8 : 24 - phase * 2;   /* −8 … +8 */
        beep[i] = (int16_t)(tri * 1200);   /* 约 30% 音量 */
    }
    tdl_audio_volume_set(audio, 60);
    for (int n = 0; n < 2; n++) {
        PR_NOTICE("SPK beep %d", n + 1);
        tdl_audio_play(audio, (uint8_t *)beep, sizeof(beep));
        tal_system_sleep(500);
    }

    char bar[21];
    uint32_t silent = 0;
    while (1) {
        tal_system_sleep(100);
        uint64_t sum = s_sum_sq;
        uint32_t cnt = s_count, peak = s_peak, frames = s_frames;
        s_sum_sq = 0;
        s_count = 0;
        s_peak = 0;
        s_frames = 0;

        uint32_t rms = cnt ? __isqrt(sum / cnt) : 0;
        int b = __bars(rms);
        for (int i = 0; i < 20; i++) {
            bar[i] = i < b ? '#' : '.';
        }
        bar[20] = 0;
        /* 固定格式，电脑上好解析：MIC rms=… peak=… frames=… |####......| */
        PR_NOTICE("MIC rms=%5u peak=%5u frames=%2u |%s|", rms, peak, frames, bar);

        silent = frames ? 0 : silent + 1;
        if (silent == 20) {
            PR_WARN("2 秒没有收到任何音频帧：麦克风没在工作");
        }
    }
}

#if OPERATING_SYSTEM == SYSTEM_LINUX
void main(int argc, char *argv[])
{
    user_main();
}
#else
static THREAD_HANDLE ty_app_thread = NULL;

static void tuya_app_thread(void *arg)
{
    user_main();
    tal_thread_delete(ty_app_thread);
    ty_app_thread = NULL;
}

void tuya_app_main(void)
{
    THREAD_CFG_T thrd_param = {0};
    thrd_param.stackDepth = 1024 * 4;
    thrd_param.priority = THREAD_PRIO_1;
    thrd_param.thrdname = "tuya_app_main";
    tal_thread_create_and_start(&ty_app_thread, NULL, NULL, tuya_app_thread, NULL, &thrd_param);
}
#endif
