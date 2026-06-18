#include "camera_task.h"
#include "config.h"
#include "shared_types.h"
#include "frame_stats.h"

#include "esp_camera.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "driver/gpio.h"

static const char *TAG = "camera";

// JPEG size of the previous frame — used as motion proxy (no decode required)
static size_t s_prev_jpeg_len = 0;
static TickType_t s_last_sent_tick = 0;

// ── Camera init ───────────────────────────────────────────────────────────────
static esp_err_t camera_init(void)
{
    camera_config_t cfg = {};
    cfg.pin_pwdn    = CAM_PIN_PWDN;
    cfg.pin_reset   = CAM_PIN_RESET;
    cfg.pin_xclk    = CAM_PIN_XCLK;
    cfg.pin_sccb_sda = CAM_PIN_SIOD;
    cfg.pin_sccb_scl = CAM_PIN_SIOC;
    cfg.pin_d0      = CAM_PIN_Y2;
    cfg.pin_d1      = CAM_PIN_Y3;
    cfg.pin_d2      = CAM_PIN_Y4;
    cfg.pin_d3      = CAM_PIN_Y5;
    cfg.pin_d4      = CAM_PIN_Y6;
    cfg.pin_d5      = CAM_PIN_Y7;
    cfg.pin_d6      = CAM_PIN_Y8;
    cfg.pin_d7      = CAM_PIN_Y9;
    cfg.pin_vsync   = CAM_PIN_VSYNC;
    cfg.pin_href    = CAM_PIN_HREF;
    cfg.pin_pclk    = CAM_PIN_PCLK;

    // S3 OPI PSRAM: DMA mode is disabled, forcing an internal→PSRAM memcpy per
    // frame. 10 MHz gives enough time for that copy; 20 MHz overruns (EV-VSYNC-OVF).
    // ESP32-CAM uses QSPI PSRAM with standard DMA — 20 MHz is fine there.
    cfg.xclk_freq_hz = CAM_XCLK_HZ;
    cfg.ledc_timer   = LEDC_TIMER_0;
    cfg.ledc_channel = LEDC_CHANNEL_0;

    // JPEG: OV2640 hardware encoder; motion-gated by compressed-size delta
    cfg.pixel_format = PIXFORMAT_JPEG;
    cfg.frame_size   = CAM_FRAMESIZE;
    cfg.jpeg_quality = 12;
    cfg.fb_count     = 2;
    cfg.grab_mode    = CAMERA_GRAB_LATEST;
    cfg.fb_location  = CAMERA_FB_IN_PSRAM;

    esp_err_t err = esp_camera_init(&cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Camera init failed: 0x%x", err);
    } else {
        // Let OV2640 stabilise after init
        vTaskDelay(pdMS_TO_TICKS(2000));
        ESP_LOGI(TAG, "Camera ready (SVGA JPEG)");
    }
    return err;
}

// ── Motion detection ──────────────────────────────────────────────────────────
// Compares compressed JPEG size between frames. A person entering the scene
// changes the high-frequency content and therefore the compressed byte count.
// Returns true if the delta exceeds the threshold; seeds on first call.
static bool has_motion_jpeg(size_t jpeg_len, int min_delta)
{
    size_t prev = s_prev_jpeg_len;
    s_prev_jpeg_len = jpeg_len;
    if (prev == 0) return false;
    int delta = (int)jpeg_len - (int)prev;
    if (delta < 0) delta = -delta;
    return delta >= min_delta;
}

// ── Task ──────────────────────────────────────────────────────────────────────
void camera_task(void *arg)
{
    camera_task_args_t *args = (camera_task_args_t *)arg;

    gpio_set_direction((gpio_num_t)LED_PIN, GPIO_MODE_OUTPUT);
    gpio_set_level((gpio_num_t)LED_PIN, 0);

    if (camera_init() != ESP_OK) {
        ESP_LOGE(TAG, "Aborting camera task — init failed");
        vTaskDelete(nullptr);
        return;
    }

    ESP_LOGI(TAG, "Camera task running");

    for (;;) {
        camera_fb_t *fb = esp_camera_fb_get();
        if (!fb) {
            ESP_LOGW(TAG, "Frame capture failed");
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        bool motion = has_motion_jpeg(fb->len, MOTION_JPEG_DELTA_MIN);
        bool heartbeat = (xTaskGetTickCount() - s_last_sent_tick) >= pdMS_TO_TICKS(MOTION_HEARTBEAT_MS);

        if (!motion && !heartbeat) {
            esp_camera_fb_return(fb);
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }

        ESP_LOGD(TAG, "Frame captured (len=%zu)", fb->len);
        gpio_set_level((gpio_num_t)LED_PIN, 1);

        // Copy JPEG to heap so we can return the camera buffer
        uint8_t *copy = (uint8_t *)heap_caps_malloc(fb->len, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (copy) {
            memcpy(copy, fb->buf, fb->len);
        }
        size_t copy_len = fb->len;
        esp_camera_fb_return(fb);
        gpio_set_level((gpio_num_t)LED_PIN, 0);

        if (!copy) {
            ESP_LOGE(TAG, "Frame copy alloc failed — dropping");
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        frame_msg_t msg = {
            .buf    = copy,
            .len    = copy_len,
            .width  = (uint32_t)CAM_FRAME_WIDTH,
            .height = (uint32_t)CAM_FRAME_HEIGHT,
        };

        g_frames_captured++;

        // Non-blocking send: if inference queue is full, drop the frame
        if (xQueueSend(args->frame_queue, &msg, 0) != pdTRUE) {
            ESP_LOGD(TAG, "Inference busy — dropping frame");
            heap_caps_free(copy);
        } else {
            s_last_sent_tick = xTaskGetTickCount();
        }

        vTaskDelay(pdMS_TO_TICKS(50));
    }
}
