# Testing & Validation

**Current Status:** Manual testing comprehensive; automated testing broken (CI/CD planned).

---

## Manual Testing (Passing ✅)

### Camera Firmware (ESP32-S3)

#### WiFi & Network
- ✅ WiFi connects on boot (WPA3-SAE to home network)
- ✅ MQTT TLS connection succeeds with correct credentials
- ✅ Camera registers with command module on first boot
- ✅ Heartbeat POSTs every 30 seconds

**How tested:** Serial monitor, MQTT broker logs, command module dashboard

#### Frame Streaming
- ✅ Frames POST to Jetson `/session/frame` endpoint
- ✅ Frame encoding is valid base64 JPEG
- ✅ Motion detection works (JPEG delta threshold honored)
- ✅ Heartbeat ensures session alive for stationary subjects (1 frame/sec)

**How tested:** Jetson inference service logs, live stream in dashboard

#### OTA Firmware Updates
- ✅ Device polls `/api/firmware/{channel}/check` every 5 minutes
- ✅ Device downloads binary when newer version available
- ✅ Device self-updates partition and reboots
- ✅ New firmware boots correctly after OTA update

**How tested:** Manual firmware upload to command module, device reset/reboot cycle

#### Both Board Variants
- ✅ ESP32-S3-EYE firmware builds and flashes via PlatformIO
- ✅ XIAO ESP32-S3 Sense firmware builds, requires bootloader entry (BOOT+RST sequence)
- ✅ Both boards reach Jetson with pass-through inference task

**How tested:** Parallel flashing, serial monitoring, dashboard camera list

---

### Inference Service (Jetson)

#### Session Management
- ✅ Session created on first `/session/frame` POST from camera
- ✅ Frames buffered in session (up to 300 frame limit)
- ✅ Session auto-rotates after 60 seconds (concluded) or 300 seconds hard-max
- ✅ Session ends explicitly if person leaves (12 frames no detection)

**How tested:** Inference service logs, recording files on disk

#### Person Detection (YOLOv8n)
- ✅ Detects humans in frame at any orientation
- ✅ Returns bounding boxes + confidence scores
- ✅ Inference time < 10ms per frame (measured on Jetson)

**How tested:** Live testing with known persons walking past camera

#### Face Detection & Recognition (InsightFace)
- ✅ Detects faces within person bounding boxes
- ✅ Extracts embeddings (512D)
- ✅ Compares against known-person cache (pgvector similarity)
- ✅ Returns person_id when similarity > 0.55

**How tested:** Manual enrollment + live recognition testing

#### Person Sustain Threshold
- ✅ Session stays alive if consecutive person detections > 0.40 confidence
- ✅ Session ends after 12 consecutive frames < 0.40 confidence

**How tested:** Moving in/out of frame, checking session lifecycle

#### Known-Person Cooldown (15 minutes, global)
- ✅ First camera recognizes person → all cameras enter cooldown
- ✅ During cooldown, arrival events suppressed (dashboard notified only)
- ✅ Cooldown expires after 15 minutes; normal operation resumes

**How tested:** Multi-camera scenario, dashboard event log, time-based testing

#### Unknown-Person Alerts
- ✅ Alert fires after 5 seconds of unrecognized face
- ✅ Alert includes best_unknown_frame_b64 (for UI display)
- ✅ Alert still fires if no face ever detected in session (person backlit case)

**How tested:** Triggering with unknown persons, checking command module event log

#### Arm/Disarm Enforcement
- ✅ When disarmed, in-progress sessions discarded immediately
- ✅ Frames still received but no alerts/recordings generated
- ✅ Re-arming resumes normal operation

**How tested:** Toggle arm/disarm in dashboard, verify session cleanup in logs

#### Live Stream (MJPEG)
- ✅ `/stream/{camera_id}` returns valid MJPEG stream
- ✅ Stream works in web browser (HTML `<img>` tag)
- ✅ Frame rate ~10-15 fps (MJPEG encoding overhead)

**How tested:** Browser testing, video player verification

---

### Command Module (R5)

#### Camera Registry
- ✅ Camera registration succeeds on POST `/api/cameras/register`
- ✅ Camera appears in list immediately
- ✅ Heartbeat updates `last_seen` timestamp
- ✅ Offline detection works (no heartbeat > 60s → offline)

**How tested:** Dashboard camera list, CLI curl testing

#### Person Enrollment
- ✅ New person created via POST `/api/persons`
- ✅ Embeddings auto-enrolled from inference sessions (via `/auto-enroll`)
- ✅ Known-person cache synced to Jetson

**How tested:** Dashboard enrollment, direct API testing

#### Arm/Disarm
- ✅ System arm/disarm state POSTs to Jetson immediately
- ✅ Jetson enforces policy (discard sessions when disarmed)
- ✅ Dashboard reflects state in real-time

**How tested:** Dashboard controls, inference service log verification

#### Scheduled Arm/Disarm
- ✅ Schedule configuration accepts `arm_time` and `disarm_time` (HH:MM format)
- ✅ System auto-arms at scheduled time
- ✅ System auto-disarms at scheduled time

**How tested:** Manual schedule configuration, time-based testing (or fast-forward via mock clock)

#### Firmware Management
- ✅ Firmware upload via curl succeeds (HTTP 200)
- ✅ Version check returns latest version per channel
- ✅ Binary download works (HTTP 200, valid .bin file)

**How tested:** Manual uploads, camera OTA polling verification

#### WebSocket Dashboard
- ✅ Real-time event stream connects
- ✅ Arm/disarm changes reflect in dashboard immediately
- ✅ Alert events shown in real-time
- ✅ Camera status updates in real-time

**How tested:** Browser DevTools WebSocket inspection, manual event triggering

---

## Automated Testing ⚠️

### Current Status
- **Broken:** `command-module/tests/` suite cannot be collected
  - Root cause: Tests import `database.py` (deleted as SQL-era dead code)
  - `database.py` referenced `settings.database_url`, which no longer exists in `config.py`
  - **Resolution:** Delete tests entirely (see Phase 1 cleanup) or rewrite for Firestore API

### Future (Phase 4 - CI/CD)
- Plan: `pytest` for command-module unit tests (Firebase emulator for integration)
- Plan: Python type checking (`mypy` on command-module, camera C++ static analysis via `clang-tidy`)
- Plan: Secrets scanning (`trufflehog`, `gitleaks`)
- Plan: Firmware build verification (`pio run -e <env>`, no hardware)
- Plan: No hardware-in-the-loop testing in CI (validated manually above)

---

## Performance Benchmarks

### Camera Firmware
- WiFi connect latency: ~2 seconds
- MQTT connect latency: ~20 seconds after WiFi
- Frame capture + encode: ~80ms per frame (10 fps)
- POST `/session/frame` latency: ~500ms (upload bottleneck on WiFi)

### Inference Service
- YOLOv8n detection: 6–10ms/frame (CPU, Jetson)
- InsightFace face detection: 5–8ms/frame (GPU)
- InsightFace embedding + recognition: 20–50ms/face (GPU, depends on DB size)
- Session management + routing: < 5ms

### Command Module
- Camera registry lookup: < 1ms
- Person embedding lookup (pgvector): < 10ms
- Webhook dispatch: 100–500ms (external network dependent)

---

## Known Test Gaps

1. **No multi-Jetson failover testing** — architecture supports single Jetson only
2. **No long-duration stability tests** — manual observation only (seen >1 week uptime)
3. **No bandwidth-constrained WiFi testing** — assumes home LAN (20 Mbps+)
4. **No IR/low-light camera testing** — not supported (hardware gap)
5. **No concurrent multi-camera edge cases** — tested with 2 cameras; limits unknown

---

## Checklist for Public Release

- ✅ Camera firmware compiles and boots (both boards)
- ✅ Jetson inference service runs and serves requests
- ✅ Command module starts and connects to DB
- ✅ Dashboard UI displays without console errors
- ❌ Automated test suite passing (needs rewrite)
- ❌ CI/CD pipeline passing (needs implementation)

---

## See Also

- `implementation.md` — Implementation status & known issues
- `design.md` — Architecture & design decisions
- `../../README.md` — Project overview
