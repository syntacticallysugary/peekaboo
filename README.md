# Peekaboo Intelligence

A privacy-first, edge-first home security system. Cameras stream JPEG frames over the local network to a Jetson inference node that runs person detection and face recognition — raw video never leaves the local network, and no cloud services are involved in the detection pipeline.

## Architecture

Three tiers communicate over a local WiFi network:

```
┌──────────────────────┐    ┌───────────────────────────┐    ┌─────────────────────────┐
│     Camera Tier      │    │      Inference Tier        │    │     Command Tier        │
│  ESP32-S3-EYE /      │    │    Jetson Orin Nano        │    │   R5 Workstation        │
│  XIAO ESP32-S3 Sense │    │   (inference-service/)     │    │   (command-module/)     │
│  (camera/)           │    │                            │    │                         │
│                      │    │ • YOLOv8n person detector  │    │ • FastAPI REST API      │
│ • JPEG frame stream  │───►│ • InsightFace recognition  │───►│ • Person registry       │
│ • Motion heartbeat   │    │   (buffalo_l model)        │    │ • Alert dispatch        │
│ • MQTT control       │    │ • Session management       │    │ • PostgreSQL + pgvector │
│ • OTA updates        │    │ • Arm/disarm enforcement   │    │ • MQTT broker           │
│                      │    │                            │    │ • WebSocket dashboard   │
└──────────────────────┘    └───────────────────────────┘    └─────────────────────────┘
```

## Data Flow

**Normal operation:**
```
Camera → POST /session/frame → Inference Service
                                     │
                          YOLOv8n person detector
                                     │
                          InsightFace face detection
                          + recognition
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
              known person                    unknown face / person
         POST /api/cameras/report           POST /api/alerts
                    │                                 │
                    └──────────────┬──────────────────┘
                                   │
                            Command Module
```

**OTA firmware updates:**
```
Command Module stores firmware binaries per channel (s3eye, xiao).
Camera OTA task polls /api/firmware/{channel}/check on boot and every 5 minutes.
If a newer version is available, the camera self-updates and reboots.
```

**Arm/disarm:**
```
Command Module → POST /system/armed → Inference Service
```
When disarmed, the inference service discards all in-progress sessions immediately
and stops recording. Cameras continue streaming; detection resumes on re-arm.

## Services

| Service | Host | Port | Notes |
|---|---|---|---|
| Command Module | R5 (`192.168.1.105`) | `8081` | FastAPI; `network_mode: host` |
| Inference Service | Jetson (`192.168.1.108`) | `8001` | FastAPI + InsightFace; NVIDIA runtime |
| Person Detector | Jetson (`192.168.1.108`) | `8002` | YOLOv8n ONNX; CPU-only sidecar |
| PostgreSQL (pgvector) | R5 | `5435` | Person embeddings + event log |
| Mosquitto MQTT | R5 | `8883` (TLS/LAN), `1883` (loopback) | Cameras connect via TLS on 8883 |

## Repository Layout

```
PI/
├── command-module/      # FastAPI app — camera registry, person mgmt, alerts, dashboard
│   ├── src/
│   │   ├── api/         # REST routes: cameras, persons, events, recordings, alerts,
│   │   │                #   firmware, system (arm/disarm/schedule), webhooks
│   │   ├── orchestration/ # LangGraph workflow nodes and state
│   │   ├── services/    # camera registry, inference client, webhook dispatcher
│   │   ├── db/          # SQLAlchemy models and database helpers
│   │   ├── storage/     # local / S3 storage backend abstraction
│   │   └── websocket/   # WebSocket dashboard event stream
│   └── frontend/        # React dashboard
├── inference-service/   # FastAPI app — person detection + face recognition (Jetson)
│   ├── src/             # Inference service: session management, InsightFace, alerts
│   └── person-detector/ # YOLOv8n ONNX person presence detector (separate process)
├── camera/              # ESP32-S3 firmware (PlatformIO / ESP-IDF)
│   └── src/
│       ├── s3eye/       # Main firmware: ESP32-S3-EYE and XIAO ESP32-S3 Sense
│       └── data_collect/ # Training data collection mode
├── mosquitto/           # Mosquitto config (TLS + auth)
├── docs/                # Architecture notes and planning docs
├── docker-compose.yml   # Command tier: db, mqtt, command-module on R5
├── init-db.sql          # pgvector schema bootstrap
└── .env                 # Secrets (not committed)
```

## Camera Boards

Two board families share the same `s3eye/` firmware source, selected at build time via PlatformIO environments:

| Board | PlatformIO env | Camera ID | Firmware channel |
|---|---|---|---|
| ESP32-S3-EYE | `esp32s3eye` | `s3eye-01` | `s3eye` |
| XIAO ESP32-S3 Sense | `xiao_s3_01` | `xiao-01` | `xiao` |

The XIAO build requires `CONFIG_NN_ANSI_C=y` in `sdkconfig.xiao_peekaboo.defaults` because
`esp-tflite-micro` is linked into all XIAO builds and its ONNX assembly kernels crash on PSRAM
without this flag. See [docs/](docs/) for details.

## Too Close to the (AI) Bleeding Edge

This project started with an ambitious goal: run on-device TFLite person detection on the ESP32-S3 to gate frame transmission to the Jetson. The idea was minimal compute at the edge — only send frames when motion or a person is detected locally.

The attempt revealed hard limits. TFLite's ONNX assembly kernels (esp-nn) cannot write to PSRAM on ESP32-S3 PIE-enabled systems, causing immediate crashes. The workaround (`CONFIG_NN_ANSI_C=y`, forcing portable C kernels) fixed the crash but left us with slow inference (~0.6 fps), high memory overhead, and fragile threshold tuning. Person detection worked but wasn't reliable enough to be a gate.

The solution: **centralize inference on the Jetson**. YOLOv8n runs fast enough on CPU-only (`8ms/frame`), faces get recognized with GPU-accelerated InsightFace, and cross-camera person tracking becomes tractable. Cameras became thin JPEG streamers. This trades minimal edge compute for architectural simplicity and better user experience — a reminder that "edge" and "AI" don't always go together.

## Prerequisites

- R5 workstation (or equivalent) running Docker and Docker Compose
- Jetson Orin Nano 8GB on the same local network, with NVIDIA Container Runtime
- One or more ESP32-S3-EYE or XIAO ESP32-S3 Sense boards
- PlatformIO CLI (`pip install platformio`) for firmware builds

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — set DB credentials, MQTT credentials, Jetson URL, webhook secrets
```

### 2. Start the Command Tier (R5)

```bash
docker compose up -d
```

Starts `peekaboo-db` (PostgreSQL + pgvector, port 5435), `peekaboo-mqtt` (Mosquitto, ports 1883/8883), and `peekaboo-command` (Command Module, port 8081).

### 3. Start the Inference Service (Jetson)

```bash
# On the Jetson — from inference-service/
docker compose -f docker-compose.yml up -d
```

Starts `peekaboo-inference` (port 8001) and `peekaboo-person-detector` (port 8002).

### 4. Build and flash firmware

```bash
cd camera

# ESP32-S3-EYE
pio run -e esp32s3eye -t upload

# XIAO ESP32-S3 Sense (requires BOOT+RST to enter bootloader — see below)
pio run -e xiao_s3_01 -t upload
```

**XIAO bootloader entry:** The BOOT and RST pads are near the USB-C end of the board.
Hold BOOT, press and release RST, release BOOT. The device enumerates as `303a:1001`.
After flashing, press RST once to boot the application.

## API Overview

### Command Module (`http://192.168.1.105:8081`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/cameras/register` | Camera self-registration on boot |
| `POST` | `/api/cameras/{id}/heartbeat` | Keepalive (proxied from Jetson) |
| `POST` | `/api/cameras/report` | Known-person or unknown-face event from Jetson |
| `POST` | `/api/alerts` | Unknown-person alert from Jetson |
| `POST` | `/api/cameras/{id}/reboot` | Remote camera reboot via MQTT |
| `POST` | `/api/cameras/{id}/ota-check` | Ask camera to poll for firmware immediately |
| `GET`  | `/api/cameras/{id}/config` | Per-camera config (WiFi, Jetson URL, MQTT) |
| `POST` | `/api/firmware/{channel}` | Upload firmware binary for a channel |
| `GET`  | `/api/firmware/{channel}/check` | Camera OTA version check |
| `GET`  | `/api/firmware/{channel}/binary` | Camera OTA binary download |
| `GET`  | `/api/persons` | List enrolled persons |
| `POST` | `/api/persons` | Enroll a new person |
| `POST` | `/api/persons/{id}/auto-enroll` | Add embedding from a recognized frame |
| `GET`  | `/api/recordings` | List recordings |
| `POST` | `/api/system/arm` | Arm the system |
| `POST` | `/api/system/disarm` | Disarm the system |
| `GET`  | `/api/system/schedule` | Get arm/disarm schedule |
| `POST` | `/api/system/schedule` | Set arm/disarm schedule |
| `GET`  | `/api/webhooks` | List configured webhooks |
| `POST` | `/api/webhooks` | Add a webhook |
| `GET`  | `/health` | Service health |
| `WS`   | `/ws/dashboard` | Real-time event stream |

### Inference Service (`http://192.168.1.108:8001`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/session/frame` | Receive JPEG frame from camera |
| `POST` | `/session/end` | Explicit session end |
| `POST` | `/system/armed` | Receive arm/disarm state from Command Module |
| `POST` | `/sync` | Receive updated person embeddings |
| `POST` | `/capture` | Arm face-capture mode for enrollment |
| `GET`  | `/snapshot/{camera_id}` | Latest frame from a camera |
| `GET`  | `/stream/{camera_id}` | MJPEG live stream |
| `GET`  | `/health` | Model load status |

## Development

### Command Module (local, without Docker)

```bash
cd command-module
pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://peekaboo:peekaboo@localhost:5435/peekaboo \
  uvicorn src.main:app --reload --port 8081
```

### Tests

```bash
cd command-module
pytest tests/
```
