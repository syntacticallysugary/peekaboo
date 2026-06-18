#include "inference_task.h"
#include "config.h"
#include "shared_types.h"
#include "frame_stats.h"

#include "esp_log.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "esp_camera.h"

static const char *TAG = "inference";

// JPEG pass-through for all boards — person/face detection runs on the Jetson.
// Motion gating is done by camera_task (JPEG size delta).

void inference_task(void *arg)
{
    inference_task_args_t *args = (inference_task_args_t *)arg;

    ESP_LOGI(TAG, "Inference task running (JPEG pass-through — detection on Jetson)");

    frame_msg_t frame;
    for (;;) {
        if (xQueueReceive(args->frame_queue, &frame, portMAX_DELAY) != pdTRUE) continue;

        event_msg_t evt = {};
        evt.jpeg     = frame.buf;
        evt.jpeg_len = frame.len;

        if (xQueueSend(args->event_queue, &evt, pdMS_TO_TICKS(200)) != pdTRUE) {
            ESP_LOGW(TAG, "Event queue full — dropping frame");
            heap_caps_free(frame.buf);
            g_frames_dropped_q++;
        }
    }
}
