# Functional Requirements

**Current Status:** Fully implemented and deployed as of 2026-06-23.

This document describes the actual system requirements as implemented. Original pre-implementation requirements are in `deprecated/requirements.md`.

---

## System Requirements

### Hardware
- **Camera nodes:** 2+ ESP32-S3 boards (ESP32-S3-EYE or XIAO ESP32-S3 Sense) with integrated cameras
- **Inference node:** Jetson Orin Nano 8GB with NVIDIA GPU
- **Command node:** x86 workstation (R5 or equivalent, Linux/Docker-capable)
- **Network:** Local LAN (WiFi for cameras, wired optional for Jetson/R5)

### Software
- **Camera firmware:** ESP-IDF + PlatformIO
- **Inference service:** Python + FastAPI + PyTorch (via ONNX Runtime)
- **Command module:** Python + FastAPI + PostgreSQL + Firestore
- **Dashboard:** React + Vue TypeScript (in-progress)

---

## Functional Requirements

### FR-1: Camera Node
- **FR-1.1** Capture JPEG frames from integrated camera at configurable intervals
- **FR-1.2** Detect motion via compressed frame size (JPEG delta)
- **FR-1.3** Stream frames to Jetson inference service
- **FR-1.4** Connect to WiFi network (WPA3-SAE support required)
- **FR-1.5** Connect to MQTT broker for receiving control commands
- **FR-1.6** Self-update firmware when new version available on command module
- **FR-1.7** Register with command module on boot
- **FR-1.8** Send heartbeat to command module every 30 seconds

**Status:** ✅ Fully implemented for ESP32-S3-EYE and XIAO ESP32-S3 Sense

### FR-2: Inference Service
- **FR-2.1** Receive JPEG frames from cameras via HTTP POST
- **FR-2.2** Run person detection on frames (YOLOv8n, ~8ms/frame)
- **FR-2.3** Run face detection on person bounding boxes
- **FR-2.4** Run face recognition against known-person embeddings (InsightFace)
- **FR-2.5** Manage per-camera sessions (buffer frames, track detections)
- **FR-2.6** Determine "known person" when similarity > 0.55 (threshold)
- **FR-2.7** Send alerts to command module for unknown/unallowed persons
- **FR-2.8** Respect arm/disarm state (discard sessions when disarmed)
- **FR-2.9** Provide live MJPEG stream per camera
- **FR-2.10** Enforce 15-minute global cooldown on known-person events (all cameras suppressed)
- **FR-2.11** Enforce 0.40 confidence threshold to keep session alive (person sustain)
- **FR-2.12** Auto-end sessions after 12 consecutive frames of no person

**Status:** ✅ Fully implemented

### FR-3: Command Module
- **FR-3.1** Maintain registry of active cameras
- **FR-3.2** Receive heartbeats from cameras (proxied via Jetson)
- **FR-3.3** Store person embeddings in PostgreSQL + pgvector
- **FR-3.4** Enroll new persons from face crops captured during inference
- **FR-3.5** Sync known-person embeddings to Jetson on demand or on DB changes
- **FR-3.6** Route alerts to webhooks (for external integrations)
- **FR-3.7** Manage system arm/disarm state
- **FR-3.8** Support scheduled arm/disarm (enable at configured times)
- **FR-3.9** Accept firmware uploads per channel (s3eye, xiao)
- **FR-3.10** Serve firmware version checks and binary downloads to cameras
- **FR-3.11** Provide WebSocket event stream for dashboard (real-time updates)
- **FR-3.12** Store recordings with metadata (camera_id, person, classification)

**Status:** ✅ Fully implemented

### FR-4: Dashboard
- **FR-4.1** Display live camera views (MJPEG streams)
- **FR-4.2** Show system arm/disarm status with toggle control
- **FR-4.3** Display event log (person detections, classifications)
- **FR-4.4** Show camera registry with online/offline status
- **FR-4.5** Manage person enrollment (add/remove persons)
- **FR-4.6** Configure system settings (WiFi for cameras, Jetson URL, etc.)

**Status:** ⚠️ Partially implemented (arm/disarm controls + camera list working; event log + person management bare-bones)

---

## Non-Functional Requirements

### NFR-1: Performance
- **NFR-1.1** Person detection latency < 10ms per frame
- **NFR-1.2** Face recognition latency < 100ms per detection
- **NFR-1.3** Session creation latency < 50ms
- **NFR-1.4** Alert dispatch latency < 1 second
- **NFR-1.5** Live stream latency < 2 seconds

**Status:** ✅ All met empirically

### NFR-2: Reliability
- **NFR-2.1** Camera node uptime > 99% (WiFi/MQTT stable on LAN)
- **NFR-2.2** Jetson inference service uptime > 99.5%
- **NFR-2.3** Graceful handling of camera loss (continue recording, notify admin)
- **NFR-2.4** Graceful handling of Jetson loss (cameras buffer, resume on reconnect)

**Status:** ✅ Stable for weeks between manual power cycles

### NFR-3: Security
- **NFR-3.1** WiFi credentials not hardcoded in source (provisioned from .env)
- **NFR-3.2** MQTT commands require TLS + HMAC nonce (replay-resistant)
- **NFR-3.3** No raw video leaves the local network (Jetson inference only)
- **NFR-3.4** Person embeddings stored locally (no cloud sync)

**Status:** ✅ Fully implemented

### NFR-4: Scalability
- **NFR-4.1** Single Jetson can handle 3+ cameras with < 30% GPU utilization
- **NFR-4.2** Support up to 100 known persons (embedding lookups < 10ms)
- **NFR-4.3** Recordings stored locally (expandable to S3-compatible storage)

**Status:** ✅ Tested with 2 cameras; architecture supports 3+

### NFR-5: Maintainability
- **NFR-5.1** Code is documented with architecture diagrams
- **NFR-5.2** Configuration is externalized (.env files)
- **NFR-5.3** All services run in Docker (reproducible across machines)

**Status:** ⚠️ Partially done (code documented; Docker working; CI/CD pipeline not yet implemented)

---

## Known Constraints

1. **Optical detection only** — no IR/low-light support (hardware gap)
2. **Single Jetson inference node** — no failover or horizontal scaling (yet)
3. **Local PostgreSQL only** — no cloud backup (manual or add to ops plan)
4. **MJPEG recordings** — no MP4 export (can be added)

---

## See Also

- `design.md` — Architecture & design decisions
- `implementation.md` — Current implementation status + known issues
- `../../README.md` — Project overview
