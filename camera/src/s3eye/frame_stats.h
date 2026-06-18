#pragma once
#include <stdint.h>

// Counters incremented from camera_task, inference_task, and network_task.
// 32-bit aligned writes on Xtensa are single-instruction — safe to read from
// mqtt_task without a mutex for diagnostic purposes.
extern volatile uint32_t g_frames_captured;   // passed motion/heartbeat gate
extern volatile uint32_t g_frames_dropped_q;  // event queue full (network backpressure)
extern volatile uint32_t g_frames_sent;        // HTTP POST accepted by Jetson (2xx)
