#pragma once
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "shared_types.h"

typedef struct {
    QueueHandle_t   frame_queue;
    QueueHandle_t   event_queue;
    device_config_t *config;
} inference_task_args_t;

void inference_task(void *arg);
