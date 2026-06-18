#include "network_task.h"
#include "config.h"
#include "shared_types.h"
#include "frame_stats.h"

#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_http_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/event_groups.h"
#include "mbedtls/base64.h"
#include "cJSON.h"
#include <string.h>
#include <time.h>
#include <algorithm>
using std::min;

#ifndef MIN
#define MIN(a,b) ((a)<(b)?(a):(b))
#endif

static const char *TAG = "network";

#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT      BIT1
#define WIFI_MAX_RETRY     10

static EventGroupHandle_t s_wifi_event_group;
static int  s_retry_count = 0;
static char s_camera_ip[16] = {};

// ── WiFi ──────────────────────────────────────────────────────────────────────
static void wifi_event_handler(void *arg, esp_event_base_t base,
                               int32_t event_id, void *event_data)
{
    if (base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        if (s_retry_count < WIFI_MAX_RETRY) {
            esp_wifi_connect();
            s_retry_count++;
            ESP_LOGW(TAG, "WiFi retry %d/%d", s_retry_count, WIFI_MAX_RETRY);
        } else {
            xEventGroupSetBits(s_wifi_event_group, WIFI_FAIL_BIT);
        }
    } else if (base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *ev = (ip_event_got_ip_t *)event_data;
        esp_ip4addr_ntoa(&ev->ip_info.ip, s_camera_ip, sizeof(s_camera_ip));
        ESP_LOGI(TAG, "IP: %s", s_camera_ip);
        s_retry_count = 0;
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

static bool wifi_connect(void)
{
    s_wifi_event_group = xEventGroupCreate();
    esp_netif_init();
    esp_event_loop_create_default();
    esp_netif_t *sta_netif = esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);

    esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID,    wifi_event_handler, nullptr, nullptr);
    esp_event_handler_instance_register(IP_EVENT,   IP_EVENT_STA_GOT_IP, wifi_event_handler, nullptr, nullptr);

    wifi_config_t wcfg = {};
    strncpy((char *)wcfg.sta.ssid,     WIFI_SSID,     sizeof(wcfg.sta.ssid)     - 1);
    strncpy((char *)wcfg.sta.password, WIFI_PASSWORD, sizeof(wcfg.sta.password) - 1);
    wcfg.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    esp_wifi_set_mode(WIFI_MODE_STA);
    esp_wifi_set_config(WIFI_IF_STA, &wcfg);
    esp_wifi_start();

    // On wall power the radio can run at full duty cycle. WIFI_PS_NONE keeps
    // the radio awake continuously, eliminating the per-packet beacon-wait
    // latency that caused frame POSTs to take 8+ seconds under MAX_MODEM.
    esp_wifi_set_ps(WIFI_PS_NONE);

    // Unique DHCP hostname per camera. Must be set after the netif is started
    // (esp_wifi_start), or it returns IF_NOT_READY and is silently ignored.
    // Without it every board presents the ESP-IDF default ("espressif"), and a
    // router that keys leases by client identifier can hand multiple cameras the
    // same IP — the address conflict that drops connections and reboot-loops the
    // loser.
    esp_err_t hn = esp_netif_set_hostname(sta_netif, CAMERA_ID);
    ESP_LOGI(TAG, "Set hostname '%s' -> %s", CAMERA_ID, esp_err_to_name(hn));

    esp_wifi_connect();

    EventBits_t bits = xEventGroupWaitBits(
        s_wifi_event_group, WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
        pdFALSE, pdFALSE, pdMS_TO_TICKS(15000));

    return (bits & WIFI_CONNECTED_BIT) != 0;
}

// ── HTTP helpers ──────────────────────────────────────────────────────────────
#define HTTP_RESPONSE_BUF 512

typedef struct {
    char buf[HTTP_RESPONSE_BUF];
    int  len;
} http_response_t;

static esp_err_t http_event_handler(esp_http_client_event_t *evt)
{
    http_response_t *resp = (http_response_t *)evt->user_data;
    if (evt->event_id == HTTP_EVENT_ON_DATA && resp) {
        int copy = MIN(evt->data_len, (int)(sizeof(resp->buf) - resp->len - 1));
        memcpy(resp->buf + resp->len, evt->data, copy);
        resp->len += copy;
        resp->buf[resp->len] = '\0';
    }
    return ESP_OK;
}

static int http_post_json(const char *url, const char *body, http_response_t *resp)
{
    esp_http_client_config_t cfg = {};
    cfg.url            = url;
    cfg.method         = HTTP_METHOD_POST;
    cfg.timeout_ms     = 8000;
    cfg.user_data      = resp;
    cfg.event_handler  = http_event_handler;

    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_header(client, "Authorization", "Bearer " SECRET_PSK);
    esp_http_client_set_post_field(client, body, strlen(body));

    esp_err_t err = esp_http_client_perform(client);
    int status = (err == ESP_OK) ? esp_http_client_get_status_code(client) : -1;
    esp_http_client_cleanup(client);
    return status;
}

// ── Base64 ────────────────────────────────────────────────────────────────────
static char *base64_encode_alloc(const uint8_t *data, size_t len)
{
    size_t out_len = 0;
    mbedtls_base64_encode(nullptr, 0, &out_len, data, len);
    char *buf = (char *)heap_caps_malloc(out_len + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!buf) return nullptr;
    mbedtls_base64_encode((unsigned char *)buf, out_len, &out_len, data, len);
    buf[out_len] = '\0';
    return buf;
}

// ── Jetson session endpoints ──────────────────────────────────────────────────

// Persistent HTTP client for /session/frame — reuses the TCP connection across
// frames so each POST pays only the data-transfer cost, not a full TCP
// handshake. On any transport error the handle is torn down and rebuilt on the
// next call, giving automatic reconnection without manual retry logic.
static esp_http_client_handle_t s_stream_client = nullptr;

static bool ensure_stream_client(void)
{
    if (s_stream_client) return true;

    char url[256];
    snprintf(url, sizeof(url), "%s/session/frame", JETSON_URL);

    esp_http_client_config_t cfg = {};
    cfg.url               = url;
    cfg.method            = HTTP_METHOD_POST;
    cfg.timeout_ms        = 8000;
    cfg.keep_alive_enable = true;

    s_stream_client = esp_http_client_init(&cfg);
    if (!s_stream_client) return false;

    esp_http_client_set_header(s_stream_client, "Content-Type", "application/json");
    esp_http_client_set_header(s_stream_client, "Authorization", "Bearer " SECRET_PSK);
    return true;
}

static void stream_frame(const uint8_t *jpeg, size_t jpeg_len)
{
    char *b64 = base64_encode_alloc(jpeg, jpeg_len);
    if (!b64) {
        ESP_LOGE(TAG, "base64 alloc failed");
        return;
    }

    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "camera_id", CAMERA_ID);
    cJSON_AddStringToObject(root, "frame",     b64);
    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    heap_caps_free(b64);

    if (!ensure_stream_client()) {
        ESP_LOGE(TAG, "HTTP client init failed");
        free(body);
        return;
    }

    esp_http_client_set_post_field(s_stream_client, body, strlen(body));
    esp_err_t err = esp_http_client_perform(s_stream_client);
    free(body);

    if (err != ESP_OK) {
        ESP_LOGW(TAG, "stream_frame failed (%s) — will reconnect", esp_err_to_name(err));
        esp_http_client_cleanup(s_stream_client);
        s_stream_client = nullptr;
        return;
    }

    int status = esp_http_client_get_status_code(s_stream_client);
    if (status >= 200 && status < 300) g_frames_sent++;
    ESP_LOGD(TAG, "session/frame → HTTP %d", status);
}

static void send_session_end(void)
{
    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "camera_id", CAMERA_ID);
    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);

    char url[256];
    snprintf(url, sizeof(url), "%s/session/end", JETSON_URL);

    http_response_t resp = {};
    int status = http_post_json(url, body, &resp);
    free(body);
    ESP_LOGI(TAG, "session/end → HTTP %d", status);
}

// ── Task ──────────────────────────────────────────────────────────────────────
void network_task(void *arg)
{
    network_task_args_t *args = (network_task_args_t *)arg;

    ESP_LOGI(TAG, "Connecting to WiFi...");
    if (!wifi_connect()) {
        ESP_LOGE(TAG, "WiFi failed — rebooting in 5s");
        vTaskDelay(pdMS_TO_TICKS(5000));
        esp_restart();
    }

    bool   in_session      = false;
    time_t last_frame_time = 0;

    ESP_LOGI(TAG, "Network task running — streaming to %s", JETSON_URL);

    event_msg_t evt;
    for (;;) {
        if (xQueueReceive(args->event_queue, &evt, pdMS_TO_TICKS(1000)) == pdTRUE) {
            stream_frame(evt.jpeg, evt.jpeg_len);
            heap_caps_free(evt.jpeg);

            if (!in_session) {
                in_session = true;
                ESP_LOGI(TAG, "Session started");
            }
            last_frame_time = time(nullptr);
        }

        // End session after SESSION_END_TIMEOUT_S of no frames
        if (in_session && (time(nullptr) - last_frame_time) >= SESSION_END_TIMEOUT_S) {
            send_session_end();
            in_session = false;
        }
    }
}
