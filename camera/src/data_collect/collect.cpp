#include "Arduino.h"
#include "esp_camera.h"
#include "FS.h"

#ifdef BOARD_XIAO_S3

#include "SD.h"
#include "SPI.h"
#define SD_SCK   7
#define SD_MISO  8
#define SD_MOSI  9
#define SD_CS   21
#define SAVE_DIR "/xiao"
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

#else  // ESP32-S3-EYE

#include "SD_MMC.h"
#define SD_CLK  39
#define SD_CMD  38
#define SD_D0   40
#define SAVE_DIR "/s3eye"
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

#endif

static int frame_idx = 0;

static bool init_camera()
{
    camera_config_t cfg = {};
    cfg.ledc_channel  = LEDC_CHANNEL_0;
    cfg.ledc_timer    = LEDC_TIMER_0;
    cfg.pin_d0        = CAM_PIN_Y2;
    cfg.pin_d1        = CAM_PIN_Y3;
    cfg.pin_d2        = CAM_PIN_Y4;
    cfg.pin_d3        = CAM_PIN_Y5;
    cfg.pin_d4        = CAM_PIN_Y6;
    cfg.pin_d5        = CAM_PIN_Y7;
    cfg.pin_d6        = CAM_PIN_Y8;
    cfg.pin_d7        = CAM_PIN_Y9;
    cfg.pin_xclk      = CAM_PIN_XCLK;
    cfg.pin_pclk      = CAM_PIN_PCLK;
    cfg.pin_vsync     = CAM_PIN_VSYNC;
    cfg.pin_href      = CAM_PIN_HREF;
    cfg.pin_sccb_sda  = CAM_PIN_SIOD;
    cfg.pin_sccb_scl  = CAM_PIN_SIOC;
    cfg.pin_pwdn      = CAM_PIN_PWDN;
    cfg.pin_reset     = CAM_PIN_RESET;
    cfg.xclk_freq_hz  = 20000000;
    cfg.frame_size    = FRAMESIZE_UXGA;   // 1600x1200 — max OV2640; downsample at training time
    cfg.pixel_format  = PIXFORMAT_JPEG;
    cfg.grab_mode     = CAMERA_GRAB_LATEST;
    cfg.fb_location   = CAMERA_FB_IN_PSRAM;
    cfg.jpeg_quality  = 4;
    cfg.fb_count      = 2;

    if (esp_camera_init(&cfg) != ESP_OK) {
        Serial.println("Camera init failed");
        return false;
    }

#ifndef BOARD_XIAO_S3
    sensor_t *s = esp_camera_sensor_get();
    s->set_vflip(s, 1);
#endif

    return true;
}

static bool init_sd()
{
#ifdef BOARD_XIAO_S3
    SPI.begin(SD_SCK, SD_MISO, SD_MOSI, SD_CS);
    if (!SD.begin(SD_CS)) {
        Serial.println("SD mount failed");
        return false;
    }
    if (!SD.exists(SAVE_DIR)) SD.mkdir(SAVE_DIR);
#else
    SD_MMC.setPins(SD_CLK, SD_CMD, SD_D0);
    if (!SD_MMC.begin("/sdcard", true)) {
        Serial.println("SD_MMC mount failed");
        return false;
    }
    if (!SD_MMC.exists(SAVE_DIR)) SD_MMC.mkdir(SAVE_DIR);
#endif
    Serial.printf("SD ready — saving to %s/\n", SAVE_DIR);
    return true;
}

static void save_frame(const uint8_t *buf, size_t len)
{
    char path[48];
    snprintf(path, sizeof(path), "%s/frame_%06d.jpg", SAVE_DIR, frame_idx++);

#ifdef BOARD_XIAO_S3
    File f = SD.open(path, FILE_WRITE);
#else
    File f = SD_MMC.open(path, FILE_WRITE);
#endif

    if (!f) {
        Serial.printf("Open failed: %s\n", path);
        return;
    }
    f.write(buf, len);
    f.close();
    Serial.printf("Saved %s (%u B)\n", path, len);
}

void setup()
{
    Serial.begin(115200);
    Serial.println("Peekaboo data collector starting");

    if (!init_camera()) { for (;;) delay(1000); }
    if (!init_sd())     { for (;;) delay(1000); }

    Serial.println("Recording — power off to stop");
}

void loop()
{
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) { delay(100); return; }

    save_frame(fb->buf, fb->len);
    esp_camera_fb_return(fb);

    delay(1000);  // 1 fps — enough frame diversity, manageable file count
}
