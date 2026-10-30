/**
 * @file face_demo.c
 * @brief DeskBot 脸的第一版：在 NiceMCU T5 的 2.8″ 屏（320×240）上画设计系统里的两屏。
 *
 *   1. idle：暖灰底、两只 ink 眼睛（会眨）、accent 嘴
 *   2. mkt：宁德时代 +4.8% 行情卡（示例数据）
 *
 * 点一下屏幕切换；不点也会每 6 秒自动切换。
 * 尺寸和颜色照 sim/screen.css 里 data-size="s" 那一套（DeskBot 设计系统 tokens v1）。
 * 字体是第一版替代：数字用 Montserrat，中文用 LVGL 自带的 SimSun 16（约 1000 个常用字）；
 * Doto / Geist 要用 lv_font_conv 转成位图字体后再换上。
 */

#include "tuya_cloud_types.h"
#include "tal_api.h"
#include "tkl_output.h"
#include "lvgl.h"
#include "lv_vendor.h"
#include "board_com_api.h"

/* ---------- 设计系统 tokens（light） ---------- */
#define C_GROUND      0xE9E9E6
#define C_SURFACE     0xF5F5F3
#define C_INK         0x121212
#define C_INK_MUTED   0x5F5F5C
#define C_RULE        0xC9C9C4
#define C_ACCENT      0xFF5B14
#define C_UP          0xC8281E

/* ---------- 320×240 尺寸（screen.css 里 data-size="s"） ---------- */
#define EYE_W     38
#define EYE_H     64
#define EYE_GAP   64
#define MOUTH_W   16
#define MOUTH_H   4
#define MOUTH_Y   156
#define PAD       12

static lv_obj_t *s_root = NULL;
static lv_obj_t *s_eyes[2] = {NULL, NULL};
static int s_screen = 0;

static const int32_t SPARK[] = {12, 11, 12, 11, 12, 12, 13, 12, 14, 13, 17, 20, 24, 23, 28};
#define SPARK_N (sizeof(SPARK) / sizeof(SPARK[0]))
static lv_point_precise_t s_spark_pts[SPARK_N];

static lv_obj_t *__box(lv_obj_t *parent, int32_t w, int32_t h, uint32_t color, int32_t radius)
{
    lv_obj_t *o = lv_obj_create(parent);
    lv_obj_remove_style_all(o);
    lv_obj_set_size(o, w, h);
    lv_obj_set_style_bg_color(o, lv_color_hex(color), 0);
    lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(o, radius, 0);
    lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);
    return o;
}

static lv_obj_t *__text(lv_obj_t *parent, const char *txt, const lv_font_t *font, uint32_t color)
{
    lv_obj_t *l = lv_label_create(parent);
    lv_label_set_text(l, txt);
    lv_obj_set_style_text_font(l, font, 0);
    lv_obj_set_style_text_color(l, lv_color_hex(color), 0);
    return l;
}

/* ---------- 屏 1：idle 表情 ---------- */
static void __build_idle(void)
{
    for (int i = 0; i < 2; i++) {
        s_eyes[i] = __box(s_root, EYE_W, EYE_H, C_INK, EYE_W / 2);
        lv_obj_align(s_eyes[i], LV_ALIGN_CENTER, (i == 0 ? -1 : 1) * (EYE_GAP + EYE_W) / 2, 0);
    }
    lv_obj_t *mouth = __box(s_root, MOUTH_W, MOUTH_H, C_ACCENT, 2);
    lv_obj_align(mouth, LV_ALIGN_TOP_MID, 0, MOUTH_Y);
}

static void __blink_end(lv_timer_t *t)
{
    for (int i = 0; i < 2; i++) {
        if (s_eyes[i]) lv_obj_set_height(s_eyes[i], EYE_H);
    }
    lv_timer_delete(t);
}

static void __blink(lv_timer_t *t)
{
    (void)t;
    if (s_screen != 0 || !s_eyes[0]) return;
    for (int i = 0; i < 2; i++) lv_obj_set_height(s_eyes[i], 6);
    lv_timer_create(__blink_end, 120, NULL);
}

/* ---------- 屏 2：行情卡 ---------- */
static void __build_mkt(void)
{
    lv_obj_t *name = __text(s_root, "宁德时代", &lv_font_simsun_16_cjk, C_INK);
    lv_obj_set_pos(name, PAD, PAD);
    lv_obj_t *code = __text(s_root, "300750.SZ", &lv_font_montserrat_12, C_INK_MUTED);
    lv_obj_align_to(code, name, LV_ALIGN_OUT_RIGHT_BOTTOM, 6, -1);
    lv_obj_t *vr = __text(s_root, "VR 2.3", &lv_font_montserrat_12, C_INK_MUTED);
    lv_obj_align(vr, LV_ALIGN_TOP_RIGHT, -PAD, PAD + 2);

    /* 大数字：accent 实时点 + 上箭头 + "+" + 4.8 + % */
    lv_obj_t *live = __box(s_root, 8, 8, C_ACCENT, 4);
    lv_obj_set_pos(live, PAD, 74);
    lv_obj_t *sign = __text(s_root, LV_SYMBOL_UP " +", &lv_font_montserrat_24, C_UP);
    lv_obj_set_pos(sign, PAD + 14, 58);
    lv_obj_t *num = __text(s_root, "4.8", &lv_font_montserrat_48, C_UP);
    lv_obj_align_to(num, sign, LV_ALIGN_OUT_RIGHT_BOTTOM, 4, 6);
    lv_obj_t *pct = __text(s_root, "%", &lv_font_montserrat_24, C_UP);
    lv_obj_align_to(pct, num, LV_ALIGN_OUT_RIGHT_BOTTOM, 2, -6);

    /* 走势线：宽 296，高 44 */
    int32_t lo = SPARK[0], hi = SPARK[0];
    for (size_t i = 0; i < SPARK_N; i++) {
        if (SPARK[i] < lo) lo = SPARK[i];
        if (SPARK[i] > hi) hi = SPARK[i];
    }
    for (size_t i = 0; i < SPARK_N; i++) {
        s_spark_pts[i].x = (int32_t)(i * 296 / (SPARK_N - 1));
        s_spark_pts[i].y = 40 - (SPARK[i] - lo) * 36 / (hi - lo ? hi - lo : 1);
    }
    lv_obj_t *line = lv_line_create(s_root);
    lv_line_set_points(line, s_spark_pts, SPARK_N);
    lv_obj_set_style_line_color(line, lv_color_hex(C_UP), 0);
    lv_obj_set_style_line_width(line, 2, 0);
    lv_obj_set_style_line_rounded(line, true, 0);
    lv_obj_set_pos(line, PAD, 128);

    lv_obj_t *hint = __text(s_root, "按头 = 记入模拟单", &lv_font_simsun_16_cjk, C_INK);
    lv_obj_set_pos(hint, PAD, 186);
    lv_obj_t *legal = __text(s_root, "示例数据 · 不构成投资建议", &lv_font_simsun_16_cjk, C_INK_MUTED);
    lv_obj_set_pos(legal, PAD, 212);
}

static void __show(int which)
{
    s_screen = which;
    lv_obj_clean(s_root);
    s_eyes[0] = s_eyes[1] = NULL;
    if (which == 0) __build_idle();
    else __build_mkt();
    PR_NOTICE("FACE screen=%s", which == 0 ? "idle" : "mkt");
}

static void __on_click(lv_event_t *e)
{
    (void)e;
    __show(!s_screen);
}

static void __auto_cycle(lv_timer_t *t)
{
    (void)t;
    __show(!s_screen);
}

void user_main(void)
{
    tal_log_init(TAL_LOG_LEVEL_DEBUG, 4096, (TAL_LOG_OUTPUT_CB)tkl_log_output);
    PR_NOTICE("face_demo start · board %s", PLATFORM_BOARD);

    board_register_hardware();
    lv_vendor_init(DISPLAY_NAME);

    lv_vendor_disp_lock();
    lv_obj_t *scr = lv_screen_active();
    PR_NOTICE("display %d x %d", (int)lv_display_get_horizontal_resolution(NULL),
              (int)lv_display_get_vertical_resolution(NULL));
    lv_obj_set_style_bg_color(scr, lv_color_hex(C_GROUND), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);

    /* 整屏一个容器：点哪里都算点屏幕 */
    s_root = lv_obj_create(scr);
    lv_obj_remove_style_all(s_root);
    lv_obj_set_size(s_root, LV_PCT(100), LV_PCT(100));
    lv_obj_add_flag(s_root, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_remove_flag(s_root, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(s_root, __on_click, LV_EVENT_CLICKED, NULL);

    __show(0);
    lv_timer_create(__blink, 4000, NULL);
    lv_timer_create(__auto_cycle, 6000, NULL);
    lv_vendor_disp_unlock();

    lv_vendor_start(5, 1024 * 8);
}

#if OPERATING_SYSTEM == SYSTEM_LINUX
void main(int argc, char *argv[])
{
    user_main();
    while (1) {
        tal_system_sleep(500);
    }
}
#else
static THREAD_HANDLE ty_app_thread = NULL;

static void tuya_app_thread(void *arg)
{
    (void)arg;
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
