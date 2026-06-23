# Peekaboo Intelligence — Architecture & Design

## Overview

This document describes the **as-implemented** three-tier edge-first architecture for distributed home surveillance with privacy-first design: cameras stream only to local Jetson inference node (no cloud), face recognition runs on-device with a local person database, and the central command module orchestrates everything.

**Note:** See `deprecated/` directory for the original pre-implementation design docs (which proposed on-device face detection on cameras — abandoned due to resource constraints).

---

## Three-Tier Architecture

```
┌────────────────────────────────┐    ┌──────────────────────────┐    ┌──────────────────────────┐
│      Camera Tier               │    │   Inference Tier         │    │    Command Tier          │
│  ESP32-S3-EYE / XIAO S3 Sense  │    │  Jetson Orin Nano 8GB    │    │  R5 Workstation          │
│                                │    │                          │    │                          │
│ • JPEG capture                 │───►│ • YOLOv8n person detect  │───►│ • FastAPI REST API       │
│ • Motion detection             │    │ • InsightFace recognition│    │ • Person registry        │
│ • Frame heartbeat              │    │ • Session management     │    │ • Alert dispatch         │
│ • MQTT control channel         │    │ • Frame→face pipeline    │    │ • PostgreSQL + pgvector  │
│ • OTA firmware updates         │    │ • Arm/disarm enforcement │    │ • MQTT broker            │
│                                │    │                          │    │ • WebSocket dashboard    │
└────────────────────────────────┘    └──────────────────────────┘    └──────────────────────────┘
```

---

## Data Flow

### Session Lifecycle

1. **Frame arrives at Jetson:**
   - Camera POSTs JPEG frame (base64) to `/session/frame`
   - Jetson creates/retrieves session for this camera

2. **Person detection (YOLOv8n):**
   - Run inference on frame (`8ms` CPU-only)
   - If person detected → move to recognition
   - If no person → buffer/drop frame

3. **Face detection + recognition (InsightFace):**
   - Extract face crops from detection boxes
   - Run InsightFace recognition (`~50ms` GPU-accelerated)
   - Compare embeddings against known-person cache

4. **Action routing:**
   - **Known person:** End session, POST `/api/cameras/report` (arrival event) → triggers 15-minute global cooldown
   - **Unknown face:** Buffer frames, wait 5 seconds, then POST `/api/alerts` (unknown alert)
   - **False positive (no face ever detected):** Session expires after 300s → fire unknown-person alert (intruder may be backlit/obscured)
   - **Person leaves:** 12 consecutive frames without detection → end session, POST event

### System arm/disarm

- Command module POSTs `/system/armed` → Jetson discards in-progress sessions, stops recording
- Cameras continue streaming; inference resumes when re-armed
- No camera-side changes needed (Jetson enforces policy)

### OTA updates

- Cameras poll `/api/firmware/{channel}/check` every 5 minutes
- If newer version available: download `/api/firmware/{channel}/binary`, self-update, reboot
- Channels: `s3eye`, `xiao` (one per board family)

---

## Tier Details

### Camera (ESP32-S3)

**Firmware:** `camera/src/s3eye/` (ESP-IDF, shared for both board types)

**Tasks:**
- `camera_task` (core 0, priority 5) — ISR-safe frame capture, motion detection, queue to inference
- `inference_task` (core 1, priority 4) — JPEG pass-through: dequeue frame, base64 encode, queue to network
- `network_task` (core 1, priority 3) — POST `/session/frame` to Jetson, handle responses
- `mqtt_task` (core 1, priority 2) — Subscribe to control channel, handle reboot/restart/OTA commands
- `ota_task` (core 1, priority 1) — Poll for firmware updates, self-update on boot

**Motion detection:** JPEG byte-count delta (no decode). Heartbeat at 1000ms ensures sessions stay alive for stationary subjects.

**Credentials:** Provisioned at build time via cmake `file(WRITE)` from `.env`:
```
WIFI_SSID, WIFI_PASSWORD, MQTT_BROKER_HOST, MQTT_PASSWORD,
JETSON_URL, COMMAND_MODULE_URL, SECRET_PSK
```

**Hardware:**
- ESP32-S3-EYE: Integrated OV2640 (2MP, SXGA 1280×1024), 8MB OPI PSRAM
- XIAO ESP32-S3 Sense: Integrated OV3660 (2MP, similar res), 8MB OPI PSRAM
- Both have native USB (CDC), no external UART adapter needed

### Inference (Jetson)

**Services:**
- `peekaboo-inference` (FastAPI, port 8001) — session management, face recognition, alert dispatch
- `peekaboo-person-detector` (FastAPI, port 8002) — YOLOv8n ONNX inference (CPU-only, ~8ms/frame)

**Key endpoints:**
- `POST /session/frame` — receive JPEG, run person detection, queue for recognition if detected
- `POST /system/armed` — receive arm/disarm state from command module
- `POST /sync` — receive updated person embeddings from command module
- `GET /snapshot/{camera_id}` — live view (last frame captured)
- `GET /stream/{camera_id}` — MJPEG live stream

**Session state:**
- Per-camera sessions track: `any_person_detected`, `any_face_detected`, `best_similarity`, `best_unknown_frame_b64`
- Sessions auto-rotate at 60s (concluded) or 300s hard-max
- On rotation: if unknown face ever detected → fire alert; if no face ever detected → still fire alert (person without visible face)

**Recognition:**
- InsightFace `buffalo_l` model (high accuracy, requires GPU)
- Embeddings cached in memory (synced from command module via `/sync` endpoint)
- Similarity threshold: 0.55 (tuned for this deployment)

### Command Module (R5)

**Services:**
- `peekaboo-command` (FastAPI, port 8081) — REST API, LangGraph orchestration
- `peekaboo-db` (PostgreSQL + pgvector) — person embeddings, event log, recordings metadata
- `peekaboo-mqtt` (Mosquitto) — camera control channel (reboot, restart, OTA trigger)

**Key endpoints:**
- `/api/cameras/register` — camera self-registration
- `/api/cameras/{id}/heartbeat` — keepalive (cameras via Jetson proxy)
- `/api/alerts` — alert events from Jetson (unknown person, unallowed person)
- `/api/cameras/report` — known-person arrival events from Jetson
- `/api/persons` — person enrollment, enrollment capture, auto-enroll
- `/api/firmware/{channel}` — firmware upload, version check, binary download
- `/api/system/arm`, `/api/system/disarm` — arm/disarm (pushes to Jetson + cameras)
- `/api/system/schedule` — scheduled arm/disarm times
- `/ws/dashboard` — WebSocket for real-time UI updates

**Person database:**
- `persons` table: `person_id`, `name`, `is_blocked`
- `embeddings` table: `person_id`, `embedding` (pgvector), `source_camera`, `timestamp`
- `events` table: `camera_id`, `classification` (arrival/unknown/false_alarm), `person_id`, `recording_path`, `timestamp`

**Orchestration (LangGraph):**
- State machine routing unknown-face detection → record path
- Known-person → suppress recording (per 15-minute global cooldown)
- Blocked person → always record with priority
- Webhook dispatch for external integrations

---

## Known Limitations

1. **No IR/low-light recognition** — cameras are passive optical only (OV2640/OV3660). IR models exist but increase BOM cost; see `docs/IR-Camera.md` for hardware cost breakdown.
2. **Single inference node** — Jetson handles multiple cameras; if Jetson is unreachable, cameras buffer locally and continue sending (no fallback inference on camera).
3. **Cross-camera person tracking** — recognized persons are tracked globally via embeddings, but the UI does not yet correlate "same person across cameras" (feature in backlog).
4. **No motion-only recording mode** — currently all recording is tied to face detection or arm/disarm state.

---

## Design Decisions & Trade-offs

### Why centralized inference instead of on-device?

Original plan: TFLite person detection on ESP32-S3 to gate frame transmission.

**Why abandoned:**
- TFLite ONNX assembly kernels crash on ESP32-S3 PSRAM (PIE architecture constraint)
- Workaround (portable C kernels) reduced inference to ~0.6 fps
- High memory overhead left little headroom for stable WiFi/MQTT
- Person detection threshold tuning unreliable

**Result:** Cameras became thin JPEG streamers. Trade-off: higher WiFi/network cost, but simpler end-to-end system with better recognition accuracy (GPU-accelerated embeddings).

### Why YOLOv8n instead of on-device inference?

- Fast enough on Jetson CPU-only (~8ms/frame)
- No separate person-detector hardware or expensive model needed on each camera
- Single model serves all cameras, easy to update/retrain

### Why InsightFace for recognition?

- GPU-accelerated (critical for real-time multi-face scenarios)
- High accuracy with small embeddings (512D, pgvector-compatible)
- License-friendly (BSD) and well-maintained
- Can enroll from Jetson inference sessions (face crops) without requiring full face photos

### Why MQTT for camera control?

- Lightweight, reliable for LAN control channel (no HTTP polling from camera)
- TLS support for encrypted commands (HMAC nonce prevents replay)
- Decouples command dispatch from REST API (broker handles queuing/retry)

---

## See Also

- `../README.md` — High-level project overview
- `../../camera/README.md` — Firmware build & flash procedures
- `deprecated/` — Original pre-implementation design proposal
- `IR-Camera.md` — IR hardware cost/benefit analysis (private)
