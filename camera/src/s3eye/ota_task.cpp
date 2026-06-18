#include "ota_task.h"
#include "config.h"

#include "cJSON.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_heap_caps.h"
#include <string.h>

static const char *TAG = "ota";

static TaskHandle_t s_ota_task = nullptr;

void ota_request_check(void)
{
    if (s_ota_task) xTaskNotifyGive(s_ota_task);
}

#define OTA_BUF_SIZE    4096
#define CHECK_RESP_CAP  256

typedef struct {
    char buf[CHECK_RESP_CAP];
    int  len;
} check_resp_t;

static esp_err_t _check_event_cb(esp_http_client_event_t *evt)
{
    check_resp_t *r = (check_resp_t *)evt->user_data;
    if (!r || evt->event_id != HTTP_EVENT_ON_DATA) return ESP_OK;
    int copy = evt->data_len;
    if (r->len + copy >= CHECK_RESP_CAP) copy = CHECK_RESP_CAP - r->len - 1;
    if (copy > 0) {
        memcpy(r->buf + r->len, evt->data, copy);
        r->len += copy;
        r->buf[r->len] = '\0';
    }
    return ESP_OK;
}

static bool update_available(void)
{
    char url[256];
    snprintf(url, sizeof(url), "%s/api/firmware/%s/check?version=%s",
             COMMAND_MODULE_URL, FIRMWARE_CHANNEL, FIRMWARE_VERSION);

    check_resp_t resp = {};
    esp_http_client_config_t cfg = {};
    cfg.url           = url;
    cfg.timeout_ms    = 10000;
    cfg.user_data     = &resp;
    cfg.event_handler = _check_event_cb;

    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    esp_http_client_set_header(client, "Authorization", "Bearer " SECRET_PSK);
    esp_err_t err = esp_http_client_perform(client);
    int status = (err == ESP_OK) ? esp_http_client_get_status_code(client) : -1;
    esp_http_client_cleanup(client);

    if (status != 200 || resp.len == 0) return false;

    cJSON *root = cJSON_Parse(resp.buf);
    if (!root) return false;
    cJSON *avail = cJSON_GetObjectItem(root, "update_available");
    bool result = avail && cJSON_IsTrue(avail);
    if (result) {
        cJSON *ver = cJSON_GetObjectItem(root, "version");
        ESP_LOGI(TAG, "Update available: %s → %s",
                 FIRMWARE_VERSION, ver ? ver->valuestring : "?");
    }
    cJSON_Delete(root);
    return result;
}

static void apply_update(void)
{
    char url[256];
    snprintf(url, sizeof(url), "%s/api/firmware/%s/binary",
             COMMAND_MODULE_URL, FIRMWARE_CHANNEL);

    const esp_partition_t *update_part = esp_ota_get_next_update_partition(NULL);
    if (!update_part) {
        ESP_LOGE(TAG, "No OTA partition found — is the partition table correct?");
        return;
    }
    ESP_LOGI(TAG, "Writing to partition '%s' from %s", update_part->label, url);

    esp_ota_handle_t ota_handle;
    esp_err_t err = esp_ota_begin(update_part, OTA_WITH_SEQUENTIAL_WRITES, &ota_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_ota_begin: %s", esp_err_to_name(err));
        return;
    }

    esp_http_client_config_t cfg = {};
    cfg.url         = url;
    cfg.timeout_ms  = 60000;
    cfg.buffer_size = OTA_BUF_SIZE;

    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    esp_http_client_set_header(client, "Authorization", "Bearer " SECRET_PSK);

    err = esp_http_client_open(client, 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HTTP open: %s", esp_err_to_name(err));
        esp_ota_abort(ota_handle);
        esp_http_client_cleanup(client);
        return;
    }

    esp_http_client_fetch_headers(client);
    int status = esp_http_client_get_status_code(client);
    if (status != 200) {
        ESP_LOGE(TAG, "Server returned HTTP %d", status);
        esp_ota_abort(ota_handle);
        esp_http_client_cleanup(client);
        return;
    }

    char *buf = (char *)heap_caps_malloc(OTA_BUF_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!buf) {
        ESP_LOGE(TAG, "OTA buffer alloc failed");
        esp_ota_abort(ota_handle);
        esp_http_client_cleanup(client);
        return;
    }

    int total = 0, read_len;
    while ((read_len = esp_http_client_read(client, buf, OTA_BUF_SIZE)) > 0) {
        err = esp_ota_write(ota_handle, buf, read_len);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "esp_ota_write: %s", esp_err_to_name(err));
            heap_caps_free(buf);
            esp_ota_abort(ota_handle);
            esp_http_client_cleanup(client);
            return;
        }
        total += read_len;
    }
    heap_caps_free(buf);
    esp_http_client_cleanup(client);
    ESP_LOGI(TAG, "Downloaded %d bytes", total);

    err = esp_ota_end(ota_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_ota_end: %s", esp_err_to_name(err));
        return;
    }

    err = esp_ota_set_boot_partition(update_part);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_ota_set_boot_partition: %s", esp_err_to_name(err));
        return;
    }

    ESP_LOGI(TAG, "OTA complete — rebooting in 2s");
    vTaskDelay(pdMS_TO_TICKS(2000));
    esp_restart();
}

void ota_task(void *arg)
{
    s_ota_task = xTaskGetCurrentTaskHandle();

    // Give the network task time to establish WiFi before the first check.
    vTaskDelay(pdMS_TO_TICKS(60000));

    ESP_LOGI(TAG, "OTA task running — channel=%s version=%s", FIRMWARE_CHANNEL, FIRMWARE_VERSION);

    for (;;) {
        if (update_available()) {
            apply_update();
            // apply_update() only returns on failure; log and retry next cycle.
            ESP_LOGW(TAG, "OTA failed — will retry in %d ms", OTA_CHECK_INTERVAL_MS);
        }
        // Sleep until the poll interval elapses or an ota_request_check() wakes
        // us early (e.g. an ota_check command over MQTT).
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(OTA_CHECK_INTERVAL_MS));
    }
}
