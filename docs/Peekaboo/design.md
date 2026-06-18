# Peekaboo Intellegence — Distributed Architecture Design

## Overview

This document describes the architecture for the distributed, ESP32-camera-based Peekaboo Intellegence system. The design replaces the original single-webcam, all-on-one-PC approach with a three-tier distributed architecture:

1. **Camera Tier** — ESP32-S3-EYE and ESP32-CAM+C6 nodes at the edge
2. **Inference Tier** — Jetson Orin Nano 8GB for GPU-accelerated face detection and recognition
3. **Command Tier** — Orchestration, web interface, database, and storage (R5 workstation initially; AWS-portable)

The Inference Node runs only a stateless REST API — no web UI, no database, no orchestration. The Command Module owns all of that.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Camera Tier                          │
│                                                          │
│  ┌─────────────┐   ┌─────────────────────────────────┐  │
│  │ Eye_Node(s) │   │        Cam_Node(s)               │  │
│  │ ESP32-S3-EYE│   │  ESP32-CAM + ESP32-C6-DevKitC-1 │  │
│  │  (standalone│   │  (C6 handles WiFi + control)     │  │
│  │   via WiFi) │   └─────────────────────────────────┘  │
│  └─────────────┘                                         │
│    │         │                                           │
│    │ motion  │ face crop (on-device detected)            │
│    │ only    │ POST /identify directly to Jetson         │
└────┼─────────┼───────────────────────────────────────────┘
     │         │
     │         ▼
     │  ┌──────────────────────────────────────────────────┐
     │  │                   Inference Tier                 │
     │  │         Jetson Orin Nano 8GB                     │
     │  │  ┌──────────────────────────────────────────┐   │
     │  │  │  Inference Service (REST API)             │   │
     │  │  │  • /identify  — detect + recognize (main)│   │
     │  │  │  • /detect    — face detection only       │   │
     │  │  │  • /recognize — recognition only          │   │
     │  │  │  • /sync      — receives known persons    │   │
     │  │  │    from Command Module                    │   │
     │  │  │  Local known-persons cache (synced from   │   │
     │  │  │  Command Module; no DB of its own)        │   │
     │  │  └──────────────────────────────────────────┘   │
     │  │    │ returns action (record/cooldown) to ESP32   │
     │  │    │ POSTs /api/cameras/report to Command Module │
     │  │    │ when unknown/unallowed person detected      │
     │  └────┼─────────────────────────────────────────────┘
     │       │
     ▼       ▼
┌──────────────────────────────────────────────────────────┐
│                   Command Tier (R5 → AWS-ready)          │
│                                                          │
│  ┌─────────────────────────────────────────────────┐     │
│  │  LangGraph Orchestration (Python)               │     │
│  │  • Camera node registry & health monitor        │     │
│  │  • Motion event router (per-camera queues)      │     │
│  │  • Inference request dispatcher                 │     │
│  │  • Recording trigger logic                      │     │
│  │  • Event queue publisher                        │     │
│  └─────────────────────────────────────────────────┘     │
│         │                                                │
│         ├──────────────────────────────────────────────┐ │
│         │                                              │ │
│  ┌──────▼──────────┐   ┌────────────────────────────┐ │ │
│  │  PostgreSQL +   │   │  FastAPI Backend +          │ │ │
│  │  pgvector       │   │  WebSocket Server           │ │ │
│  │  (embeddings,   │   │  (REST + WS for dashboard)  │ │ │
│  │   events, clips)│   └────────────────────────────┘ │ │
│  └─────────────────┘           │                      │ │
│                         ┌──────▼──────┐               │ │
│                         │  React      │               │ │
│                         │  Dashboard  │               │ │
│                         └─────────────┘               │ │
│                                                       │ │
│  ┌────────────────────────────────────────────────┐  │ │
│  │  Recording Storage  (local disk / S3-compatible│  │ │
│  │  object store for AWS migration)               │  │ │
│  └────────────────────────────────────────────────┘  │ │
└──────────────────────────────────────────────────────────┘
```

---

## Camera Tier

### ESP32-S3-EYE (Eye_Node)

Deployed independently. No companion controller required. Runs ESP-IDF (not Arduino).

- Performs **on-device face detection** using ESP-WHO HumanFaceDetect (two-stage MobileNet pipeline on ESP-DL)
- Performs on-device motion detection using frame differencing
- **Two event paths depending on what was detected:**
  - **Motion only (no face):** POST `{COMMAND_MODULE_URL}/api/cameras/{id}/motion` with `{"camera_id": "..."}`
  - **Face detected:** POST `{JETSON_URL}/identify` with `{"camera_id": "...", "frame": "<base64 face crop>"}` directly to Jetson; handles `record`/`cooldown` response locally
- Registers on boot: POST `/api/cameras/register` to Command Module
- Polls config every 300s: GET `/api/cameras/{id}/config` from Command Module
- Configuration (WiFi credentials, URLs, thresholds) provisioned at build time via cmake `file(WRITE)` from `.env`

### ESP32-CAM + ESP32-C6-DevKitC-1 V1.2 (Cam_Node)

Operates as a unit. The ESP32-CAM handles image capture; the C6 handles WiFi connectivity and acts as the network-facing controller.

- C6 receives JPEG frames from the CAM over UART/SPI
- C6 exposes the same HTTP MJPEG stream and MQTT trigger interface as an Eye_Node
- C6 runs motion detection logic; ESP32-CAM is dedicated to image capture
- From the Command Module's perspective, a Cam_Node is indistinguishable from an Eye_Node at the API boundary

### Camera Node Protocol

**Registration (on boot):**
```
POST /api/cameras/register
Body: { "camera_id": "eye-01", "type": "eye", "capabilities": "motion,face_detect" }
```

**Motion-only trigger (no face detected on device):**
```
POST /api/cameras/{camera_id}/motion
Body: { "camera_id": "eye-01" }
```

**Face detected on-device — sent directly to Jetson, NOT Command Module:**
```
POST {JETSON_URL}/identify
Body: { "camera_id": "eye-01", "frame": "<base64 JPEG face crop>" }
Response: { "action": "record" | "cooldown", "duration_s": 600 }
```

**Config poll (every 300s):**
```
GET /api/cameras/{camera_id}/config
Response: { "cooldown_s": 600, "motion_threshold": 20, "jpeg_quality": 12 }
```

---

## Inference Tier — Jetson Orin Nano 8GB

The Inference Node is intentionally simple: a stateless REST service. It holds no persistent state, no known-person database, and no web UI.

### Inference Service API

**Primary endpoint (Edge-First path — called by ESP32 directly):**
```
POST /identify
Body: { "camera_id": "eye-01", "frame": "<base64 JPEG face crop>" }
Response: { "action": "record" | "cooldown", "duration_s": 600 }
```
Combines detection + recognition in one GPU call against the local known-persons cache.
If unknown/unallowed, the Jetson itself POSTs `/api/cameras/report` to the Command Module.

**Supporting endpoints (called by Command Module for workflow processing):**
```
POST /detect
Body: { "frame": "<base64 JPEG>" }
Response: { "faces": [{ "bbox": [...], "confidence": 0.97, "embedding": [...512] }], "inference_ms": 34 }

POST /recognize
Body: { "embedding": [...512 floats...], "candidates": [{ "person_id": "uuid", "embedding": [...] }] }
Response: { "match": { "person_id": "uuid", "similarity": 0.91 } | null, "inference_ms": 8 }

POST /sync
Body: { "candidates": [{ "person_id": "uuid", "embedding": [...] }] }
Response: { "status": "synced", "count": N }
— Called by Command Module when known-persons DB changes; updates Jetson's local cache

GET /health
Response: { "status": "ok", "model_pack": "buffalo_l", "gpu_available": true, "queue_depth": 0 }
```

### Inference Stack

- **Runtime**: TensorRT (via `tensorrt` Python bindings) or ONNX Runtime with CUDA EP
- **Face detection model**: YOLOv8-face or RetinaFace, exported to TRT engine at setup time
- **Embedding model**: ArcFace or AdaFace (ResNet-50), exported to TRT engine
- **Server**: FastAPI + uvicorn, single process, async request handling
- **Concurrency**: GPU inference is serialized; async I/O handles concurrent HTTP requests without blocking

The Command Module is responsible for passing known-person embeddings as `candidates` in the `/recognize` call. The Inference Node never reads from the database directly.

---

## Command Tier

The Command Module is the brain of the system. It owns all orchestration, persistence, and user interaction. It is designed to run in Docker so it can be lifted from R5 to AWS without code changes.

### LangGraph Orchestration

The orchestration layer uses LangGraph to route events through a per-camera processing pipeline.

#### System State

```python
class SystemState(TypedDict):
    # Camera registry
    cameras: Dict[str, CameraNodeInfo]          # camera_id → status, type, stream_url, last_seen

    # Per-camera processing queues
    pending_triggers: List[TriggerEvent]         # motion triggers awaiting processing
    active_recordings: Dict[str, RecordingSession]

    # Inference pipeline
    inference_node_url: str
    inference_health: Dict[str, Any]

    # Recognition
    known_persons: List[KnownPersonRecord]       # loaded at startup, refreshed on DB change
    recognition_results: List[RecognitionResult]

    # Event queue (for extensibility)
    event_queue: List[DetectionEvent]

    # Workflow routing
    current_trigger: Optional[TriggerEvent]
    current_workflow_path: str
```

#### Workflow Graph

```python
def create_guard_workflow() -> CompiledGraph:
    workflow = StateGraph(SystemState)

    workflow.add_node("receive_trigger",    receive_trigger_node)
    workflow.add_node("fetch_frame",        fetch_frame_node)
    workflow.add_node("run_detection",      run_detection_node)     # → Inference Node /detect
    workflow.add_node("run_recognition",    run_recognition_node)   # → Inference Node /recognize
    workflow.add_node("start_recording",    start_recording_node)
    workflow.add_node("suppress_recording", suppress_recording_node)
    workflow.add_node("publish_event",      publish_event_node)
    workflow.add_node("notify_dashboard",   notify_dashboard_node)

    workflow.set_entry_point("receive_trigger")
    workflow.add_edge("receive_trigger", "fetch_frame")
    workflow.add_edge("fetch_frame", "run_detection")

    workflow.add_conditional_edges(
        "run_detection",
        face_detection_router,
        {
            "face_found":  "run_recognition",
            "no_face":     "start_recording",   # motion, no face → record
        }
    )

    workflow.add_conditional_edges(
        "run_recognition",
        recognition_router,
        {
            "known_person":   "suppress_recording",
            "unknown_person": "start_recording",
            "unallowed":      "start_recording",
        }
    )

    workflow.add_edge("start_recording",    "publish_event")
    workflow.add_edge("suppress_recording", "publish_event")
    workflow.add_edge("publish_event",      "notify_dashboard")
    workflow.add_edge("notify_dashboard",   END)

    return workflow.compile()
```

#### Workflow Scenarios

| Scenario | Path | Action |
|---|---|---|
| Motion, no face | receive → fetch → detect → **start_recording** → publish → notify | Record clip |
| Motion, unknown face | receive → fetch → detect → recognize → **start_recording** → publish → notify | Record clip |
| Motion, known face | receive → fetch → detect → recognize → **suppress_recording** → publish → notify | Suppress, 10-min cooldown |
| Motion, unallowed face | receive → fetch → detect → recognize → **start_recording** → publish → notify | Record + priority alert |

### Camera Registry Service

A background async task (not part of the LangGraph workflow) manages camera node lifecycle:

- Maintains a registry of known Camera_Nodes with last-heartbeat timestamp
- Marks nodes as `disconnected` if no heartbeat or trigger received within 30 seconds
- Pushes camera status changes to the dashboard via WebSocket
- On startup, loads previously registered cameras from the database and waits for them to reconnect

### FastAPI Backend

The Command Module exposes REST and WebSocket endpoints consumed by the React dashboard and Camera_Nodes.

```
# Camera node endpoints
POST   /api/cameras/register
POST   /api/cameras/{camera_id}/trigger
GET    /api/cameras                         # list all with status
DELETE /api/cameras/{camera_id}

# Known persons management
GET    /api/persons
POST   /api/persons                         # upload images, generate embeddings via Inference Node
PUT    /api/persons/{person_id}
DELETE /api/persons/{person_id}

# Recordings
GET    /api/recordings                      # paginated, filterable by camera/date/type
GET    /api/recordings/{recording_id}/clip

# Events
GET    /api/events                          # recent detection events
POST   /api/webhooks                        # register a webhook endpoint

# WebSocket
WS     /ws/dashboard                        # real-time: camera status, detection alerts, recording started
```

### Recording Storage

Recording_Sessions are stored as MP4 clips on the Command Module's local disk, organized as:

```
recordings/
  {YYYY-MM-DD}/
    {camera_id}/
      {timestamp}_{classification}.mp4
```

For AWS migration, the storage backend is abstracted behind a `StorageBackend` interface with two implementations: `LocalDiskBackend` (default) and `S3Backend`. Switching is done via an environment variable (`STORAGE_BACKEND=s3`).

### Database Schema

```sql
-- Camera node registry
CREATE TABLE cameras (
    camera_id    TEXT PRIMARY KEY,
    type         TEXT NOT NULL,        -- 'eye' | 'cam'
    stream_url   TEXT,
    last_seen    TIMESTAMPTZ,
    status       TEXT DEFAULT 'disconnected'
);

-- Known persons
CREATE TABLE persons (
    person_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    is_blocked  BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Face embeddings (one person may have multiple reference images)
CREATE TABLE face_embeddings (
    embedding_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id     UUID REFERENCES persons(person_id) ON DELETE CASCADE,
    embedding     vector(512),        -- pgvector
    source_image  TEXT               -- original filename for reference
);

-- Detection events
CREATE TABLE detection_events (
    event_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id     TEXT REFERENCES cameras(camera_id),
    detected_at   TIMESTAMPTZ NOT NULL,
    classification TEXT NOT NULL,    -- 'known' | 'unknown' | 'unallowed' | 'no_face'
    person_id     UUID REFERENCES persons(person_id),
    confidence    FLOAT,
    recording_path TEXT              -- NULL if suppressed
);
```

### React Dashboard

The dashboard is a single-page app served by the FastAPI backend (static files or a separate Nginx container).

Key views:
- **Live Cameras**: Grid of camera status tiles; click to open MJPEG stream in modal
- **Recent Events**: Feed of detection events with thumbnails/clips; filterable by camera and classification
- **Known Persons**: List with add/edit/block/remove actions; image upload for enrollment
- **System Health**: Inference Node GPU utilization, inference latency, queue depth; per-camera heartbeat status
- **Settings**: Motion threshold per camera, recording retention policy, webhook configuration

---

## Data Flow: End-to-End Detection Event

### Path A — Motion only (no face detected on ESP32)
```
1. ESP32 detects motion via frame differencing
        ↓
2. ESP32 POSTs to Command Module POST /api/cameras/{id}/motion
        ↓
3. Command Module runs LangGraph workflow:
   fetch_frame_node → run_detection_node (/detect) → run_recognition_node (/recognize)
        ↓
4. start_recording or suppress_recording → publish_event → notify_dashboard
```

### Path B — Face detected on-device (ESP32 edge-first path, hot path)
```
1. ESP32 detects face on-device using ESP-WHO HumanFaceDetect
        ↓
2. ESP32 POSTs face crop directly to Jetson POST /identify
   ← Jetson returns { "action": "record" | "cooldown" }
        ↓
3a. action=cooldown: ESP32 suppresses motion events locally for cooldown_s seconds
        ↓
3b. action=record:   Jetson POSTs to Command Module POST /api/cameras/report
                     with classification + frame
        ↓
4. Command Module runs LangGraph workflow → record + notify dashboard
```

### Known-persons sync
```
Command Module DB change (enroll/remove person)
        ↓
Command Module POSTs to Jetson POST /sync with updated embeddings
Jetson updates local cache — used by /identify on the hot path
```

---

## Deployment

### Initial Deployment (R5 Workstation)

```
docker-compose up
  services:
    command-module:        # FastAPI + LangGraph + React static
    postgres:              # PostgreSQL + pgvector
    mqtt-broker:           # Mosquitto (for Camera_Node triggers)
    recording-storage:     # local volume mount

Inference Node (Jetson):
    systemd service or Docker container running inference_service.py
    accessible at http://jetson-local-ip:8001
```

Environment variables (`.env`):
```
INFERENCE_NODE_URL=http://192.168.1.10:8001
DATABASE_URL=postgresql://pfig:password@postgres:5432/pfig
STORAGE_BACKEND=local
RECORDINGS_PATH=/data/recordings
MQTT_BROKER=mqtt://mqtt-broker:1883
```

### AWS Migration Path

When moving the Command Module to AWS:

1. Change `STORAGE_BACKEND=s3` and set `S3_BUCKET`
2. Point `DATABASE_URL` to RDS PostgreSQL with pgvector extension
3. Update `INFERENCE_NODE_URL` — Jetson remains on-premises, accessible via a site-to-site VPN or tailscale tunnel
4. Camera_Nodes update their `COMMAND_MODULE_URL` to the public AWS endpoint (provisioned at flash time via OTA config update)
5. No application code changes required

---

## Error Handling and Resilience

- **Camera_Node offline**: Camera registry marks node as `disconnected`; orchestrator skips triggers from that node; dashboard shows alert; system continues with remaining nodes
- **Inference_Node offline**: Command Module queues incoming triggers; retries with exponential backoff; if Inference Node is unreachable for >60s, falls back to "record all motion" mode (no face recognition) and alerts dashboard
- **Recording storage full**: Recording agent checks available disk before writing; if below threshold, deletes oldest clips beyond retention window; alerts dashboard if space is still insufficient
- **Database unavailable**: Command Module buffers recent events in memory; retries DB writes; Inference Node is stateless and unaffected
- **LangGraph workflow error**: Each node wraps its logic in try/except; on failure the node emits an error event and routes to `notify_dashboard`; workflow does not crash

---

## Correctness Properties

### Property 1: Inference Node Statelessness
*For any* inference request, the Inference Node SHALL return identical results given identical inputs, regardless of prior requests. It SHALL NOT maintain session state between requests.
**Validates: Requirement 7.1**

### Property 2: Camera Node Isolation
*For any* Camera_Node failure or disconnection, the system SHALL continue processing triggers from all other Camera_Nodes without interruption.
**Validates: Requirement 2.4**

### Property 3: Per-Camera Routing Consistency
*For any* simultaneous Motion_Events from multiple Camera_Nodes, each event SHALL be processed through an independent workflow invocation. Events from different cameras SHALL NOT interfere with each other's recording decisions.
**Validates: Requirements 3.4, 4.4**

### Property 4: Command Module Portability
*For any* deployment (R5 or AWS), the system SHALL behave identically given the same environment variables, with no code changes required.
**Validates: Requirement 7.4, 7.5**

### Property 5: Known Person Suppression Cooldown
*For any* Known_Person detection, the system SHALL suppress recording for that camera for exactly 10 minutes, and SHALL resume recording for unknown persons on that same camera immediately after the cooldown expires.
**Validates: Requirement 4.2**

### Property 6: Recording Classification Completeness
*For any* detection event that results in a Recording_Session, the stored clip SHALL include camera_id, classification, timestamp, and (if recognized) person_id in the database record.
**Validates: Requirement 5.5**

---

## Testing Strategy

### Unit Tests
- LangGraph routing functions (each conditional router) with mocked state
- Camera registry service (registration, heartbeat, disconnect detection)
- Storage backend implementations (LocalDisk and S3 interface)
- Known-person enrollment pipeline (image → embedding → DB write)

### Integration Tests
- End-to-end trigger flow: mock Camera_Node POST → mock Inference Node → verify recording created in DB
- Multi-camera simultaneous trigger: verify independent processing, no crosstalk
- Known person suppression: verify cooldown is respected and recording suppressed
- Inference Node offline fallback: verify record-all mode activates

### Hardware-in-Loop Tests (once ESP32 firmware is stable)
- Eye_Node registers, streams, and sends motion trigger on real movement
- Cam_Node operates correctly as a unit; C6 correctly relays frames from CAM
- Camera_Node disconnect is detected within 30s on the dashboard

### Performance Tests
- Inference Node: sustained throughput ≥ 10 FPS at full resolution
- End-to-end latency: motion trigger → recording start ≤ 2 seconds
- Multi-camera load: 4 simultaneous motion events without queue backup
