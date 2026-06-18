# Peekaboo Intelligence

A privacy-first, edge-first home security system. Face recognition runs on the camera nodes themselves — raw video never leaves the local network.

## Architecture

Three tiers communicate over a local WiFi network:

```
┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────────────┐
│  Camera Tier    │    │   Inference Tier      │    │     Command Tier        │
│  ESP32-S3-EYE   │    │  Jetson Orin Nano     │    │   R5 Workstation        │
│  (camera/)      │    │  (inference-service/) │    │   (command-module/)     │
│                 │    │                      │    │                         │
│ • On-device     │───►│ • InsightFace         │    │ • FastAPI REST API      │
│   face detect   │    │   (buffalo_l model)   │    │ • LangGraph workflow    │
│ • Motion detect │    │ • Local identity      │    │ • PostgreSQL + pgvector │
│ • WiFi upload   │    │   cache               │    │ • MQTT                  │
│                 │    │ • /identify endpoint  │    │ • WebSocket dashboard   │
└─────────────────┘    └──────────────────────┘    └─────────────────────────┘
```

## Data Flow

**Path A — Motion only (no face detected on device):**
```
ESP32 → POST /api/cameras/{id}/motion → Command Module → LangGraph workflow
```

**Path B — Face detected on device (hot path):**
```
ESP32 → POST /identify → Jetson (face crop, base64)
                           │
                           ├─ action: "cooldown" → ESP32 suppresses locally
                           └─ action: "record"   → Jetson POST /api/cameras/report
                                                         → Command Module → LangGraph
```

**Known-persons sync:**
```
Command Module → POST /sync → Jetson (triggered on DB changes)
```

The Jetson is called directly by the ESP32 — not by the Command Module. The Jetson calls back to the Command Module only when a recording event is warranted.

## Services

| Service | Location | Port | Notes |
|---|---|---|---|
| Command Module | R5 workstation (`192.168.0.38`) | `8000` | FastAPI + LangGraph; `network_mode: host` required |
| Inference Service | Jetson Orin Nano (`192.168.0.122`) | `8001` | FastAPI + InsightFace |
| PostgreSQL (pgvector) | R5 workstation | `5435` | Person embeddings + event log |
| MQTT (Mosquitto) | R5 workstation | `1883` | Camera events, future alerting |

## Repository Layout

```
PI/
├── command-module/      # FastAPI app — camera registry, LangGraph brain, person mgmt
│   ├── src/
│   │   ├── api/         # REST routes: cameras, persons, events, recordings, webhooks
│   │   ├── orchestration/ # LangGraph workflow nodes and state
│   │   ├── services/    # camera registry, inference client, webhook dispatcher
│   │   ├── db/          # SQLAlchemy models and database helpers
│   │   └── storage/     # local / S3 storage backend abstraction
│   └── frontend/        # React dashboard (in development)
├── inference-service/   # FastAPI app — InsightFace wrapper for Jetson
├── camera/              # ESP32-S3-EYE firmware (ESP-IDF / PlatformIO)
├── mosquitto/           # Mosquitto config
├── docs/
├── docker-compose.yml   # Manages db, mqtt, command-module on R5
├── init-db.sql          # pgvector schema bootstrap
└── .env                 # Secrets (not committed)
```

## Prerequisites

- R5 workstation running Docker and Docker Compose
- Jetson Orin Nano 8GB on the same local network
- One or more ESP32-S3-EYE boards
- PlatformIO (for firmware builds)

## Quick Start

### 1. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

### 2. Start the Command Tier

```bash
docker compose up -d
```

This starts `peekaboo-db` (PostgreSQL + pgvector on port 5435), `peekaboo-mqtt` (Mosquitto on port 1883), and `peekaboo-command` (Command Module on port 8000).

### 3. Start the Inference Service (on Jetson)

```bash
# On the Jetson
docker build -f Dockerfile.jetson -t peekaboo-inference .
docker run --runtime nvidia --network host peekaboo-inference
```

### 4. Flash ESP32-S3-EYE firmware

```bash
cd camera
./build-esp32s3eye.sh
./upload-esp32s3eye.sh /dev/ttyACM0
```

See [camera/README.md](camera/README.md) for board-specific flashing details.

## API Overview

### Command Module (`http://192.168.0.38:8000`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/cameras/register` | Camera self-registration on boot |
| `POST` | `/api/cameras/{id}/heartbeat` | Periodic keepalive |
| `POST` | `/api/cameras/{id}/motion` | Motion event (no face) |
| `POST` | `/api/cameras/report` | Face-identified event from Jetson |
| `GET` | `api/persons` | List enrolled persons |
| `POST` | `/api/persons` | Enroll a new person |
| `GET` | `/api/recordings` | List recordings |
| `GET` | `/health` | Service + inference node health |
| `WS` | `/ws/dashboard` | Real-time event stream |

### Inference Service (`http://192.168.0.122:8001`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/identify` | Face crop → identity + action decision |
| `POST` | `/sync` | Receive updated person embeddings from Command Module |
| `GET` | `/health` | Model load status |

## Development

### Command Module (local, without Docker)

```bash
cd command-module
pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://pfig:pfig_password@localhost:5435/peekaboo \
  uvicorn src.main:app --reload --port 8000
```

### Tests

```bash
cd command-module
pytest tests/
```
