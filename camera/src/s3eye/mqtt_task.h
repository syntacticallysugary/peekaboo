#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// Secure MQTT control channel. Connects to the broker over TLS, authenticates
// with per-device username/password, subscribes to this camera's command topic,
// and handles a small allowlist of commands (reboot / diag / ota_check) with
// replay protection. Publishes boot, ack, and diagnostic messages to the
// camera's status topic.
void mqtt_task(void *arg);

#ifdef __cplusplus
}
#endif
