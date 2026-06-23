# Peekaboo Intellegence — Implementation Roadmap

This document outlines the phased implementation plan for the Peekaboo Intellegence system, mapping the requirements and design into actionable development steps.

---

## Phase 1: Environment & Infrastructure (Foundation)

Set up the core development environment and shared services that all tiers will rely on.

1.  **Project Structure Setup**:
    *   Initialize the monorepo structure as defined (already partially done).
    *   Create `docker-compose.yml` for local development (Command Module, DB, MQTT).
2.  **Database Layer**:
    *   Set up PostgreSQL with the `pgvector` extension.
    *   Apply the schema from `design.md`.
    *   **Validation**: Verify extension and tables exist via `psql`.
3.  **Shared Configuration**:
    *   Define a centralized `.env.example` template.

## Phase 2: Inference Tier Development (Jetson Orin Nano)

Develop the stateless REST API for face detection and recognition.

1.  **Model Preparation**:
    *   Select and export YOLOv8-face and ArcFace/AdaFace to TensorRT engines.
2.  **Inference Service (FastAPI)**:
    *   Implement `/detect`, `/recognize`, and `/health` endpoints.
    *   **Unit Testing**: Test vector similarity logic and image decoding in isolation.
3.  **Containerization & Deployment**:
    *   Create `Dockerfile.jetson`.
    *   Deploy to physical hardware (Jetson Nano).
    *   **Validation**: Verify `/health` endpoint and run a sample `/detect` with a static image.
    *   **Performance Benchmarking**: Verify ≥ 10 FPS throughput.

## Phase 3: Command Tier Core & Storage

Build the backbone of the Command Module.

1.  **Storage Abstraction**:
    *   Implement `StorageBackend` (Local/S3).
    *   **Unit Testing**: Verify `save_clip`, `get_clip_url`, and `delete_clip` with mocks.
2.  **Camera Registry Service**:
    *   Implement background monitoring and heartbeat logic.
    *   **Integration Testing**: Verify camera registration and disconnect detection (30s timeout) via DB state checks.
3.  **Person Management API**:
    *   Build CRUD endpoints and enrollment flow.
    *   **Integration Testing**: Verify image upload → inference call → `pgvector` storage chain.

## Phase 4: Orchestration Layer (LangGraph)

Implement the "Brain" of the system using LangGraph.

1.  **Workflow & Routing**:
    *   Implement nodes and conditional routers.
    *   **Unit Testing**: Verify each node's state mutations using mock `SystemState`.
    *   **Scenario Testing**: Execute the graph with mock triggers (Known, Unknown, No-Face) and verify the final `classification` and `recording_path`.
2.  **Event Bus & Webhooks**:
    *   Integrate event queue and dispatcher.
    *   **Validation**: Verify webhook delivery on detection events.

## Phase 5: Camera Tier (ESP32 Nodes)

Firmware development for the "Eyes" of the system.

1.  **Common Camera Core**:
    *   Implement WiFi, MJPEG, and motion detection.
    *   **Unit Testing**: Verify motion detection algorithm with sample frame buffers.
2.  **HIL Testing**:
    *   **Registration**: Verify node POSTs to `/api/cameras/register` on boot.
    *   **Triggering**: Verify node sends motion trigger and face crop on actual movement.

## Phase 6: Web Dashboard (React)

Create the user interface for monitoring and management.

1.  **Implementation**:
    *   Build grid view, event feed, and management views.
2.  **Validation**:
    *   **Component Testing**: Test UI components with mock API data.
    *   **Real-time Testing**: Verify dashboard updates instantly when a mock detection event is published to WebSockets.

## Phase 7: System Integration & E2E Validation

Full-system verification.

1.  **End-to-End (E2E) Scenarios**:
    *   Run all E2E scenarios defined in `testing.md`.
    *   Verify latency (Motion → Recording start) is ≤ 2 seconds.
2.  **Stress Testing**:
    *   Simulate 4+ cameras triggering simultaneously.
    *   Verify system stability under sustained motion.

---

## Mapping Requirements to Phases

| Requirement | Description | Primary Phase |
|---|---|---|
| Req 1 | Privacy/Local Processing | Phase 2, 3 |
| Req 2 | Multi-Camera Support | Phase 5, 3 |
| Req 3 | Motion-Triggered Inference | Phase 5, 4 |
| Req 4 | Known Person Suppression | Phase 4 |
| Req 5 | Recording Unknowns | Phase 4, 3 |
| Req 6 | Person Management UI | Phase 3, 6 |
| Req 7 | AWS Portability | Phase 3, 8 |
| Req 8 | Real-time Dashboard | Phase 6 |
| Req 9 | Event Queue/Webhooks | Phase 4 |
