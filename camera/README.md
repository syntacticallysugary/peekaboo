# Peak-a-Boo Hub

A secure video surveillance system hub built with FastAPI. This service receives JPEG frames from ESP32-CAM devices and streams them as MJPEG to web clients.

## Features

- **Secure Upload**: ESP32-CAM devices upload frames via HTTP POST with PSK authentication
- **In-Memory Storage**: Frames are stored in RAM only (no disk I/O)
- **MJPEG Streaming**: Real-time video streams for web browsers
- **Async Processing**: Non-blocking distribution using Python asyncio

## Prerequisites

- Python 3.10+ in a conda environment named 'camera'
- Required packages: fastapi, uvicorn, opencv, python-multipart

## Installation

The environment and packages are already set up. If needed, activate the environment:

```bash
conda activate camera
```

## Running the Hub

Start the server:

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The hub will be available at `http://localhost:8000`.

## API Endpoints

### POST /api/upload/{cam_id}
Upload a JPEG frame from a camera.

- **Headers**:
  - `Authorization: Bearer secret_psk` (replace with actual PSK)
  - `Content-Type: multipart/form-data`
- **Body**: JPEG file as form data
- **Response**: Confirmation of upload

Example with curl:
```bash
curl -X POST "http://localhost:8000/api/upload/cam_01" \
  -H "Authorization: Bearer secret_psk" \
  -F "file=@frame.jpg"
```

### GET /api/stream/{cam_id}
Stream MJPEG video from a camera.

- **Response**: Multipart MJPEG stream
- Open in browser: `http://localhost:8000/api/stream/cam_01`

### GET /api/cameras
List active cameras with available streams.

- **Response**: JSON list of camera IDs

## Security Notes

- **PSK Authentication**: Currently uses a hardcoded PSK. In production, use environment variables.
- **HTTPS**: The instructions require TLS/SSL. For development, use HTTP; for production, deploy behind a reverse proxy with SSL.
- **Network Isolation**: Cameras should be on a guest network with no knowledge of clients.

## ESP32-CAM Integration

Cameras should:
- Capture JPEG frames every 200ms
- POST to `/api/upload/{cam_id}` with `Authorization: Bearer <PSK>` header
- Use `X-Camera-ID` header if needed (though cam_id is in URL)

## ESP32 Setup

This project supports both ESP32-CAM and ESP32-S3-SPY boards.

### Prerequisites
- [PlatformIO](https://platformio.org/) installed in VS Code (or Docker for isolation)
- ESP32 board connected via USB

### Board Support

| Board | Board Type | Camera | PSRAM | USB Device |
|-------|------------|--------|-------|------------|
| ESP32-CAM | `esp32cam` | AI-Thinker OV2640 | 1MB | `/dev/ttyUSB0` |
| ESP32-S3-SPY | `esp32-s3-devkitc-1` | Optional OV2640 | 8MB (QIO) | `/dev/ttyACM0` |
| ESP32-S3-EYE | `esp32-s3-devkitc-1` | Integrated OV2640 | 8MB (Octal) | `/dev/ttyACM0` |

### Option 1: Native PlatformIO (Recommended for Flashing)
1. Install PlatformIO IDE extension in VS Code
2. Open the project
3. Build and flash directly

### Option 2: Docker Isolation (For Building and Flashing)
To isolate ESP32 development from your host system:

#### For ESP32-CAM:
1. **Find your ESP32 USB device**:
    ```bash
    ls /dev/tty*
    ```
    Common device: `/dev/ttyUSB0`. Note the path.

2. **Build the firmware**:
    ```bash
    chmod +x build-esp32-cam.sh
    ./build-esp32-cam.sh
    ```

3. **Upload to ESP32-CAM**:
    ```bash
    chmod +x upload-esp32-cam.sh
    ./upload-esp32-cam.sh /dev/ttyUSB0
    ```
    Upload sequence:
    - Connect GPIO 0 to GND with a jumper wire
    - Press and release the RST button
    - Wait for upload to complete

4. **Monitor serial output**:
    ```bash
    chmod +x monitor-esp32-cam.sh
    ./monitor-esp32-cam.sh /dev/ttyUSB0
    ```

#### For ESP32-S3-SPY:
1. **Find your ESP32 USB device**:
    ```bash
    ls /dev/tty*
    ```
    Common device: `/dev/ttyACM0` (native USB on S3). Note the path.

2. **Build the firmware**:
    ```bash
    chmod +x build-esp32s3.sh
    ./build-esp32s3.sh
    ```

3. **Upload to ESP32-S3-SPY**:
    ```bash
    chmod +x upload-esp32s3.sh
    ./upload-esp32s3.sh /dev/ttyACM0
    ```
    Upload sequence:
    - Hold the BOOT button
    - Press and release the RST button
    - Release the BOOT button
    - Wait for upload to complete

4. **Monitor serial output**:
    ```bash
    chmod +x monitor-esp32s3.sh
    ./monitor-esp32s3.sh /dev/ttyACM0
    ```

The container gets privileged access to the USB device for flashing, but the PlatformIO installation and build process remain isolated from your host.

#### For ESP32-S3-EYE:
1. **Find your ESP32 USB device**:
    ```bash
    ls /dev/tty*
    ```
    Common device: `/dev/ttyACM0` (native USB on S3). Note the path.

2. **Build the firmware**:
    ```bash
    chmod +x build-esp32s3eye.sh
    ./build-esp32s3eye.sh
    ```

3. **Upload to ESP32-S3-EYE**:
    ```bash
    chmod +x upload-esp32s3eye.sh
    ./upload-esp32s3eye.sh /dev/ttyACM0
    ```
    Upload sequence:
    - Hold the BOOT button
    - Press and release the RST button
    - Release the BOOT button
    - Wait for upload to complete

4. **Monitor serial output**:
    ```bash
    chmod +x monitor-esp32s3eye.sh
    ./monitor-esp32s3eye.sh /dev/ttyACM0
    ```

The container gets privileged access to the USB device for flashing, but the PlatformIO installation and build process remain isolated from your host.

### Configuration
Update the build flags in `platformio.ini` with your actual values:

```ini
build_flags =
    -DCORE_DEBUG_LEVEL=0
    -D WIFI_SSID="\"YourWiFiName\""
    -D WIFI_PASSWORD="\"YourWiFiPassword\""
    -D HUB_URL="\"http://192.168.1.100:8000/api/upload/cam_01\""
    -D SECRET_PSK="\"your_secure_psk\""
```

This keeps sensitive information out of the source code, treating them as "secrets" managed at build time.

### Board-Specific Settings

#### ESP32-CAM
- Frame size: `FRAMESIZE_QVGA` (320x240) for PSRAM
- JPEG quality: Lower number = higher quality (10-63 range)
- Uses PSRAM for frame buffering when available
- GPIO pins configured for AI-Thinker ESP32-CAM
- Memory-safe: Always calls `esp_camera_fb_return()` after processing

#### ESP32-S3-SPY
- No camera module (optional camera can be added)
- Native USB connection (no external USB-to-UART converter needed)
- Larger PSRAM available by default (8MB QIO)
- LED on GPIO 38

#### ESP32-S3-EYE
- Integrated OV2640 camera module (2MP)
- Native USB connection (no external USB-to-UART converter needed)
- 8MB Octal PSRAM for frame buffering
- Camera pins: XCLK=0, SDA=26, SCL=27, Y9=35, Y8=34, Y7=39, Y6=36, Y5=21, Y4=19, Y3=18, Y2=5, VSYNC=25, HREF=23, PCLK=22

### Flashing the ESP32-CAM
1. Connect ESP32-CAM to USB
2. Use PlatformIO "Upload" button (native) or `pio run -e esp32cam --target upload` (Docker)
3. Monitor serial output for connection status

### Flashing the ESP32-S3-SPY
1. Connect ESP32-S3-SPY to USB
2. Use PlatformIO "Upload" button (native) or `pio run -e esp32s3spy --target upload` (Docker)
3. Monitor serial output for connection status

### Flashing the ESP32-S3-EYE
1. Connect ESP32-S3-EYE to USB
2. Use PlatformIO "Upload" button (native) or `pio run -e esp32s3eye --target upload` (Docker)
3. Monitor serial output for connection status

## Troubleshooting

- **No stream**: Ensure frames are being uploaded to the camera ID
- **401 Unauthorized**: Check PSK in Authorization header
- **Memory usage**: Monitor RAM as frames accumulate in memory
- **Performance**: For multiple cameras/clients, consider optimization in future iterations

## Future Enhancements

- Camera heartbeat monitoring
- Dynamic resolution settings
- Web dashboard for camera grid
- Multi-consumer scaling
- Automatic camera registration