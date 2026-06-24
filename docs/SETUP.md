# Peekaboo Intelligence — Setup Guide

Welcome! This guide walks you through setting up Peekaboo Intelligence in your home network.

## Prerequisites

- **Jetson Orin Nano** (4 GB or 8 GB, Ubuntu 20.04+)
- **ESP32-S3-EYE** or **XIAO ESP32-S3 Sense** camera board(s)
- **Docker & Docker Compose** (on R5 workstation or Jetson)
- **PlatformIO CLI** (for firmware builds)
- **Google Cloud** project with Firestore enabled (or use emulator for local dev)
- **Network setup**: LAN with WiFi for cameras, wired for Jetson/command module

---

## Step 1: Clone & Create Credential Files

```bash
git clone https://github.com/YOUR_ORG/peekaboo.git
cd peekaboo
```

### 1a. Environment File (Root)

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
# Edit .env:
# - GCP_PROJECT_ID: your Google Cloud project name
# - GCP_SA_KEY_PATH: path to your Firestore service account JSON
# - MQTT_COMMAND_PASSWORD: generate with: python3 -c "import secrets; print(secrets.token_urlsafe(24))"
# - INFERENCE_NODE_URL: IP of your Jetson (e.g., http://192.168.1.108:8001)
```

### 1b. Camera Firmware Configuration

Copy `camera/.env.example` to `camera/.env` and fill in your credentials:

```bash
cp camera/.env.example camera/.env
# Edit camera/.env:
# - WIFI_SSID: your network name
# - WIFI_PASSWORD: your WiFi password
# - COMMAND_MODULE_URL: IP of your command module (e.g., http://192.168.1.105:8081)
# - JETSON_URL: IP of your Jetson (e.g., http://192.168.1.108:8001)
# - MQTT_BROKER_HOST: IP where Mosquitto runs (usually same as command module)
# - MQTT_PASSWORD_*: generate passwords for each camera (one per line)
#   Example: MQTT_PASSWORD_S3EYE_01=<random_password>
```

Generate MQTT passwords:
```bash
for i in 1 2; do
  python3 -c "import secrets; print('MQTT_PASSWORD_S3EYE_0${i}=' + secrets.token_urlsafe(24))"
done
```

### 1c. Firmware Credentials Header

Copy `camera/credentials.h.example` to `camera/credentials.h`:

```bash
cp camera/credentials.h.example camera/credentials.h
# This will be auto-generated during build based on camera/.env
# No manual edits needed (platformio pre-build script handles it)
```

### 1d. Inference Service Configuration

Copy `inference-service/.env.example` to `inference-service/.env`:

```bash
cp inference-service/.env.example inference-service/.env
# Adjust if needed (defaults are fine for most setups)
```

---

## Step 2: Build & Flash Firmware

### 2a. Install PlatformIO

```bash
pip install platformio
```

### 2b. Build Firmware

```bash
cd camera
# For ESP32-S3-EYE
pio run -e esp32s3eye

# For XIAO ESP32-S3 Sense
pio run -e xiao_s3_01
```

### 2c. Flash to Device

Connect your camera board via USB and enter bootloader mode:
- **ESP32-S3-EYE**: Hold **BOOT** button, press **RST**, release **BOOT**
- **XIAO ESP32-S3 Sense**: Hold **BOOT** button, press **RST**, release **BOOT**

Then flash:
```bash
# For ESP32-S3-EYE
pio run -e esp32s3eye -t upload

# For XIAO
pio run -e xiao_s3_01 -t upload
```

Monitor the device:
```bash
pio device monitor -e esp32s3eye -b 1200
```

---

## Step 3: Deploy Services

### 3a. MQTT Broker Setup

Generate Mosquitto password file:
```bash
# Create password file with command-module user
mosquitto_passwd -c mosquitto/config/passwd command-module YOUR_MQTT_PASSWORD_FROM_ENV
```

### 3b. Start Docker Services

```bash
docker-compose up -d
```

### 3c. Verify Services

```bash
# Check all containers
docker-compose ps

# View command-module logs
docker-compose logs -f command-module

# Test MQTT broker
mosquitto_sub -h 127.0.0.1 -p 1883 -u command-module -P YOUR_PASSWORD -t "peekaboo/status/#"
```

---

## Step 4: Register Cameras

Open the command module dashboard:

```
http://localhost:8081
```

1. Click **Settings** → **Cameras** → **Register**
2. Enter camera ID (e.g., `s3eye-01`)
3. Enter camera IP (e.g., `192.168.1.50`)
4. Click **Register**

Repeat for each camera.

---

## Step 5: Enroll Known Persons

1. Click **Settings** → **People** → **Add Person**
2. Enter name (e.g., "Alice")
3. Upload 3–5 face photos (different angles/lighting)
4. Click **Enroll**

---

## Troubleshooting

### Firmware Build Fails: "WIFI_PASSWORD not defined"

Ensure `camera/.env` exists and has all required variables:
```bash
cat camera/.env | grep WIFI_SSID
```

### Cameras Don't Connect

1. Check WiFi password in `camera/.env` matches your network
2. Check camera IP is on the same network as your computer
3. Verify router is broadcasting SSID (not hidden)
4. Check device serial monitor:
   ```bash
   pio device monitor -e esp32s3eye
   ```

### MQTT Connection Fails

1. Verify Mosquitto is running: `docker-compose ps | grep mqtt`
2. Check MQTT password in `camera/.env` matches `mosquitto/config/passwd`
3. Verify MQTT_BROKER_HOST IP is correct
4. Test manually:
   ```bash
   mosquitto_pub -h <MQTT_HOST> -u s3eye-01 -P <PASSWORD> -t "peekaboo/cmd/s3eye-01" -m '{"cmd":"diag"}'
   ```

### Jetson Inference Service Crashes

1. Check available GPU memory: `nvidia-smi`
2. Verify inference service logs: `docker logs peekaboo-inference`
3. Ensure models are downloaded: `ls inference-service/models/`

---

## File Organization

```
peekaboo/
├── .env                           # ⚠️ NOT in git (you create this)
├── .env.example                   # Template (in git)
├── camera/
│   ├── .env                       # ⚠️ NOT in git
│   ├── .env.example               # Template (in git)
│   ├── credentials.h              # ⚠️ NOT in git (auto-generated by build)
│   ├── credentials.h.example      # Template (in git)
│   └── src/
│       ├── s3eye/                 # ESP32-S3-EYE firmware
│       └── ...
├── command-module/
│   ├── src/                       # FastAPI backend
│   └── frontend/                  # Vue dashboard
├── inference-service/
│   ├── .env.example               # Template (in git)
│   └── src/                       # Jetson inference service
├── mosquitto/
│   └── config/
│       └── passwd                 # ⚠️ NOT in git (you generate this)
├── docker-compose.yml
├── docs/
│   ├── SETUP.md                   # This file
│   └── ARCHITECTURE.md
└── README.md
```

**⚠️ Files NOT in git (add to `.env` files, never commit):**
- Root `.env`
- `camera/.env`
- `camera/credentials.h`
- `mosquitto/config/passwd`

---

## Next Steps

1. Read [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) to understand the system design
2. See [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md) for common issues
3. Check [`camera/README.md`](camera/README.md) for firmware-specific details
4. Review [`command-module/frontend/README.md`](command-module/frontend/README.md) for dashboard development

---

## Support

For issues, questions, or contributions, see [CONTRIBUTING.md](CONTRIBUTING.md) or open an issue on GitHub.

Happy monitoring! 🎥
