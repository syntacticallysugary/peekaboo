# Peekaboo Intelligence — Camera Firmware

ESP32-S3 firmware for streaming JPEG frames to the Jetson inference node. Cameras run pass-through detection: frame capture → JPEG encoding → HTTP POST to Jetson. All person detection and face recognition runs on the Jetson; the camera is a thin client.

## Supported Boards

| Board | PlatformIO env | USB Device | Flash Size | PSRAM | Notes |
|-------|---|---|---|---|---|
| ESP32-S3-EYE | `esp32s3eye` | `/dev/s3eye` | 8MB | 8MB OPI | Integrated OV2640 camera |
| XIAO ESP32-S3 Sense | `xiao_s3_01` | `/dev/ttyACM0` | 8MB | 8MB OPI | Integrated OV3660 camera; no visible BOOT/RST buttons |

## Prerequisites

- [PlatformIO CLI](https://platformio.org/install/cli) (`pip install platformio`)
- One or more supported boards connected via USB
- Jetson inference service running on `192.168.1.108:8001`
- Command module running on `192.168.1.105:8081`

## Quick Start

### 1. Configure environment

Create a `.env` file at the repo root with your network credentials:

```bash
WIFI_SSID=your-network-name
WIFI_PASSWORD=your-password
MQTT_BROKER_HOST=192.168.1.105
MQTT_PASSWORD=your-mqtt-password
```

These are baked into the firmware at build time via build flags in `platformio.ini`.

### 2. Build and flash

**ESP32-S3-EYE:**
```bash
pio run -e esp32s3eye -t upload
```

**XIAO ESP32-S3 Sense** (requires bootloader entry):
```bash
# 1. Enter bootloader mode:
#    - Hold BOOT pad (small button near USB-C end)
#    - Press and release RST pad
#    - Release BOOT
#    Device enumerates as 303a:1001 (Espressif USB JTAG)
#
# 2. Flash:
pio run -e xiao_s3_01 -t upload

# 3. Exit bootloader:
#    - Press RST once
#    Device boots application, enumerates as 303a:0009
```

### 3. Verify connection

Check the dashboard (`http://192.168.1.105:8081`) — camera should appear online within 15 seconds.

Monitor serial output (optional):
```bash
pio device monitor -e esp32s3eye -b 115200
```

## Architecture

```
Camera Task (core 0, priority 5)
    └─ Capture JPEG frames
    └─ Motion detection (JPEG delta)
    └─ Queue to inference task (1-frame deep, drop if full)

Inference Task (core 1, priority 4)
    └─ Dequeue frames
    └─ Base64 encode
    └─ Queue to network task

Network Task (core 1, priority 3)
    └─ POST /session/frame → Jetson (192.168.1.108:8001)
    └─ Handle responses, track session state
    └─ POST /api/cameras/{id}/heartbeat → Command Module

OTA Task (core 1, priority 1)
    └─ Poll /api/firmware/{channel}/check every 5 minutes
    └─ Download binary if newer version available
    └─ Self-update + reboot

MQTT Task (core 1, priority 2)
    └─ Listen for reboot/restart commands from broker
```

## Build Flags

Configured in `platformio.ini` per environment:

| Flag | Purpose | Example |
|---|---|---|
| `CAMERA_ID` | Device identifier | `xiao-01` |
| `WIFI_SSID` | Network name | `HomeNetwork` |
| `WIFI_PASSWORD` | Network password | `secure-password` |
| `MQTT_BROKER_HOST` | MQTT broker IP | `192.168.1.105` |
| `MQTT_PASSWORD` | MQTT password | `mqtt-secret` |
| `JETSON_URL` | Jetson inference service | `http://192.168.1.108:8001` |
| `COMMAND_MODULE_URL` | Command module URL | `http://192.168.1.105:8081` |
| `FIRMWARE_VERSION` | Semantic version | `2.1.0` |
| `FIRMWARE_CHANNEL` | OTA channel (s3eye, xiao) | `xiao` |

## OTA Updates

Cameras poll the command module every 5 minutes for new firmware:

```
GET /api/firmware/{channel}/check
Response: { "version": "2.1.0" }

If newer:
  GET /api/firmware/{channel}/binary
  Download .bin
  Self-update partition (ota_0 or ota_1)
  Reboot into new firmware
```

To push a new firmware:

```bash
curl -X POST http://192.168.1.105:8081/api/firmware/xiao \
  -H "X-Firmware-Version: 2.1.1" \
  -F "file=@.pio/build/xiao_s3_01/firmware.bin"
```

## Configuration

### Per-Camera Settings

Dynamic settings pushed by the command module:

```python
# camera/src/s3eye/config.h
MOTION_HEARTBEAT_MS = 1000           # send frame every 1s even w/o motion
MOTION_JPEG_DELTA_MIN = 2000         # JPEG byte-count delta for motion
SESSION_END_TIMEOUT_S = 15           # timeout before ending session
OTA_CHECK_INTERVAL_MS = 300000       # 5-minute OTA poll interval
```

### WiFi & Networking

- **SSID/Password**: Build flags (baked into firmware)
- **MQTT**: TLS to `192.168.1.105:8883` with per-camera credentials
- **Jetson**: HTTP to `192.168.1.108:8001` (no TLS on LAN)
- **Command Module**: HTTP to `192.168.1.105:8081` for heartbeat/OTA

## Troubleshooting

### Camera not appearing online
1. Check WiFi credentials in build flags
2. Verify SSID/password with `pio device monitor`
3. Ping camera IP to confirm WiFi connectivity
4. Check Jetson/command module are running (`curl http://192.168.1.105:8081/health`)

### Frames not reaching Jetson
1. Verify Jetson URL in build flags: `http://192.168.1.108:8001`
2. Check serial for frame post errors
3. Confirm network routing between camera and Jetson

### XIAO won't enter bootloader
1. Bootloader pads are **near the USB-C end**, not top/bottom
2. Try different pressure/angle when holding BOOT
3. Verify pad contact with multimeter
4. If stuck: use esptool to erase and restore partition table

### StoreProhibited crash on XIAO
The fix `CONFIG_NN_ANSI_C=y` is in `sdkconfig.xiao_peekaboo.defaults`. This is required because TFLite is linked into all XIAO builds (even when inference is pass-through) and its ONNX assembly kernels crash on PSRAM without this flag. Do not remove it.

### WiFi drops frequently
Symptoms: Offline for 60-750 seconds, then reconnects. Caused by:
- Power supply instability (use USB 3.0 port, not 2.0)
- Concurrent WiFi + TLS load causing brownout
- Fix: Phone charger (2A+) instead of USB

## Development

### Serial monitoring

Use pyserial to avoid hardware reset (DTR):

```bash
python3 -c "
import serial, time
s = serial.Serial('/dev/ttyACM0', 115200, timeout=0.1)
s.dtr = False  # Prevent auto-reset
end = time.time() + 120
while time.time() < end:
    data = s.read(1024)
    if data: print(data.decode(errors='replace'), end='', flush=True)
"
```

### Building without flashing

```bash
pio run -e xiao_s3_01
# Outputs to .pio/build/xiao_s3_01/firmware.bin
```

### Cleaning build artifacts

```bash
pio run -e xiao_s3_01 -t clean
```

## Pin Maps

### ESP32-S3-EYE (integrated OV2640)
- **Camera**: XCLK=15, SDA=4, SCL=5, VSYNC=6, HREF=7, PCLK=13, Y[9:2]={16,17,18,12,10,8,9,11}
- **LED**: GPIO 3

### XIAO ESP32-S3 Sense (integrated OV3660)
- **Camera**: XCLK=10, SDA=40, SCL=39, VSYNC=38, HREF=47, PCLK=13, Y[9:2]={48,11,12,14,16,18,17,15}
- **LED**: GPIO 21
- **SD Card**: CLK=7, CMD=9, D0=8, CS=21 (Arduino mode only)

## See Also

- [../docs/](../docs/) — Architecture notes and planning
- [../README.md](../README.md) — Full system documentation
