# Peekaboo Intelligence

**A portfolio demo of distributed IoT and edge AI.**

A privacy-first, edge-first home security system that demonstrates practical IoT patterns and on-device AI inference. Cameras (ESP32-S3) stream JPEG frames over local WiFi to a Jetson inference node running real-time person detection and face recognition—raw video never leaves the LAN, and no cloud services are involved in the detection pipeline.

> **Reference Architecture — No Hosted Demo**
> This repository is a deployable reference architecture. A production instance runs on private hardware; there is no hosted demo for the straightforward reason that the data is biometric and belongs to real people. To deploy your own instance, you need the hardware listed in [Prerequisites](#prerequisites) and your own camera placement. The code is the portfolio piece.

## IoT & Edge AI: Core Themes

**Why this project matters:**

This system demonstrates **two critical architectural shifts in modern computing**:

1. **IoT at the Edge** — Traditionally, IoT devices (cameras) sent raw streams to cloud infrastructure for processing. Here, we keep data local, reducing latency (frame → inference in <100ms) and improving privacy. Cameras self-register via MQTT, auto-update firmware over-the-air (OTA), and respond to commands via encrypted TLS channels. This showcases the distributed nature of modern IoT systems.

2. **Edge AI (Inference at the Source)** — Rather than shipping frames to remote cloud GPUs, we run state-of-the-art ML models locally on consumer-grade hardware (Jetson Orin Nano, ~$200). YOLOv8n person detection runs at 8ms/frame on CPU; face recognition at 15ms/frame on GPU. No API rate limits, no latency spikes, no dependency on internet connectivity.

**The payoff:** A system that is faster (<100ms end-to-end), cheaper (one-time hardware cost, no SaaS subscriptions), more private (data never leaves the LAN), and more resilient (offline-first architecture)—demonstrating why edge AI is becoming the norm for real-time IoT deployments.

## Reference Architecture — No Live Demo (By Design)

This repository is a **deployable reference architecture**, not a hosted service. A production instance runs on private home hardware with real family members' biometric data. There is no public demo for the obvious reason: face recognition data belongs to real people, and sanitizing it for public consumption would defeat the entire point of building a privacy-first system.

If you want to evaluate this system, deploy it yourself. That's the design. The code, the architecture, the IoT patterns, and the performance numbers are the artifacts. People working in this space understand: you can't fake a real face recognition system.

To get started, see [Prerequisites](#prerequisites) and [Quick Start](#quick-start) below.

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
│ • MQTT control       │    │ • Session management       │    │ • Firestore database    │
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

## IoT Patterns Demonstrated

This project showcases real-world IoT architecture patterns:

### Distributed Device Management
- **Self-registration** — Cameras announce themselves on boot via `/api/cameras/register`, no manual provisioning
- **Heartbeats** — Cameras ping the command module every 60 seconds to report status (motion, uptime, IP changes)
- **Device lifecycle** — Support for multi-tenancy: cameras, inference nodes, and control modules operate independently; adding a new camera requires only WiFi credentials

### Secure Command & Control
- **Encrypted MQTT** — All device-to-device communication via TLS 1.2 on port 8883; per-device credentials prevent unauthorized command injection
- **Stateless handshake** — Commands include nonces (replay protection); cameras ignore duplicates within 8-minute window
- **Async acknowledgment** — Commands sent via MQTT; responses come back asynchronously via REST callbacks (cameras poll `/api/cameras/{id}/config` for pending commands)

### Over-the-Air (OTA) Updates
- **Versioned channels** — Firmware binaries stored per board type (`s3eye`, `xiao`); each channel maintains independent version history
- **Smart polling** — Cameras poll `/api/firmware/{channel}/check` on boot and every 5 minutes; only download if newer version available
- **Atomic updates** — Firmware downloaded in full, checksum-verified, then applied; rollback via forced re-flash if corruption detected

### Edge Inference Pipeline
- **Session-based processing** — Camera streams frames in bursts during motion; inference service groups them into sessions for person tracking
- **Cross-device context** — Inference service deduplicates detections across all cameras; a person entering frame A gets matched against all faces seen in frame B (if recent)
- **Local fallback** — If command module is unreachable, inference service continues operating with last-known state (arm/disarm, person registry)

## Services

| Service | Host | Port | Notes |
|---|---|---|---|
| Command Module | R5 (`192.168.1.105`) | `8081` | FastAPI; `network_mode: host` |
| Inference Service | Jetson (`192.168.1.108`) | `8001` | FastAPI + InsightFace; NVIDIA runtime |
| Person Detector | Jetson (`192.168.1.108`) | `8002` | YOLOv8n ONNX; CPU-only sidecar |
| Firestore (Google Cloud) | Cloud | — | Person embeddings, audit logs, events, webhooks |
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
├── docker-compose.yml   # Orchestration: mqtt, command-module on R5
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

## Edge AI Trade-offs: A Real-World Lesson

**The original vision:** Run TFLite person detection directly on each ESP32-S3 to filter frames before uploading—true edge AI, minimal bandwidth, maximum privacy. Only send frames when a person is detected locally.

**What we learned:**

This revealed a hard truth about edge AI: not all hardware can run modern ML models efficiently. TFLite's optimized ONNX assembly kernels (esp-nn) cannot write to PSRAM on ESP32-S3 systems with PIE (Position Independent Executable) enabled, causing immediate crashes. The workaround (`CONFIG_NN_ANSI_C=y`, forcing portable C kernels) fixed the crash but delivered only ~0.6 fps—too slow to be useful as a gate, and too unreliable for production.

**The pragmatic solution:** Centralize inference on the Jetson. YOLOv8n runs at 8ms/frame on CPU-only; face recognition at 15ms/frame on GPU with GPU acceleration (InsightFace buffalo_l). Cameras became thin JPEG streamers.

**Why this matters:** This trade-off is the reality of edge AI in 2026. True edge inference on microcontrollers (ESP32, ARM Cortex-M) only works for tiny quantized models (<1MB). For production-grade computer vision, you need a capable edge node (Jetson, TPU, GPU). The lesson: pick the right layer for ML (not "as close to the sensor as possible," but "close enough to matter"). Cameras handle networking and persistence; inference nodes handle smarts. This is the emerging architecture for scalable IoT AI systems.

## Performance & Why Edge AI Matters

### Latency Comparison

| Stage | Latency | Hardware |
|-------|---------|----------|
| Frame capture → network | ~30ms | ESP32-S3 @ 115200 baud UART |
| Network transit (WiFi) | ~10ms | Local LAN (5GHz) |
| **Inference** | **8ms** | Jetson CPU (YOLOv8n) |
| Face recognition | ~15ms | Jetson GPU (InsightFace) |
| **Total (edge)** | **~63ms** | All local, no cloud |
| **Cloud alternative** | **500ms–2s** | Upload → cloud GPU → response |

**What this means:**

- **Responsiveness:** Motion detection → alert in <100ms (human-perceptible instant)
- **Privacy:** Raw frames never leave the LAN; only metadata (detections, alerts) possible to export
- **Reliability:** System works offline; no cloud outages, no API rate limits, no vendor SLAs
- **Cost:** One-time hardware ($200 Jetson) vs. recurring cloud inference costs (≈$100/month per camera at scale)

### Scalability on a Budget

| Model | FPS @ CPU | FPS @ GPU | Power | Cost |
|-------|-----------|-----------|-------|------|
| YOLOv8n (light) | 125 fps | 300+ fps | <5W | Jetson ($200) |
| YOLOv8m (medium) | 40 fps | 100+ fps | <10W | — |
| MobileNetV2 (tiny) | 400+ fps | 600+ fps | <2W | — |

A single Jetson Orin Nano can process 4–6 simultaneous camera streams in real-time, making it cost-effective for home deployments. For larger installations, scale to Jetson AGX Orin (8+ streams) or build a cluster behind a load balancer.

## Prerequisites

### Hardware

**Command Tier (Control Module & Database)**
- Any x86-64 or ARM workstation running Linux, macOS, or WSL2 with Docker & Docker Compose
- Minimum: 2 cores, 4GB RAM; recommended: 4+ cores, 8GB RAM
- Example: R5 Ryzen 5 (used in this deployment), Intel NUC, Raspberry Pi 5, used laptop

**Inference Tier (Edge AI)**
- **Jetson Orin Nano 8GB** (~$200–250, includes NVIDIA GPU, optimized for YOLOv8 + face recognition)
  - Requires NVIDIA Container Runtime for GPU acceleration
  - Alternative: Jetson Orin NX 8GB (smaller, same performance), Jetson AGX Orin (4–8 simultaneous streams)
  - CPU-only inference possible but slow (YOLOv8 ~40ms/frame instead of 8ms)

**Camera Tier (IoT Devices)**
- **ESP32-S3-EYE** (~$40–50, built-in OV2640 camera, no soldering)
  - OR **XIAO ESP32-S3 Sense** (~$15 board + ~$10 OV2640 camera module, compact form factor)
- Both share the same firmware (`src/s3eye/`), selected at build time via PlatformIO

**Networking**
- WiFi 5GHz network (2.4GHz works but slower for video)
- Router with stable LAN connectivity (no internet required for inference pipeline)
- Optional: TLS certificates for encrypted MQTT (self-signed generation included)

**Development Tools**
- PlatformIO CLI (`pip install platformio`) for firmware builds
- Python 3.10+ with pip for backend dev
- Docker & Docker Compose (for orchestration)
- Git (to clone this repo)

### Software

- Linux (Ubuntu 22.04+ recommended for Jetson), or Docker Desktop on macOS/Windows
- Python 3.10+
- Docker & Docker Compose
- PlatformIO (open-source, integrated with VSCode)

### Estimated Cost (Single-Camera Deployment)

| Component | Cost | Notes |
|-----------|------|-------|
| Jetson Orin Nano 8GB | $200–250 | Reusable across projects |
| ESP32-S3-EYE camera | $40–50 | Add $15–25 per additional camera |
| Workstation | $100–500+ | Often a spare laptop/NUC |
| USB cables, micro-SD, power | $30–50 | Standard off-the-shelf |
| **Total** | **$370–850** | One-time cost; no recurring subscriptions |

**Comparison:** Cloud-based security system (e.g., Google Nest Hub, Ring) costs $100–200 upfront + $10–20/month per camera. This breaks even in 12–24 months and eliminates vendor lock-in.

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — set GCP project ID, MQTT credentials, Jetson URL, webhook secrets
# Ensure GOOGLE_APPLICATION_CREDENTIALS points to your Firestore service account JSON
```

### 2. Start the Command Tier (R5)

```bash
docker compose up -d
```

Starts `peekaboo-mqtt` (Mosquitto, ports 1883/8883) and `peekaboo-command` (Command Module, port 8081).
The Command Module connects to Google Cloud Firestore for all data storage (see `.env` for credentials).

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
# Set up Firestore credentials (service account JSON)
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/gcp-sa.json
export GCP_PROJECT_ID=your-gcp-project
# Run the app
uvicorn src.main:app --reload --port 8081
```

## Testing

### Run Tests

```bash
cd command-module
pytest tests/ -v
```

### Test Coverage

The test suite covers:

- **Unit tests** — Individual endpoint handlers with mocked database and MQTT
- **Input validation** — Format checks, size limits, SSRF blocking, path traversal prevention
- **Authentication** — Bearer token validation, rate limit enforcement
- **Integration tests** — Full API flows (camera registration, person enrollment, firmware upload)

Mock patterns:
- Firestore queries mocked with in-memory dictionaries
- MQTT publish calls captured and verified
- External service calls (inference, webhooks) stubbed

---

## Design Decisions

### Architecture Choices

**Why Firestore instead of PostgreSQL?**
- Firestore's audit logging capabilities are built-in and immutable (append-only)
- Schema-less design accommodates rapid prototyping (person embeddings can grow without migrations)
- Serverless billing matches low-traffic home deployment
- Trade-off: no complex joins or transactions; application enforces referential integrity

**Why MQTT instead of REST for device control?**
- Cameras may be offline or changing IPs; MQTT persists messages via broker until delivery
- Bidirectional: cameras can send heartbeats and reports asynchronously, independent of command timing
- Per-device subscriptions enable granular access control (each camera only reads its own topic)
- Trade-off: introduces a stateful broker dependency; REST would be simpler but less reliable

**Why centralized inference on Jetson instead of distributed edge inference?**
- Microcontroller inference (ESP32-S3) works only for tiny quantized models; YOLOv8n doesn't fit efficiently
- Centralized inference enables cross-camera person tracking (same person detected on camera A → camera B recognizes them immediately)
- Jetson is cost-effective: $200 one-time vs. cloud GPU subscriptions ($100+/month)
- Trade-off: inference latency (8ms) is acceptable for real-time video analysis but wouldn't work for sub-millisecond requirements

**Why session-based processing instead of frame-by-frame?**
- Grouping frames by motion event reduces false positives (random noise → person detection → confirmed or rejected)
- Sessions enable temporal context: "this face was seen 10 seconds ago, same session" vs "new person"
- Trade-off: adds complexity; requires motion detection + frame buffering on cameras

**Why TLS + per-device MQTT credentials instead of public MQTT?**
- Each device has unique credentials; compromised credential only exposes that one camera, not the whole system
- TLS prevents MITM attacks in home WiFi environments
- Trade-off: requires certificate generation and embedding in firmware; adds deployment complexity

---

## Security

Peekaboo Intelligence implements security at every layer:

### Authentication & Authorization
- **API Key authentication** — All endpoints require Bearer token (see [config.py](command-module/src/config.py))
- **Per-device MQTT credentials** — Each camera has unique username/password; see [docs/MQTT_SETUP.md](docs/MQTT_SETUP.md)
- **Audit logging** — All state-changing actions (camera registration, person enrollment, firmware upload, arm/disarm) logged to Firestore with timestamp, actor, and result; see [docs/AUDIT_LOGGING.md](docs/AUDIT_LOGGING.md)

### Input Validation
- **Format validation** — Camera IDs, channel names, person IDs matched against strict regex patterns
- **Size limits** — JPEG images capped at 5MB, firmware binaries at 10MB, base64 frames at 6MB
- **SSRF protection** — Webhook URLs validated to block private IP ranges (10.0.0.0/8, 192.168.0.0/16, etc.); see [validation.py](command-module/src/validation.py)
- **MIME type validation** — Images restricted to JPEG/PNG, firmware to octet-stream

### Rate Limiting
- **Per-endpoint limits** — Camera registration (10/min), firmware upload (5/min), person enrollment (20/min), general endpoints (100/min)
- **Enforcement** — slowapi library; responses include `Retry-After` header
- Prevents quota exhaustion and brute-force attacks

### Infrastructure
- **HTTPS/TLS** — Self-signed certificates for internal LAN (optional; setup in [docs/HTTPS_SETUP.md](docs/HTTPS_SETUP.md))
- **MQTT over TLS** — Cameras connect to broker on port 8883 with certificate validation
- **Nonce-based replay protection** — Commands include nonces; duplicates within 8-minute window are rejected

### Privacy
- **Local-only inference** — Raw video frames never leave the LAN; only metadata (detections, alerts) exit
- **No cloud dependency** — System operates completely offline if needed; no third-party API keys or data transmission
- **Encrypted storage** — Person embeddings and recordings encrypted at rest in Firestore

---

## CI/CD

The project includes automated testing and security scanning via GitHub Actions.

### Pipeline Stages

| Stage | Tools | Purpose |
|-------|-------|---------|
| **Security Scans** | Bandit, TruffleHog, pip-audit | SAST, secrets detection, dependency vulnerabilities |
| **Linting** | pylint, black | Code style enforcement |
| **Build** | Docker, PlatformIO | Firmware compilation for ESP32-S3 boards |
| **Type Checking** | mypy | Python type validation |

### Workflow Files

- `.github/workflows/ci.yml` — Main meta-workflow orchestrating all stages
- `.github/workflows/security-scans.yml` — Bandit + TruffleHog + pip-audit
- `.github/workflows/test-backend.yml` — pytest suite
- `.github/workflows/build-frontend.yml` — Vue.js dashboard build
- `.github/workflows/build-firmware.yml` — PlatformIO compile for all camera boards

See `.github/WORKFLOWS.md` for detailed stage descriptions.

### Running Locally

To run security scans and tests before pushing:

```bash
# Security scans
bandit -r command-module/src/
trufflehog filesystem . --json

# Tests
cd command-module && pytest tests/ -v

# Firmware build (requires PlatformIO)
cd camera && pio run -e esp32s3eye
```

---

## Documentation

Key architectural and operational docs:

| Document | Purpose |
|----------|---------|
| [docs/SETUP.md](docs/SETUP.md) | End-to-end deployment guide for new instances |
| [docs/MQTT_SETUP.md](docs/MQTT_SETUP.md) | Per-device MQTT credential generation and ACL configuration |
| [docs/AUDIT_LOGGING.md](docs/AUDIT_LOGGING.md) | Audit trail schema, querying patterns, forensics examples |
| [docs/HTTPS_SETUP.md](docs/HTTPS_SETUP.md) | TLS certificate generation and deployment |
| [docs/IR-Camera.md](docs/IR-Camera.md) | Hardware limitations: why IR cameras aren't used (cost/performance analysis) |
| [docs/jetsonModels.md](docs/jetsonModels.md) | Jetson hardware options and inference benchmarks |
| [docs/PUBLIC_RELEASE_PLAN.md](docs/PUBLIC_RELEASE_PLAN.md) | GitHub public release checklist and status |

---

## License

[License to be added]
