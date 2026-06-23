# Implementation Status

**As of 2026-06-23** — Production-ready for a single Jetson + multiple cameras + local command module.

## Implemented ✅

### Camera Firmware (ESP32-S3)
- ✅ JPEG capture and motion detection (JPEG delta)
- ✅ WiFi connectivity with WPA3-SAE support
- ✅ MQTT TLS client for control commands
- ✅ HTTP POST to Jetson `/session/frame` endpoint
- ✅ Heartbeat (1 frame/sec to keep sessions alive)
- ✅ OTA firmware updates (self-update via command module)
- ✅ Per-device camera ID + firmware channel
- ✅ Config provisioning from `.env` at build time
- ✅ Both ESP32-S3-EYE and XIAO ESP32-S3 Sense boards supported

### Inference Service (Jetson)
- ✅ YOLOv8n person detection (CPU, ~8ms/frame)
- ✅ InsightFace face detection + recognition (GPU, ~50ms/frame)
- ✅ Session management (per-camera, auto-rotate)
- ✅ Known-person cache (synced from command module)
- ✅ Unknown-person alert after 5 seconds no-match
- ✅ Unknown-person alert even if no face ever detected (intruder backlit case)
- ✅ Person sustain threshold (0.40 confidence to keep session alive)
- ✅ 15-minute global known-person cooldown (all cameras suppressed)
- ✅ Arm/disarm state enforcement (Jetson immediately discards sessions)
- ✅ MJPEG live stream per camera
- ✅ Frame extraction (first frame of recording)

### Command Module (R5)
- ✅ FastAPI REST API (port 8081)
- ✅ Camera registry + heartbeat tracking
- ✅ Person enrollment + embeddings database
- ✅ Alert routing to external webhooks
- ✅ System arm/disarm + scheduled arm/disarm
- ✅ Firmware upload + version management
- ✅ WebSocket dashboard (real-time event stream)
- ✅ LangGraph orchestration (alert → webhook dispatch path)

### Hardware
- ✅ ESP32-S3-EYE board working + deployed
- ✅ XIAO ESP32-S3 Sense working + deployed
- ✅ Jetson Orin Nano 8GB (GPU for face recognition)
- ✅ R5 workstation (command module host)

---

## Partially Implemented ⚠️

### Recording & Storage
- ✅ MJPEG encoding per-session
- ✅ Recording uploaded to command module
- ✅ Webhook dispatch on alerts
- ⚠️ S3-compatible object store abstraction (code exists but not tested beyond local disk)
- ⚠️ Recording retention policy (configured but not enforced at scale)

### Dashboard (React frontend)
- ✅ Arm/disarm controls
- ✅ Camera list + live view (snapshot)
- ⚠️ Event log (created but not fully connected)
- ⚠️ Person management UI (bare bones)
- ⚠️ Settings page layout (exists but not fully wired)

---

## Not Yet Implemented ❌

### Features
- ❌ Cross-camera person tracking (embedding correlations shown in UI)
- ❌ Motion-only recording mode (all recording tied to face/arm state)
- ❌ Facial recognition confidence threshold UI adjustment
- ❌ IR/low-light board support
- ❌ Multi-zone motion masking
- ❌ Export recordings as MP4 (MJPEG stored internally)

### Operational
- ❌ Automated backup of PostgreSQL + recordings
- ❌ Camera firmware rollback
- ❌ Analytics dashboard (heatmaps, person frequency, etc.)
- ❌ Per-person notification preferences
- ❌ Bluetooth or local-user enrollment (enrollment via live face crop only)

### Monitoring
- ❌ Alerting on Jetson/command module outage
- ❌ Disk space monitoring + low-space alerts
- ❌ Person detection false-positive rate metrics
- ❌ WiFi signal strength tracking per camera

---

## Known Issues & Workarounds

### XIAO ESP32-S3 Hardware
- **No visible BOOT/RST buttons** — tiny pads near USB-C end. Bootloader entry requires finding them by feel or measuring continuity.
- **Workaround:** See `../../camera/README.md` "XIAO bootloader entry" section.

### TFLite linking (XIAO)
- **Issue:** CMakeLists.txt links `esp-tflite-micro` for all XIAO builds (even pass-through firmware).
- **Root cause:** TFLite ONNX assembly kernels attempt PSRAM writes; ESP32-S3 PIE only allows internal SRAM writes.
- **Fix:** `CONFIG_NN_ANSI_C=y` in `sdkconfig.xiao_peekaboo.defaults` (portable C kernels).
- **Permanent:** This fix must stay in the config; removing it causes StoreProhibited crashes.

### Person detector threshold tuning
- **Issue:** Original 0.35 threshold led to ~1 false positive per 2-3 minutes on empty space.
- **Fix:** Raised to 0.55 (2026-06-23). Empty-space scores cluster 0.38-0.45; known good detections are 0.55+.
- **Trade-off:** May miss distant/partially-obscured persons. Empirically tested and acceptable for home surveillance.

### OTA data partition
- **Issue:** Device was booting from old OTA partition (ota_1) instead of new flash (ota_0).
- **Cause:** `ota_data_initial.bin` didn't reset partition pointer on flash.
- **Fix:** Bumped firmware version (1.1.0 → 2.1.0) to supersede old version served by command module. Now all cameras boot new firmware on next OTA check.

---

## Testing

### Manual testing (in progress)
- ✅ WiFi connectivity + MQTT control on both camera boards
- ✅ Frame streaming to Jetson (all cameras online in ~15 sec)
- ✅ Person detection + face recognition on known persons
- ✅ Unknown-person alert after 5 seconds no-match
- ✅ 15-minute global cooldown on known-person recognition
- ✅ Arm/disarm enforcement (sessions discarded immediately)
- ✅ OTA firmware update (device self-updates + reboots)

### Automated testing
- ⚠️ Python pytest suite exists but broken (references deleted SQL-era database.py)
- ⚠️ No CI/CD pipeline yet (design planned, implementation blocked)

---

## Migration Path (if AWS deployment planned)

1. **Jetson inference service:** Can move to AWS EC2 GPU instance (same Docker image)
2. **Command module:** Already uses Firestore for data (AWS-compatible via `storage/` abstraction)
3. **Cameras:** No changes needed (HTTP/MQTT endpoints configurable at build time)
4. **Blockers:** No automated backup of recordings to S3 yet; manual copy required

---

## See Also

- `design.md` — Architecture and design decisions
- `requirements.md` — Original requirements (pre-implementation)
- `../../camera/README.md` — Firmware build/flash procedures
- `../README.md` — Project overview
