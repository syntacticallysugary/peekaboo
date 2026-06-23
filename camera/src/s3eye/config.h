#pragma once

// Credentials generated at cmake configure time from .env (see src/CMakeLists.txt).
// Lives in the cmake binary dir; path is added to INCLUDE_DIRS in idf_component_register.
#include "credentials.h"

// ── Board identity ────────────────────────────────────────────────────────────
#ifndef CAMERA_ID
#define CAMERA_ID "s3eye-01"
#endif

// ── Network ───────────────────────────────────────────────────────────────────
#ifndef WIFI_SSID
#error "WIFI_SSID must be set via build flags"
#endif
#ifndef WIFI_PASSWORD
#error "WIFI_PASSWORD must be set via build flags"
#endif
#ifndef COMMAND_MODULE_URL
#error "COMMAND_MODULE_URL must be set via build flags"
#endif
#ifndef JETSON_URL
#error "JETSON_URL must be set via build flags"
#endif
#ifndef SECRET_PSK
#error "SECRET_PSK must be set via build flags"
#endif

// ── MQTT control channel ──────────────────────────────────────────────────────
// MQTT_BROKER_HOST, MQTT_BROKER_PORT, and MQTT_PASSWORD come from credentials.h
// (generated from .env at configure time). The username is the camera_id, so the
// broker can apply per-device ACLs.
#ifndef MQTT_BROKER_HOST
#error "MQTT_BROKER_HOST must be set via .env"
#endif
#ifndef MQTT_BROKER_PORT
#define MQTT_BROKER_PORT 8883
#endif
#ifndef MQTT_PASSWORD
#error "MQTT_PASSWORD must be set via .env"
#endif
#define MQTT_USERNAME      CAMERA_ID
#define MQTT_CMD_TOPIC     "peekaboo/cmd/" CAMERA_ID
#define MQTT_STATUS_TOPIC  "peekaboo/status/" CAMERA_ID

// Reject a command whose timestamp is more than this many seconds from now
// (only enforced once the clock is set via SNTP).
#ifndef MQTT_CMD_WINDOW_S
#define MQTT_CMD_WINDOW_S 60
#endif
// Number of recent command nonces remembered to reject replays.
#ifndef MQTT_NONCE_CACHE
#define MQTT_NONCE_CACHE 8
#endif
// Ignore reboot commands within this many seconds of boot (anti reboot-loop).
#ifndef MQTT_REBOOT_MIN_INTERVAL_S
#define MQTT_REBOOT_MIN_INTERVAL_S 60
#endif

// ── Camera ────────────────────────────────────────────────────────────────────
// S3 OPI PSRAM: DMA mode is disabled, forcing an internal→PSRAM memcpy per
// frame. 10 MHz XCLK gives enough time for that copy; 20 MHz overruns (EV-VSYNC-OVF).
#define CAM_FRAME_WIDTH   1280
#define CAM_FRAME_HEIGHT  1024
#ifndef CAM_FRAMESIZE
#define CAM_FRAMESIZE     FRAMESIZE_SXGA
#endif
#ifndef CAM_XCLK_HZ
#define CAM_XCLK_HZ       10000000
#endif
#define CAM_JPEG_QUALITY  12   // 0=best, 63=worst; overridden by remote config

// ── Motion detection ──────────────────────────────────────────────────────────
// Minimum JPEG byte-count delta between consecutive frames to declare motion.
#ifndef MOTION_JPEG_DELTA_MIN
#define MOTION_JPEG_DELTA_MIN 2000
#endif
// Heartbeat: always forward one frame at this interval even with no motion.
// Keeps sessions alive for stationary subjects and allows enrollment at distance.
#ifndef MOTION_HEARTBEAT_MS
#define MOTION_HEARTBEAT_MS 1000
#endif

// ── Behaviour ─────────────────────────────────────────────────────────────────
// Seconds of no frames before the camera signals session end to Jetson
#ifndef SESSION_END_TIMEOUT_S
#define SESSION_END_TIMEOUT_S 15
#endif

// ── OTA ───────────────────────────────────────────────────────────────────────
// Increment FIRMWARE_VERSION before each OTA push to trigger an update.
#ifndef FIRMWARE_VERSION
#define FIRMWARE_VERSION "1.0.0"
#endif
// Firmware channel groups cameras of the same board type for OTA targeting.
#ifndef FIRMWARE_CHANNEL
#define FIRMWARE_CHANNEL "unknown"
#endif
// How often to poll the command module for a new firmware binary.
#ifndef OTA_CHECK_INTERVAL_MS
#define OTA_CHECK_INTERVAL_MS (5 * 60 * 1000)
#endif

// ── Task stacks & priorities ──────────────────────────────────────────────────
#define CAMERA_TASK_STACK    8192
// TFLite Micro (XIAO) needs more stack than ESP-DL (S3-EYE)
#ifdef BOARD_XIAO_S3
#define INFERENCE_TASK_STACK 32768
#else
#define INFERENCE_TASK_STACK 16384
#endif
#define NETWORK_TASK_STACK   8192
#define OTA_TASK_STACK       8192
#ifndef MQTT_TASK_STACK
#define MQTT_TASK_STACK      8192
#endif

#define CAMERA_TASK_PRIORITY    5
#define INFERENCE_TASK_PRIORITY 4
#define NETWORK_TASK_PRIORITY   3
#define OTA_TASK_PRIORITY       1
#define MQTT_TASK_PRIORITY      2

// Camera pinned to core 0 (handles ISR), inference + network on core 1
#define CAMERA_TASK_CORE    0
#define INFERENCE_TASK_CORE 1
#define NETWORK_TASK_CORE   1

// ── Queue sizes ───────────────────────────────────────────────────────────────
// Only 1 frame deep — always process the freshest frame, drop stale ones
#define FRAME_QUEUE_DEPTH  1
#define EVENT_QUEUE_DEPTH  4

// ── Pin map ───────────────────────────────────────────────────────────────────
#ifdef BOARD_XIAO_S3
// Seeed XIAO ESP32S3 Sense
#define CAM_PIN_PWDN    -1
#define CAM_PIN_RESET   -1
#define CAM_PIN_XCLK    10
#define CAM_PIN_SIOD    40
#define CAM_PIN_SIOC    39
#define CAM_PIN_Y2      15
#define CAM_PIN_Y3      17
#define CAM_PIN_Y4      18
#define CAM_PIN_Y5      16
#define CAM_PIN_Y6      14
#define CAM_PIN_Y7      12
#define CAM_PIN_Y8      11
#define CAM_PIN_Y9      48
#define CAM_PIN_VSYNC   38
#define CAM_PIN_HREF    47
#define CAM_PIN_PCLK    13
#define LED_PIN         21
#else
// ESP32-S3-EYE
#define CAM_PIN_PWDN    -1
#define CAM_PIN_RESET   -1
#define CAM_PIN_XCLK    15
#define CAM_PIN_SIOD     4
#define CAM_PIN_SIOC     5
#define CAM_PIN_Y2      11
#define CAM_PIN_Y3       9
#define CAM_PIN_Y4       8
#define CAM_PIN_Y5      10
#define CAM_PIN_Y6      12
#define CAM_PIN_Y7      18
#define CAM_PIN_Y8      17
#define CAM_PIN_Y9      16
#define CAM_PIN_VSYNC    6
#define CAM_PIN_HREF     7
#define CAM_PIN_PCLK    13
#define LED_PIN          3
#endif
