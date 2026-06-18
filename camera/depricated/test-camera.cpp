#define BOARD_TYPE 2  // ESP32-S3-SPY

#include <WiFi.h>
#include "board_config.h"
#include <esp_camera.h>

// WiFi credentials - configured via build flags for security
#ifndef WIFI_SSID
    #define WIFI_SSID "MISSING_WIFI_SSID"
#endif
#ifndef WIFI_PASSWORD
    #define WIFI_PASSWORD "MISSING_WIFI_PASSWORD"
#endif
const char* ssid = WIFI_SSID;
const char* password = WIFI_PASSWORD;

void setup() {
    Serial.begin(115200);
    
    // Setup LED and blink 3 times to signal boot start
    pinMode(LED_PIN, OUTPUT);
    for(int i = 0; i < 3; i++) {
        digitalWrite(LED_PIN, HIGH);
        delay(100);
        digitalWrite(LED_PIN, LOW);
        delay(100);
    }

    Serial.println("\n========================================");
    Serial.println("  ESP32 Camera Test");
    Serial.println("========================================");
    Serial.print("Board: ");
    Serial.println(BOARD_NAME);
    Serial.print("Has Camera: ");
    Serial.println(HAS_CAMERA ? "YES" : "NO");
    
#if HAS_CAMERA
    Serial.println("\nCamera Pin Configuration:");
    Serial.print("  PWDN:   GPIO ");
    Serial.println(PWDN_GPIO_NUM);
    Serial.print("  RESET:  GPIO ");
    Serial.println(RESET_GPIO_NUM);
    Serial.print("  XCLK:   GPIO ");
    Serial.println(XCLK_GPIO_NUM);
    Serial.print("  SIOD:   GPIO ");
    Serial.println(SIOD_GPIO_NUM);
    Serial.print("  SIOC:   GPIO ");
    Serial.println(SIOC_GPIO_NUM);
    Serial.print("  Y9:     GPIO ");
    Serial.println(Y9_GPIO_NUM);
    Serial.print("  Y8:     GPIO ");
    Serial.println(Y8_GPIO_NUM);
    Serial.print("  Y7:     GPIO ");
    Serial.println(Y7_GPIO_NUM);
    Serial.print("  Y6:     GPIO ");
    Serial.println(Y6_GPIO_NUM);
    Serial.print("  Y5:     GPIO ");
    Serial.println(Y5_GPIO_NUM);
    Serial.print("  Y4:     GPIO ");
    Serial.println(Y4_GPIO_NUM);
    Serial.print("  Y3:     GPIO ");
    Serial.println(Y3_GPIO_NUM);
    Serial.print("  Y2:     GPIO ");
    Serial.println(Y2_GPIO_NUM);
    Serial.print("  VSYNC:  GPIO ");
    Serial.println(VSYNC_GPIO_NUM);
    Serial.print("  HREF:   GPIO ");
    Serial.println(HREF_GPIO_NUM);
    Serial.print("  PCLK:   GPIO ");
    Serial.println(PCLK_GPIO_NUM);
    
    // Check for PSRAM
    Serial.print("\nPSRAM found: ");
    Serial.println(psramFound() ? "YES" : "NO");
    if (psramFound()) {
        // ESP32-S3 with Octal PSRAM - 8MB
        Serial.println("PSRAM size: 8192 KB (8MB Octal)");
    }
    
    // Camera configuration
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 10;
    config.fb_count = 2;

    // Initialize camera
    Serial.println("\nInitializing camera...");
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("Camera init FAILED with error 0x%x\n", err);
        Serial.println("Check your camera connections!");
    } else {
        Serial.println("Camera initialized successfully!");
        
        // Try to capture a frame
        Serial.println("\nCapturing test frame...");
        camera_fb_t *fb = esp_camera_fb_get();
        if (fb) {
            Serial.printf("SUCCESS! Frame captured: %d bytes, %dx%d\n", 
                         fb->len, fb->width, fb->height);
            esp_camera_fb_return(fb);
        } else {
            Serial.println("Frame capture FAILED!");
        }
    }
#endif

    Serial.println("\n========================================");
    Serial.println("Test complete. Press reset to restart.");
    Serial.println("========================================\n");
}

void loop() {
    // Do nothing - test is complete
    delay(1000);
}
