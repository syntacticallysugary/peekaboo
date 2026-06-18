---
name: Peak-a-Boo
description: Secure ESP32-CAM to Python Hub streaming architecture
authors: James Huschle
version: 1.0
---

# Project "Peak-a-Boo" System Design

## 1. Project Overview
Project "Peak-a-Boo" is a private, secure video surveillance system. The architecture uses **ESP32-CAM** nodes as "Pushers" and a central **Linux-based Python service** as a "Hub." 

### Key Security Principle
**The Blind Hub Pattern:** The cameras are isolated on a guest network and have zero knowledge of how many clients are watching the stream. The Python Hub acts as a proxy, consuming a single stream from each camera and "fanning out" the frames to multiple web consumers.

---

## 2. Technical Stack
- **Hardware:** ESP32-CAM (AI-Thinker)
- **Embedded Language:** C++ (Arduino framework via PlatformIO)
- **Backend:** Python 3.10+ (FastAPI) managed via Conda
- **Networking:** HTTPS/WSS (TLS/SSL) for camera-to-hub security
- **Concurrency:** Python `asyncio` for non-blocking distribution

---

## 3. Iteration 1: MVP Definition (Current Task)
The goal is to prove the "Critical Path" from sensor to screen.

### ESP32-CAM (The Pusher)
- Capture JPEG frames every 200ms using PSRAM.
- Perform a secure `HTTP POST` to the Hub.
- **Headers:** `X-Camera-ID: cam_01` and `Authorization: Bearer <PSK>`.

### Python Hub (The Buffer)
- FastAPI endpoint `/api/upload/{cam_id}`.
- Validate PSK and store the binary frame in an in-memory `dict`.
- No disk I/O; frames must reside in RAM only.

### The Watcher (The Streamer)
- FastAPI `StreamingResponse` endpoint `/api/stream/{cam_id}`.
- Serves an MJPEG stream (`multipart/x-mixed-replace`) to browser clients.

---

## 4. Future User Stories (Next Phases)
- **API Interface:** Implement a management API to list active camera heartbeats and remotely toggle resolution settings.
- **Unified UI:** Build a web dashboard that dynamically discovers active camera IDs and renders them in a grid.
- **Multi-Consumer Scaling:** Optimize the broadcast loop to handle 10+ concurrent watchers per stream.
- **Camera Registry:** Allow new cameras to "handshake" and register their unique identifiers automatically.

---

## 5. Coding Constraints
- **PlatformIO Only:** Do not generate `.ino` files. Use `platformio.ini` for configuration.
- **Memory Safety:** In C++, always release the camera buffer using `esp_camera_fb_return()`.
- **Environment:** Use `conda` compatible Python libraries (e.g., `opencv-python` via conda-forge).
- **Security:** Reject any request that does not use TLS/SSL.