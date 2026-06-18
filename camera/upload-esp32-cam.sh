#!/bin/bash
# Upload ESP32-CAM firmware from Docker container
# Usage: ./upload-esp32-cam.sh /dev/ttyUSB0

DEVICE=${1:-/dev/ttyUSB0}

if [ ! -e "$DEVICE" ]; then
    echo "Device $DEVICE not found. Please check your ESP32 connection."
    echo "Common devices: /dev/ttyUSB0, /dev/ttyACM0"
    echo "Run 'ls /dev/tty*' to find your device."
    exit 1
fi

echo "--- ESP32-CAM Upload Sequence ---"
echo "1. Ensure GPIO 0 is jumpered to GND."
echo "2. Press and release the RST button on the back of the camera NOW."
echo "Waiting 3 seconds for you to get ready..."
sleep 3
echo "Starting upload to $DEVICE..."

# Run upload in container with device access
docker run --rm \
    -v $(pwd):/workspace \
    --device $DEVICE \
    --privileged \
    peakaboo-esp32 \
    pio run -e esp32cam --target upload --upload-port $DEVICE
