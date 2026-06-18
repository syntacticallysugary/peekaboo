#!/bin/bash
# Monitor script for ESP32-S3-EYE with auto-detection of serial port

set -e

# Find the most recent ttyACM device (in case port changes on restart)
SERIAL_PORT=$(ls -t /dev/ttyACM* 2>/dev/null | head -n 1)

if [ -z "$SERIAL_PORT" ]; then
    echo "ERROR: No ESP32 device found on /dev/ttyACM*"
    echo "Please connect the ESP32-S3-EYE and try again."
    exit 1
fi

echo "=============================================="
echo "ESP32-S3-EYE Serial Monitor"
echo "=============================================="
echo "Detected port: $SERIAL_PORT"
echo "=============================================="
echo "Press Ctrl+A, then X to exit minicom"
echo "=============================================="

# Use minicom for serial monitoring
minicom -D "$SERIAL_PORT" -b 115200 -o
