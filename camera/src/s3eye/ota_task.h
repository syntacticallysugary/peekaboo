#pragma once

#ifdef __cplusplus
extern "C" {
#endif

void ota_task(void *arg);

// Wake the OTA task to check for a new firmware binary immediately, instead of
// waiting for the next poll interval. Safe to call from other tasks.
void ota_request_check(void);

#ifdef __cplusplus
}
#endif
