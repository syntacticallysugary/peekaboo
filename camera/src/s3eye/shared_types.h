#pragma once
#include <stdint.h>
#include <stddef.h>

// ── Frame queue: camera → inference ──────────────────────────────────────────
// Heap-allocated JPEG buffer owned by inference task after dequeue.
typedef struct {
    uint8_t *buf;
    size_t   len;      // JPEG byte length
    uint32_t width;    // original frame width (for reference)
    uint32_t height;   // original frame height (for reference)
} frame_msg_t;

// ── Event queue: inference → network ─────────────────────────────────────────
// Sent when a human is detected; carries the full-frame JPEG for streaming.
typedef struct {
    uint8_t *jpeg;      // heap-allocated JPEG of full frame
    size_t   jpeg_len;
} event_msg_t;

// ── Runtime config ────────────────────────────────────────────────────────────
typedef struct {
    int   motion_threshold;  // pixel count
    int   jpeg_quality;      // 0–63 (ESP scale: 0=best)
} device_config_t;
