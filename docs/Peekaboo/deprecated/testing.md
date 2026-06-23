# Peekaboo Intellegence — Comprehensive Test Plan

This document defines the testing strategy for the Peekaboo Intellegence system, ensuring reliability, accuracy, and performance across the distributed architecture.

---

## 1. Testing Philosophy

We follow a **Test-Driven Development (TDD)** approach where possible. Every functional change must be accompanied by a corresponding test. 
*   **Surgical Validation**: Each phase of implementation includes a "Validation" step.
*   **Empirical Verification**: Bug fixes must start with a reproduction test case.
*   **Continuous Integration**: Tests should be automated and runnable in the development environment.

---

## 2. Environment Setup

To run the test suite locally on the Command Tier (R5), follow these steps:

1.  **Create a Virtual Environment**:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
2.  **Install Dependencies**:
    The system requires several libraries for async database access and testing:
    ```bash
    pip install sqlalchemy asyncpg greenlet pydantic-settings fastapi uvicorn httpx pgvector pytest pytest-asyncio
    ```
3.  **Database Configuration**:
    Ensure your `.env` file uses the `asyncpg` driver:
    `DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5435/peekaboo`

---

## 3. Running Tests

Tests should be run from the project root. Ensure the virtual environment is active.

### 3.1. Command Tier Tests
```bash
# Set PYTHONPATH to include the source directory
export PYTHONPATH=$PYTHONPATH:$(pwd)/command-module/src

# Run all tests
pytest command-module/tests

# Run a specific test file
pytest command-module/tests/unit/test_storage.py
```

---

## 4. Tier-Specific Testing

### 2.1. Command Tier (Python / FastAPI)
*   **Unit Tests (pytest)**:
    *   **Storage**: Test `LocalDiskBackend` and `S3Backend` using mocks for filesystem/boto3.
    *   **Orchestration**: Test LangGraph nodes in isolation. Mock the `SystemState` and verify output mutations.
    *   **Routers**: Verify `face_detection_router` and `recognition_router` with all permutations of state (error, no face, known, unknown, unallowed).
*   **Integration Tests (pytest-asyncio)**:
    *   **API**: Test REST endpoints using `httpx.AsyncClient`. Verify DB persistence and status codes.
    *   **Database**: Test `pgvector` operations (insert embedding, similarity search) against a test database.
    *   **Inference Client**: Mock the Inference Node response and verify the client correctly parses bboxes and embeddings.

### 2.2. Inference Tier (Python / Jetson)
*   **Unit Tests**:
    *   **Preprocessing**: Verify image decoding and resizing logic.
    *   **Vector Logic**: Test the similarity calculation in the `recognize` endpoint.
*   **Performance Tests**:
    *   **Throughput**: Measure FPS for sustained `/detect` calls. Target: ≥ 10 FPS.
    *   **Latency**: Measure end-to-end time from POST request to JSON response.

### 2.3. Camera Tier (ESP-IDF / Unity)
*   **Unit Tests**:
    *   **Motion Detection**: Feed static and dynamic frames to the algorithm and verify trigger logic.
    *   **Protocol**: Verify JSON payload generation for MQTT/HTTP triggers.
*   **Hardware-in-the-Loop (HIL)**:
    *   **Connectivity**: Verify auto-reconnect logic on WiFi/MQTT failure.
    *   **Registration**: Verify the node correctly registers with the Command Module on boot.

### 2.4. Dashboard (React / Vitest)
*   **Component Tests**: Verify individual UI components (Camera Tile, Event Feed) render correctly with mock data.
*   **State Tests**: Verify WebSocket message handlers correctly update the UI state.

---

## 3. Integration & E2E Scenarios

These tests simulate real-world flows and require all services (Command, DB, MQTT, Mock Inference) to be running.

| Scenario | Trigger | Expected Outcome |
|---|---|---|
| **Known Person Flow** | HTTP Trigger + Known Embedding | Suppression event logged; No recording created; Cooldown set. |
| **Unknown Person Flow** | HTTP Trigger + Unknown Embedding | "Unknown" event logged; Recording session started; WebSocket alert sent. |
| **Unallowed Person Flow** | HTTP Trigger + Blocked Embedding | "Unallowed" event logged; Priority alert sent; Recording started. |
| **No Face Flow** | HTTP Trigger + No Face | "No Face" event logged; Recording started. |
| **Inference Offline** | Trigger while Jetson unreachable | "Fallback" mode active; Recording started for all motion. |

---

## 4. Performance & Stress Testing

*   **Multi-Camera Load**: Trigger motion on 4 cameras simultaneously. Verify the Command Module processes all without dropping events or exceeding 2s latency.
*   **Database Scaling**: Insert 1,000+ known-person embeddings. Verify similarity search in `pgvector` remains < 50ms.
*   **Storage Retention**: Fill the storage to the threshold. Verify the cleanup agent correctly deletes the oldest clips.

---
## 5. Tooling

*   **Test Runner**: `pytest`
*   **Mocks**: `unittest.mock`, `pytest-mock`
*   **API Testing**: `httpx`
*   **HIL Simulation**: Python scripts to "act" as ESP32 nodes for testing the Command Module in isolation.

---

## Appendix A: Requirement Coverage Matrix

This matrix maps each of the 9 requirements to their corresponding test cases across the test pyramid.

| Req ID | User Story | Unit Tests | Integration Tests | E2E/Performance Tests | Status | Notes |
|---|---|---|---|---|---|---|
| Req 1 | Privacy/Local Processing | ✅ Verify no cloud API calls mocked | ✅ Verify pgvector storage verified against isolated DB | ✅ Verify offline operation simulated (no-internet E2E) | ✅ | AC1-3 only require backend verification; AC5 (offline) is an E2E scenario |
| Req 2 | Multi-Camera Support | ✅ Verify registration endpoint signature with ID assignment | ✅ Verify registration, heartbeat detection, disconnect timeout (30s) | ✅ Verify 4 cameras concurrent registration; Simulate disconnect and monitor 30s window | ⬜ | AC1-5 mapped; AC6-7 require camera involvement (HIL) |
| Req 3 | Motion-Triggered Inference | ✅ Verify motion-to-trigger JSON payload generation | ✅ Verify trigger latency measurement within 2s; Multiple concurrent triggers handling | ✅ Verify simultaneous 4-camera motion triggers end-to-end | ✅ | AC1-2 latency mapped in performance tests |
| Req 4 | Known Person Suppression | ✅ Verify embedding similarity search (1%, cosine threshold) | ✅ Verify cooldown logic (10-min duration) and logging | ✅ Verify full Known Person Flow E2E scenario | ⬜ | AC2 (10-min cooldown) is NOT TESTED; AC4 (2s SLA) latency NOT TESTED |
| Req 5 | Recording Unknowns | ✅ Verify Unknown/Unallowed/NoFace classification logic | ✅ Verify recording path generation in StorageBackend | ✅ Verify Unknown Person Flow E2E; Capture latency measurement (2s SLA) | ⬜ | AC4/5 (100% capture within 2s) NOT TESTED |
| Req 6 | Person Management UI | ✅ (N/A for UI) | ✅ Verify user CRUD API endpoints | ⬜ | ⬜ | AC1-3 (web UI, CRUD, load embeddings at startup) missing from Reactive |
| Req 7 | AWS Portability | ✅ Verify InferenceNode REST-only exposed; verify no web UI in Dockerfile | ✅ Verify Command Module Docker compose and DB/MQTT isolation | ✅ Verify environment variable re-config without code change for Command Module address | ✅ | AC5 (env var config) needs explicit integration-test case |
| Req 8 | Real-time Dashboard | ✅ (N/A for UI) | ✅ Verify WebSocket message handler simulation | ✅ Verify dashboard update latency; Verify InferenceNode health metrics display | ✅ | React component test + WebSocket test mapped |
| Req 9 | Event Queue/Webhooks | ✅ (N/A for inference tier) | ⬜ | ⬜ | ⬜ | AC2 (consumer contract) for LangGraph integration event queue NOT TESTED |

---

## Appendix B: Negative Testing Registry (DEFECT-003)

*   **Database Connection Failure**: Which triggers recording fallback mode?
    *   Unit: Mock `AsyncSession.close()` fail; Verify recording still initiated.
    *   E2E: Simulate DB process stop; Verify fallback mode and event queue continuity.
    *   Gap: No test exists for inference tier while Command tier DB fails.

*   **Malformed JSON from Camera**: What happens if an ESP32 sends invalid `{{`?
    *   Integration: Test `memory_parser` with `{"trigger":` (invalid) → Should raise `ServiceUnavailable`.
    *   E2E: Verify system doesn't crash; Recording graceful degradation.
    *   Gap: No test exists for malformed payload scenarios.

*   **Duplicate Camera Registration**: Duplicate UUIDs?
    *   Integration: Test POST `/cameras/register` twice; Ensure system raises `Conflict` status code or returns existing camera ID.
    *   Gap: No test exists for duplicate registration scenario.

*   **Embedding Dimension Mismatch**: GLOVE 768 vs ArcFace 128?
    *   Integration: Verify `SteerVectors` accepts 128-dim vectors; Test similarity search failure for 768-dim input.
    *   Gap: No test exists for dimension mismatch causing db query rejection.

*   **Storage Full / Cleanup Agent**: S3 quota exceeded?
    *   Unit: Mock `save_clip()` to fail with `OSError`; Verify `CleanupAgent` is goroutine triggered.
    *   Integration: Send deletion request; Verify files are deleted from `movie_db`.
    *   E2E: Simulate full disk during unknown flow; Verify oldest clips are removed before recording write failure.
    *   Gap: No test exists for storage boundary conditions.

*   **False Positive Rate (Model Confidence Boundary)**: 47% vs 73%?
    *   Gap: Model confidence boundary testing NOT TESTED.

