#include "config.h"
#include "shared_types.h"
#include "camera_task.h"
#include "inference_task.h"
#include "network_task.h"
#include "ota_task.h"
#include "mqtt_task.h"

#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "nvs_flash.h"
#include "driver/gpio.h"

static const char *TAG = "main";

// Shared runtime config — all tasks hold a pointer to this
static device_config_t s_config = {
    .motion_threshold = DEFAULT_MOTION_THRESHOLD,
    .jpeg_quality     = CAM_JPEG_QUALITY,
};

extern "C" void app_main(void)
{
    ESP_LOGI(TAG, "Peekaboo S3 starting — camera_id=%s", CAMERA_ID);
    ESP_LOGW(TAG, "Reset reason: %d (1=poweron 3=sw 4=panic 5=int_wdt 6=task_wdt 7=wdt 9=brownout)",
             (int)esp_reset_reason());

#ifdef BOARD_XIAO_S3
    gpio_reset_pin(GPIO_NUM_21);
    gpio_set_direction(GPIO_NUM_21, GPIO_MODE_OUTPUT);
    gpio_set_level(GPIO_NUM_21, 0);  // user LED off
#endif

    // NVS required by WiFi driver
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }

    ESP_LOGI(TAG, "PSRAM: %u KB free",
             (unsigned)(heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024));

    // ── Queues ────────────────────────────────────────────────────────────────
    QueueHandle_t frame_queue = xQueueCreate(FRAME_QUEUE_DEPTH, sizeof(frame_msg_t));
    QueueHandle_t event_queue = xQueueCreate(EVENT_QUEUE_DEPTH, sizeof(event_msg_t));

    if (!frame_queue || !event_queue) {
        ESP_LOGE(TAG, "Queue creation failed — halting");
        for (;;) vTaskDelay(portMAX_DELAY);
    }

    // ── Task argument blocks (static lifetime) ────────────────────────────────
    static camera_task_args_t camera_args = {
        .frame_queue = nullptr,
        .config      = &s_config,
    };
    camera_args.frame_queue = frame_queue;

    static inference_task_args_t inference_args = {
        .frame_queue = nullptr,
        .event_queue = nullptr,
        .config      = &s_config,
    };
    inference_args.frame_queue = frame_queue;
    inference_args.event_queue = event_queue;

    static network_task_args_t network_args = {
        .event_queue = nullptr,
        .config      = &s_config,
    };
    network_args.event_queue = event_queue;

    // ── Start tasks ───────────────────────────────────────────────────────────
    xTaskCreatePinnedToCore(camera_task,    "camera",    CAMERA_TASK_STACK,
                            &camera_args,    CAMERA_TASK_PRIORITY,    nullptr, CAMERA_TASK_CORE);

    xTaskCreatePinnedToCore(inference_task, "inference", INFERENCE_TASK_STACK,
                            &inference_args, INFERENCE_TASK_PRIORITY, nullptr, INFERENCE_TASK_CORE);

    xTaskCreatePinnedToCore(network_task,   "network",   NETWORK_TASK_STACK,
                            &network_args,   NETWORK_TASK_PRIORITY,   nullptr, NETWORK_TASK_CORE);

    xTaskCreatePinnedToCore(ota_task, "ota", OTA_TASK_STACK,
                            nullptr, OTA_TASK_PRIORITY, nullptr, INFERENCE_TASK_CORE);

    xTaskCreatePinnedToCore(mqtt_task, "mqtt", MQTT_TASK_STACK,
                            nullptr, MQTT_TASK_PRIORITY, nullptr, NETWORK_TASK_CORE);

    ESP_LOGI(TAG, "All tasks started — firmware %s channel %s",
             FIRMWARE_VERSION, FIRMWARE_CHANNEL);
    // app_main returns — tasks run independently under FreeRTOS scheduler
}
