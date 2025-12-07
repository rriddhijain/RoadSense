#include "ti_msp_dl_config.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* ===================== Tunables ===================== */
#define VREF_MV               3300.0f
#define FS_HZ                 200.0f
#define ALPHA_SMOOTH_Q15      6554
#define START_THR_MV          250
#define SETTLE_THR_MV         150
#define STABLE_SEC            3.0f

#define BASELINE_SEC          1.0f
#define BASELINE_SAMPLES      ((uint16_t)(FS_HZ * BASELINE_SEC + 0.5f))
#define SETTLE_HOLD_SAMPLES   ((uint16_t)(FS_HZ * STABLE_SEC   + 0.5f))
#define EVT_MAX_SEC           10.0f
#define EVT_MAX_SAMPLES       ((uint16_t)(FS_HZ * EVT_MAX_SEC  + 0.5f))

#define NOISE_FLOOR_MV        250
#define L1_THR_MV             500
#define L2_THR_MV             900
#define LED_ON_TIME_MS        500U

/* =================== Severity Helper =================== */
static inline uint8_t classify_pothole_severity(uint16_t peak_mV)
{
    if (peak_mV <= NOISE_FLOOR_MV) return 0;
    if (peak_mV <= L1_THR_MV)       return 1;  // Green
    if (peak_mV <= L2_THR_MV)       return 2;  // Yellow
    return 3;                                  // Red
}

/* ===================== Mock GPS ===================== */
typedef struct {
    int32_t  x;
    int32_t  y;
    uint32_t last_update_ms;
} MockGPS_t;

static MockGPS_t gps = {0, 0, 0};

static inline void update_mock_gps(uint32_t now_ms)
{
    if ((now_ms - gps.last_update_ms) >= 1000U) {
        gps.last_update_ms = now_ms;
        gps.x++;
        gps.y++;
    }
}

/* ===================== LED Control ===================== */
#define PIN_RED    GPIO_LEDS_USER_LED_2_PIN
#define PIN_GREEN  GPIO_LEDS_USER_LED_3_PIN
#define PIN_BLUE   GPIO_LEDS_USER_LED_1_PIN
#define PIN_ALL    (PIN_RED | PIN_GREEN | PIN_BLUE)

static inline void leds_all_off(void)
{
    DL_GPIO_clearPins(GPIO_LEDS_PORT, PIN_ALL);
}

static inline void set_rgb(uint8_t r, uint8_t g, uint8_t b)
{
    DL_GPIO_clearPins(GPIO_LEDS_PORT, PIN_ALL);
    uint32_t mask = 0;
    if (r) mask |= PIN_RED;
    if (g) mask |= PIN_GREEN;
    if (b) mask |= PIN_BLUE;
    if (mask) DL_GPIO_setPins(GPIO_LEDS_PORT, mask);
}

static inline void led_on_for_level(uint8_t sev)
{
    switch (sev) {
        case 1: set_rgb(0, 1, 0); break;   // Green
        case 2: set_rgb(1, 1, 0); break;   // Yellow (R+G)
        case 3: set_rgb(1, 0, 0); break;   // Red
        default: leds_all_off(); break;
    }
}

/* ====================== UART TX ====================== */

static inline void uart_tx_byte(uint8_t b)
{
    while (DL_UART_Main_isTXFIFOFull(UART_0_INST)) { /* wait */ }
    DL_UART_Main_transmitData(UART_0_INST, b);
}

static void uart_tx_str(const char *s)
{
    while (*s) {
        uart_tx_byte((uint8_t)(*s++));
    }
}

static void uart_send_line_json(const char *json)
{
    uart_tx_str(json);
    uart_tx_byte('\n');
}



/* ====================== JSON over UART ====================== */

static void send_pothole_json(uint8_t severity,
                              uint16_t peak_mV,
                              uint16_t width_samples,
                              uint32_t timestamp_ms,
                              int32_t x, int32_t y)
{
    char buf[192];
    int n = snprintf(buf, sizeof(buf),
        "{\"type\":\"POTHOLE\",\"severity\":%u,"
        "\"peak_mV\":%u,\"width\":%u,"
        "\"timestamp\":%lu,\"x\":%ld,\"y\":%ld}",
        (unsigned)severity, (unsigned)peak_mV, (unsigned)width_samples,
        (unsigned long)timestamp_ms, (long)x, (long)y);
    if (n > 0 && n < (int)sizeof(buf)) uart_send_line_json(buf);
}

static void send_speedbrk_json(uint16_t peak_mV,
                               uint16_t width_samples,
                               uint32_t timestamp_ms,
                               int32_t x, int32_t y)
{
    char buf[192];
    int n = snprintf(buf, sizeof(buf),
        "{\"type\":\"SPEEDBRK\","
        "\"peak_mV\":%u,\"width\":%u,"
        "\"timestamp\":%lu,\"x\":%ld,\"y\":%ld}",
        (unsigned)peak_mV, (unsigned)width_samples,
        (unsigned long)timestamp_ms, (long)x, (long)y);
    if (n > 0 && n < (int)sizeof(buf)) uart_send_line_json(buf);
}

/* ====================== State ======================= */
typedef enum { IDLE=0, TRACKING, WAIT_STABLE, REFRACTORY } MotionState;

/* =================== Globals =================== */
volatile uint16_t g_adcRaw = 0;
volatile bool     g_new    = false;
volatile uint32_t g_ts_ms  = 0;

static bool     g_led_active      = false;
static uint32_t g_led_off_time_ms = 0;
static bool     g_burst_lock      = false;

/* =================== ISRs =================== */
void ADC12_0_INST_IRQHandler(void)
{
    uint32_t iidx = DL_ADC12_getPendingInterrupt(ADC12_0_INST);
    if (iidx == DL_ADC12_IIDX_MEM0_RESULT_LOADED) {
        g_adcRaw = DL_ADC12_getMemResult(ADC12_0_INST, DL_ADC12_MEM_IDX_0);
        g_new = true;
        DL_ADC12_clearInterruptStatus(ADC12_0_INST, DL_ADC12_IIDX_MEM0_RESULT_LOADED);
    }
}

void TIMER_1_INST_IRQHandler(void)
{
    uint32_t iidx = DL_TimerG_getPendingInterrupt(TIMER_1_INST);
    if (iidx == DL_TIMERG_IIDX_ZERO) {
        g_ts_ms++;
        DL_TimerG_clearInterruptStatus(TIMER_1_INST, DL_TIMERG_IIDX_ZERO);
    }
}

/* ====================== Main ======================== */
int main(void)
{
    SYSCFG_DL_init();
    leds_all_off();

    NVIC_EnableIRQ(ADC12_0_INST_INT_IRQN);
    NVIC_EnableIRQ(TIMER_1_INST_INT_IRQN);
    __enable_irq();

    DL_TimerG_startCounter(TIMER_0_INST);
    DL_ADC12_enableConversions(ADC12_0_INST);
    DL_TimerG_startCounter(TIMER_1_INST);

    /* Boot banner */
    uart_send_line_json("{\"type\":\"BOOT\",\"msg\":\"RoadSense online\",\"baud\":115200}");

    /* ---- Establish baseline (~1 s) ---- */
    uint32_t acc = 0;
    for (uint16_t n = 0; n < BASELINE_SAMPLES; ) {
        if (!g_new) continue;
        g_new = false;
        acc += (uint32_t)(((float)g_adcRaw * VREF_MV) / 4095.0f);
        n++;
    }
    uint16_t vzero_mv = (uint16_t)(acc / (uint32_t)BASELINE_SAMPLES);

    /* ---- Runtime state ---- */
    MotionState state = IDLE;
    uint32_t v_smooth_q0 = vzero_mv;
    uint8_t  eventType = 0;
    uint16_t maxMag_mv = 0;
    uint16_t event_len = 0;
    uint16_t settle_cnt = 0;
    uint16_t impulse_width_samp = 0;
    bool     width_captured = false;
    uint16_t post_stable_cnt = 0;

    while (1) {
        update_mock_gps(g_ts_ms);

        if (g_led_active && (g_ts_ms >= g_led_off_time_ms)) {
            leds_all_off();
            g_led_active = false;
        }

        if (!g_new) { __WFI(); continue; }
        g_new = false;

        uint16_t mv_raw = (uint16_t)(((float)g_adcRaw * VREF_MV) / 4095.0f);
        int32_t diff_q0 = (int32_t)mv_raw - (int32_t)v_smooth_q0;
        v_smooth_q0 += (int32_t)((ALPHA_SMOOTH_Q15 * diff_q0) >> 15);
        uint16_t vs = (uint16_t)v_smooth_q0;
        int16_t dev = (int16_t)vs - (int16_t)vzero_mv;

        switch (state) {
        case IDLE:
            if (!g_burst_lock) {
                if (dev < -(int16_t)START_THR_MV) {
                    state = TRACKING; eventType = 1;  // POTHOLE (down-first)
                    g_burst_lock = true;
                    maxMag_mv = (uint16_t)((int16_t)vzero_mv - (int16_t)vs);
                    event_len = settle_cnt = 0; width_captured = false;
                } else if (dev > (int16_t)START_THR_MV) {
                    state = TRACKING; eventType = 2;  // SPEEDBRK (up-first)
                    g_burst_lock = true;
                    maxMag_mv = (uint16_t)((int16_t)vs - (int16_t)vzero_mv);
                    event_len = settle_cnt = 0; width_captured = false;
                }
            }
            break;

        case TRACKING:
            event_len++;
            if (eventType == 1 && dev < 0) {
                uint16_t d = (uint16_t)((int16_t)vzero_mv - (int16_t)vs);
                if (d > maxMag_mv) maxMag_mv = d;
            } else if (eventType == 2 && dev > 0) {
                uint16_t h = (uint16_t)((int16_t)vs - (int16_t)vzero_mv);
                if (h > maxMag_mv) maxMag_mv = h;
            }

            if ((dev < (int16_t)SETTLE_THR_MV) && (dev > -(int16_t)SETTLE_THR_MV)) {
                if (!width_captured) { impulse_width_samp = event_len; width_captured = true; }
                state = WAIT_STABLE; settle_cnt = 0;
            } else if (event_len >= EVT_MAX_SAMPLES) {
                if (!width_captured) { impulse_width_samp = event_len; width_captured = true; }
                state = WAIT_STABLE; settle_cnt = 0;
            }
            break;

        case WAIT_STABLE:
            if ((dev < (int16_t)SETTLE_THR_MV) && (dev > -(int16_t)SETTLE_THR_MV)) {
                if (++settle_cnt >= SETTLE_HOLD_SAMPLES) {
                    uint32_t ts_ms = g_ts_ms;
                    if (eventType == 1) {
                        uint8_t sev = classify_pothole_severity(maxMag_mv);
                        if (sev > 0) {
                            send_pothole_json(sev, maxMag_mv, impulse_width_samp, ts_ms, gps.x, gps.y);
                            leds_all_off(); led_on_for_level(sev);
                        }
                    } else if (eventType == 2) {
                        send_speedbrk_json(maxMag_mv, impulse_width_samp, ts_ms, gps.x, gps.y);
                        set_rgb(1, 1, 1);
                    }
                    g_led_active = true;
                    g_led_off_time_ms = ts_ms + LED_ON_TIME_MS;
                    state = REFRACTORY;
                    post_stable_cnt = 0; eventType = 0;
                    maxMag_mv = event_len = settle_cnt = impulse_width_samp = 0;
                    width_captured = false;
                }
            } else {
                settle_cnt = 0;
                if (eventType == 1 && dev < -(int16_t)START_THR_MV) {
                    uint16_t d = (uint16_t)((int16_t)vzero_mv - (int16_t)vs);
                    if (d > maxMag_mv) maxMag_mv = d;
                } else if (eventType == 2 && dev > (int16_t)START_THR_MV) {
                    uint16_t h = (uint16_t)((int16_t)vs - (int16_t)vzero_mv);
                    if (h > maxMag_mv) maxMag_mv = h;
                }
            }
            break;

        case REFRACTORY:
            if ((dev < (int16_t)SETTLE_THR_MV) && (dev > -(int16_t)SETTLE_THR_MV)) {
                if (++post_stable_cnt >= SETTLE_HOLD_SAMPLES) {
                    post_stable_cnt = 0;
                    g_burst_lock = false;
                    state = IDLE;
                }
            } else {
                post_stable_cnt = 0;
            }
            break;
        }
    }
}

