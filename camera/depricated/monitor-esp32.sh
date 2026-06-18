#!/bin/bash
# Monitor ESP32 serial output from Docker container
# Usage: ./monitor-esp32.sh /dev/ttyUSB0

DEVICE=${1:-/dev/ttyUSB0}

if [ ! -e "$DEVICE" ]; then
    echo "Device $DEVICE not found. Please check your ESP32 connection."
    echo "Common devices: /dev/ttyUSB0, /dev/ttyACM0"
    exit 1
fi

echo "Monitoring $DEVICE..."

# Run monitor in container with device access
docker run --rm -it \
    --device $DEVICE \
    --privileged \
    peakaboo-esp32 \
    pio device monitor --port $DEVICE