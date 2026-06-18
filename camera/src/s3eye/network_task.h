#pragma once
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "shared_types.h"

typedef struct {
    QueueHandle_t   event_queue;
    device_config_t *config;
} network_task_args_t;

void network_task(void *arg);
