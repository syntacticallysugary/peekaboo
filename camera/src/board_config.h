// src/board_config.h
#pragma once

// Board type detection - use integer macros for preprocessor comparison
#ifndef BOARD_TYPE
    #error "BOARD_TYPE must be defined via build flags (e.g., -D BOARD_TYPE=1 for ESP32-CAM, -D BOARD_TYPE=2 for ESP32-S3-SPY, -D BOARD_TYPE=3 for ESP32-S3-EYE)"
#endif

// Board type constants
#define BOARD_ESP32CAM 1
#define BOARD_ESP32S3SPY 2
#define BOARD_ESP32S3EYE 3

// Common pin definitions
#if BOARD_TYPE == BOARD_ESP32CAM
    // ESP32-CAM pin definitions
    #define BOARD_NAME "ESP32-CAM"
    #define HAS_CAMERA true
    #define LED_PIN 4
    #define BUTTON_PIN -1  // No button on ESP32-CAM
    
    // Camera pins for AI-Thinker ESP32-CAM
    #define PWDN_GPIO_NUM     32
    #define RESET_GPIO_NUM    -1
    #define XCLK_GPIO_NUM      0
    #define SIOD_GPIO_NUM     26
    #define SIOC_GPIO_NUM     27
    #define Y9_GPIO_NUM       35
    #define Y8_GPIO_NUM       34
    #define Y7_GPIO_NUM       39
    #define Y6_GPIO_NUM       36
    #define Y5_GPIO_NUM       21
    #define Y4_GPIO_NUM       19
    #define Y3_GPIO_NUM       18
    #define Y2_GPIO_NUM        5
    #define VSYNC_GPIO_NUM    25
    #define HREF_GPIO_NUM     23
    #define PCLK_GPIO_NUM     22

#elif BOARD_TYPE == BOARD_ESP32S3SPY
    // ESP32-S3-SPY pin definitions (ESP32-S3-CAM-11B compatible)
    #define BOARD_NAME "ESP32-S3-SPY"
    #define HAS_CAMERA true
    #define LED_PIN 38
    #define BUTTON_PIN 0
    
    // Camera pins for ESP32-S3-CAM-11B (OV2640)
    // These are the standard pins for ESP32-S3 with camera
    #define PWDN_GPIO_NUM     -1  // Not used on S3-CAM-11B
    #define RESET_GPIO_NUM    -1  // Not used on S3-CAM-11B
    #define XCLK_GPIO_NUM      4
    #define SIOD_GPIO_NUM     18
    #define SIOC_GPIO_NUM     17
    #define Y9_GPIO_NUM       40
    #define Y8_GPIO_NUM       41
    #define Y7_GPIO_NUM       42
    #define Y6_GPIO_NUM       12
    #define Y5_GPIO_NUM       10
    #define Y4_GPIO_NUM       11
    #define Y3_GPIO_NUM       13
    #define Y2_GPIO_NUM        9
    #define VSYNC_GPIO_NUM     6
    #define HREF_GPIO_NUM      14
    #define PCLK_GPIO_NUM      15

#elif BOARD_TYPE == BOARD_ESP32S3EYE
    // ESP32-S3-EYE pin definitions
    // Verified against Espressif CameraWebServer camera_pins.h (CAMERA_MODEL_ESP32S3_EYE)
    // Y2=D0(LSB) .. Y9=D7(MSB) — must match DVP bit order or JPEG SOI marker is corrupted
    #define BOARD_NAME "ESP32-S3-EYE"
    #define HAS_CAMERA true
    #define LED_PIN 3
    #define BUTTON_PIN -1

    // Camera pins for ESP32-S3-EYE (OV2640)
    #define PWDN_GPIO_NUM     -1
    #define RESET_GPIO_NUM    -1
    #define XCLK_GPIO_NUM     15
    #define SIOD_GPIO_NUM      4
    #define SIOC_GPIO_NUM      5
    #define Y2_GPIO_NUM       11
    #define Y3_GPIO_NUM        9
    #define Y4_GPIO_NUM        8
    #define Y5_GPIO_NUM       10
    #define Y6_GPIO_NUM       12
    #define Y7_GPIO_NUM       18
    #define Y8_GPIO_NUM       17
    #define Y9_GPIO_NUM       16
    #define VSYNC_GPIO_NUM     6
    #define HREF_GPIO_NUM      7
    #define PCLK_GPIO_NUM     13

#else
    #error "Unknown BOARD_TYPE. Must be 1 (ESP32-CAM), 2 (ESP32-S3-SPY), or 3 (ESP32-S3-EYE)"
#endif

// Helper macros
#define BOARD_HAS_CAMERA() (HAS_CAMERA)
#define GET_BOARD_NAME() BOARD_NAME
