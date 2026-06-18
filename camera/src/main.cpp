#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include "board_config.h"

volatile uint32_t heartbeat_counter = 0;
#if HAS_CAMERA
esp_err_t camera_init_result = ESP_FAIL;
#endif

// Wraps a byte buffer as an Arduino Stream so HTTPClient can send it in chunks,
// working around the original ESP32 WiFi stack's fixed TCP send buffer limit.
class BufferStream : public Stream {
    const uint8_t *_buf;
    size_t _len, _pos;
public:
    BufferStream(const uint8_t *buf, size_t len) : _buf(buf), _len(len), _pos(0) {}
    int available() override { return _len - _pos; }
    int read()      override { return _pos < _len ? _buf[_pos++] : -1; }
    int peek()      override { return _pos < _len ? _buf[_pos]   : -1; }
    size_t write(uint8_t) override { return 0; }
    size_t readBytes(uint8_t *buf, size_t len) override {
        size_t n = min(len, _len - _pos);
        memcpy(buf, _buf + _pos, n);
        _pos += n;
        return n;
    }
};

void heartbeat_task(void*) {
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(5000));
        if (WiFi.status() != WL_CONNECTED) continue;
        heartbeat_counter++;
        HTTPClient http;
        String url = String(HUB_URL);
        url = url.substring(0, url.indexOf("/api/")) + "/api/heartbeat/cam_01";
        http.begin(url);
        http.addHeader("Content-Type", "text/plain");
        http.addHeader("Authorization", String("Bearer ") + SECRET_PSK);
        int code = http.POST(String(heartbeat_counter));
        if (code > 0) Serial.printf("Heartbeat OK (counter: %d)\n", heartbeat_counter);
        else          Serial.printf("Heartbeat failed: %d\n", code);
        http.end();
    }
}

// Only include camera if board has it
#if HAS_CAMERA
    #include <esp_camera.h>
#endif

// WiFi credentials - configured via build flags for security
#ifndef WIFI_SSID
    #define WIFI_SSID "MISSING_WIFI_SSID"
#endif
#ifndef WIFI_PASSWORD
    #define WIFI_PASSWORD "MISSING_WIFI_PASSWORD"
#endif
const char* ssid = WIFI_SSID;
const char* password = WIFI_PASSWORD;

// Hub server details - configured via build flags
#ifndef HUB_URL
    #define HUB_URL "http://localhost:8000/api/upload/cam_01"
#endif
#ifndef SECRET_PSK
    #define SECRET_PSK "default_psk"
#endif
const char* hub_url = HUB_URL;
const char* psk = SECRET_PSK;

void setup() {
    Serial.begin(115200);
    // Wait for USB CDC to enumerate and monitor to connect (native USB only)
    unsigned long t0 = millis();
    while (!Serial && (millis() - t0) < 10000) delay(100);
    delay(3000);  // extra window to connect monitor before camera init
    
    Serial.println("========================================");
    Serial.println("Peak-a-Boo ESP32 Pusher starting...");
    Serial.print("Board: ");
    Serial.println(BOARD_NAME);
    Serial.println("========================================");
    
    // Setup LED and blink 3 times to signal boot start
    pinMode(LED_PIN, OUTPUT);
    for(int i = 0; i < 3; i++) {
        digitalWrite(LED_PIN, HIGH);
        delay(100);
        digitalWrite(LED_PIN, LOW);
        delay(100);
    }

#if HAS_CAMERA
    Serial.println("========================================");
    Serial.println("Camera Initialization");
    Serial.println("========================================");
    
    // Check PSRAM first
    Serial.print("PSRAM found: ");
    Serial.println(psramFound() ? "Yes" : "No");
    
    // Camera configuration
    camera_config_t config = {};  // zero-init: avoids garbage in fields added by newer lib versions
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
    config.grab_mode = CAMERA_GRAB_LATEST;
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 10;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    Serial.println("QVGA JPEG, 2 frame buffers, PSRAM, 20MHz XCLK, GRAB_LATEST");

    // I2C scan: confirm OV2640 is electrically present before driver probe
    Serial.println("Scanning I2C bus (SDA=4, SCL=5)...");
    Wire.begin(SIOD_GPIO_NUM, SIOC_GPIO_NUM);
    int i2c_devices = 0;
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            Serial.printf("  Found device at 0x%02X\n", addr);
            i2c_devices++;
        }
    }
    if (i2c_devices == 0) {
        Serial.println("  No I2C devices found — camera hardware not responding");
    }
    Wire.end();

    // Initialize camera
    Serial.println("Initializing camera...");
    camera_init_result = esp_camera_init(&config);
    if (camera_init_result != ESP_OK) {
        Serial.printf("Camera init FAILED with error 0x%x — continuing without camera\n", camera_init_result);
    } else {
        Serial.println("Camera initialized successfully!");
        delay(2000);  // let OV2640 JPEG engine stabilize before first fb_get
    }
    
    // Test frame capture
    Serial.println("Testing frame capture...");
    camera_fb_t *test_fb = esp_camera_fb_get();
    if (test_fb) {
        Serial.printf("Test capture SUCCESS: %d bytes\n", test_fb->len);
        esp_camera_fb_return(test_fb);
    } else {
        Serial.println("Test capture FAILED!");
    }
#endif

    xTaskCreate(heartbeat_task, "heartbeat", 8192, nullptr, 1, nullptr);

    // Connect to WiFi (non-blocking — will retry in loop if it fails)
    WiFi.mode(WIFI_STA);
    WiFi.setMinSecurity(WIFI_AUTH_WPA2_PSK);
    WiFi.begin(ssid, password);
    Serial.print("Connecting to WiFi");
    int wifiAttempts = 0;
    while (WiFi.status() != WL_CONNECTED && wifiAttempts < 20) {
        delay(500);
        Serial.print(".");
        wifiAttempts++;
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi connected!");
        Serial.print("IP Address: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("\nWiFi not connected — will retry in loop.");
    }
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        static unsigned long last_reconnect = 0;
        if (millis() - last_reconnect > 10000) {
            last_reconnect = millis();
            WiFi.reconnect();
            Serial.println("WiFi reconnecting...");
        }
        delay(500);
        return;
    }

#if HAS_CAMERA
    if (camera_init_result != ESP_OK) {
        Serial.printf("Camera init failed (0x%x) — skipping capture\n", camera_init_result);
        delay(2000);
        return;
    }
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("========================================");
        Serial.println("Camera capture FAILED!");
        Serial.println("========================================");
        Serial.println("Possible causes:");
        Serial.println("1. Camera sensor not responding on I2C bus");
        Serial.println("2. Incorrect pin configuration");
        Serial.println("3. Hardware issue with camera module");
        Serial.println("4. PSRAM not functioning correctly");
        Serial.print("PSRAM found: ");
        Serial.println(psramFound() ? "Yes" : "No");
        Serial.println("========================================");
        delay(2000);
        return;
    }

    // Send to Hub
    if (WiFi.status() == WL_CONNECTED) {
        HTTPClient http;
        http.begin(hub_url);
        http.addHeader("Content-Type", "image/jpeg");
        http.addHeader("Authorization", String("Bearer ") + psk);
        http.addHeader("X-Camera-ID", "cam_01");  // Redundant with URL, but per spec

        BufferStream bs(fb->buf, fb->len);
        int httpResponseCode = http.sendRequest("POST", &bs, fb->len);

        if (httpResponseCode <= 0) {
            Serial.printf("Frame POST failed: %d\n", httpResponseCode);
        }

        http.end();
    } else {
        Serial.println("WiFi not connected!");
    }

    // Release frame buffer - critical for memory safety
    esp_camera_fb_return(fb);
#else
    // ESP32-S3-SPY: Simple LED blink test
    Serial.println("ESP32-S3-SPY running LED test...");
    digitalWrite(LED_PIN, HIGH);
    delay(1000);
    digitalWrite(LED_PIN, LOW);
    delay(1000);
#endif

}
