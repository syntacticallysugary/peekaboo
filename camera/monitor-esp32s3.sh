#!/bin/bash
# Monitor ESP32-S3-SPY serial output from Docker container
# Usage: ./monitor-esp32s3.sh /dev/ttyACM0

DEVICE=${1:-/dev/ttyACM0}

if [ ! -e "$DEVICE" ]; then
    echo "Device $DEVICE not found. Please check your ESP32 connection."
    echo "Common devices: /dev/ttyUSB0, /dev/ttyACM0"
    exit 1
fi

echo "Monitoring ESP32-S3-SPY on $DEVICE..."

# Run monitor in container with device access
docker run --rm -it \
    --device $DEVICE \
    --privileged \
    peakaboo-esp32 \
    pio device monitor --port $DEVICE
