#include "mqtt_task.h"
#include "config.h"
#include "ota_task.h"
#include "frame_stats.h"
#include "mqtt_ca_cert.h"  // generated at configure time from certs/mqtt_ca.pem

#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_sntp.h"
#include "esp_heap_caps.h"
#include "esp_netif.h"
#include "mqtt_client.h"
#include "cJSON.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
#include <time.h>

static const char *TAG = "mqtt";

static esp_mqtt_client_handle_t s_client = nullptr;

// ── Replay protection state ─────────────────────────────────────────────────
// Commands carry a nonce and a unix timestamp. We reject any command whose
// nonce we have seen recently, and (when the clock is set via SNTP) any command
// whose timestamp is outside a freshness window. The nonce ring closes the
// replay gap within the window; the timestamp closes it across longer spans.
static uint32_t s_seen_nonces[MQTT_NONCE_CACHE] = {0};
static int      s_nonce_idx = 0;

static bool nonce_seen_or_record(uint32_t nonce)
{
    for (int i = 0; i < MQTT_NONCE_CACHE; i++) {
        if (s_seen_nonces[i] == nonce) return true;
    }
    s_seen_nonces[s_nonce_idx] = nonce;
    s_nonce_idx = (s_nonce_idx + 1) % MQTT_NONCE_CACHE;
    return false;
}

static bool clock_is_set(void)
{
    return time(nullptr) > 1600000000;  // ~2020-09; anything earlier means SNTP hasn't synced
}

// ── Status publishing ───────────────────────────────────────────────────────
static void publish_status(const char *json)
{
    if (!s_client) return;
    esp_mqtt_client_publish(s_client, MQTT_STATUS_TOPIC, json, 0, 1, 0);
}

static void publish_event(const char *event)
{
    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "event", event);
    cJSON_AddStringToObject(root, "fw", FIRMWARE_VERSION);
    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (body) { publish_status(body); cJSON_free(body); }
}

static void publish_diag(void)
{
    wifi_ap_record_t ap = {};
    int rssi = (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) ? ap.rssi : 0;

    char ip_str[16] = "0.0.0.0";
    esp_netif_ip_info_t ip_info = {};
    esp_netif_t *netif = esp_netif_get_default_netif();
    if (netif && esp_netif_get_ip_info(netif, &ip_info) == ESP_OK)
        esp_ip4addr_ntoa(&ip_info.ip, ip_str, sizeof(ip_str));

    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "event",       "diag");
    cJSON_AddStringToObject(root, "fw",          FIRMWARE_VERSION);
    cJSON_AddStringToObject(root, "channel",     FIRMWARE_CHANNEL);
    cJSON_AddStringToObject(root, "ip",          ip_str);
    cJSON_AddNumberToObject(root, "uptime_s",    (double)(esp_timer_get_time() / 1000000));
    cJSON_AddNumberToObject(root, "free_heap",      (double)esp_get_free_heap_size());
    cJSON_AddNumberToObject(root, "free_iram",      (double)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
    cJSON_AddNumberToObject(root, "frames_captured", (double)g_frames_captured);
    cJSON_AddNumberToObject(root, "frames_dropped",  (double)g_frames_dropped_q);
    cJSON_AddNumberToObject(root, "frames_sent",     (double)g_frames_sent);
    cJSON_AddNumberToObject(root, "rssi",            rssi);
    cJSON_AddNumberToObject(root, "reset_reason",    (double)esp_reset_reason());
    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (body) { publish_status(body); cJSON_free(body); }
}

// ── Command handling ────────────────────────────────────────────────────────
static void handle_command(const char *data, int len)
{
    cJSON *root = cJSON_ParseWithLength(data, len);
    if (!root) {
        ESP_LOGW(TAG, "Dropping command: invalid JSON");
        return;
    }

    const cJSON *jcmd   = cJSON_GetObjectItem(root, "cmd");
    const cJSON *jnonce = cJSON_GetObjectItem(root, "nonce");
    const cJSON *jts    = cJSON_GetObjectItem(root, "ts");

    if (!cJSON_IsString(jcmd) || !cJSON_IsNumber(jnonce)) {
        ESP_LOGW(TAG, "Dropping command: missing cmd/nonce");
        cJSON_Delete(root);
        return;
    }

    // Freshness check — only when the clock is trustworthy (SNTP synced).
    if (clock_is_set() && cJSON_IsNumber(jts)) {
        long now = (long)time(nullptr);
        long skew = now - (long)jts->valuedouble;
        if (skew < -MQTT_CMD_WINDOW_S || skew > MQTT_CMD_WINDOW_S) {
            ESP_LOGW(TAG, "Dropping command '%s': stale ts (skew %lds)", jcmd->valuestring, skew);
            cJSON_Delete(root);
            return;
        }
    }

    // Replay check — reject a nonce we have already acted on.
    uint32_t nonce = (uint32_t)jnonce->valuedouble;
    if (nonce_seen_or_record(nonce)) {
        ESP_LOGW(TAG, "Dropping command '%s': replayed nonce %u", jcmd->valuestring, nonce);
        cJSON_Delete(root);
        return;
    }

    const char *cmd = jcmd->valuestring;
    ESP_LOGI(TAG, "Command accepted: %s (nonce %u)", cmd, nonce);

    if (strcmp(cmd, "diag") == 0) {
        publish_diag();
    } else if (strcmp(cmd, "ota_check") == 0) {
        publish_event("ota_check_requested");
        ota_request_check();
    } else if (strcmp(cmd, "reboot") == 0) {
        // Debounce: ignore reboots in the first window after boot so a flood (or
        // a message that slips through) cannot drive a continuous reboot loop.
        if (esp_timer_get_time() < (int64_t)MQTT_REBOOT_MIN_INTERVAL_S * 1000000) {
            ESP_LOGW(TAG, "Ignoring reboot: within %ds debounce after boot", MQTT_REBOOT_MIN_INTERVAL_S);
            publish_event("reboot_debounced");
        } else {
            ESP_LOGW(TAG, "Reboot commanded — rebooting in 1s");
            publish_event("rebooting");
            cJSON_Delete(root);
            vTaskDelay(pdMS_TO_TICKS(1000));
            esp_restart();
        }
    } else {
        ESP_LOGW(TAG, "Unknown command '%s' — ignored", cmd);
    }

    cJSON_Delete(root);
}

// ── MQTT events ─────────────────────────────────────────────────────────────
static void mqtt_event_handler(void *handler_args, esp_event_base_t base,
                               int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;
    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "Connected — subscribing to %s", MQTT_CMD_TOPIC);
        esp_mqtt_client_subscribe(s_client, MQTT_CMD_TOPIC, 1);
        publish_event("online");
        break;
    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "Disconnected from broker");
        break;
    case MQTT_EVENT_DATA:
        if (event->data_len > 0) handle_command(event->data, event->data_len);
        break;
    case MQTT_EVENT_ERROR:
        ESP_LOGW(TAG, "MQTT error (will auto-reconnect)");
        break;
    default:
        break;
    }
}

static void sntp_start(void)
{
    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "pool.ntp.org");
    esp_sntp_init();
}

void mqtt_task(void *arg)
{
    // Let the network task establish WiFi first.
    vTaskDelay(pdMS_TO_TICKS(8000));

    sntp_start();  // best-effort; replay protection degrades gracefully without it

    char uri[64];
    snprintf(uri, sizeof(uri), "mqtts://%s:%d", MQTT_BROKER_HOST, MQTT_BROKER_PORT);

    esp_mqtt_client_config_t cfg = {};
    cfg.broker.address.uri                 = uri;
    cfg.broker.verification.certificate    = MQTT_CA_CERT;
    cfg.credentials.username               = MQTT_USERNAME;
    cfg.credentials.authentication.password = MQTT_PASSWORD;
    cfg.session.keepalive                  = 30;
    cfg.session.last_will.topic            = MQTT_STATUS_TOPIC;
    cfg.session.last_will.msg              = "{\"event\":\"offline\"}";
    cfg.session.last_will.qos              = 1;
    cfg.session.last_will.retain           = 0;

    s_client = esp_mqtt_client_init(&cfg);
    if (!s_client) {
        ESP_LOGE(TAG, "Failed to init MQTT client — task exiting");
        vTaskDelete(nullptr);
        return;
    }

    esp_mqtt_client_register_event(s_client, MQTT_EVENT_ANY, mqtt_event_handler, nullptr);
    esp_mqtt_client_start(s_client);

    ESP_LOGI(TAG, "MQTT task running — broker %s, topic %s", uri, MQTT_CMD_TOPIC);

    // The esp-mqtt client runs its own task; nothing more to drive here.
    for (;;) vTaskDelay(portMAX_DELAY);
}
