#pragma once
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "shared_types.h"

typedef struct {
    QueueHandle_t   frame_queue;
    device_config_t *config;     // live pointer — read each iteration
} camera_task_args_t;

void camera_task(void *arg);
