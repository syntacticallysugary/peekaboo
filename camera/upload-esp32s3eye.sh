#!/bin/bash
# Upload script for ESP32-S3-EYE
# Based on Espressif ESP32-S3-EYE with OV2640 camera and 8MB Octal PSRAM

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <serial_port>"
    echo "Example: $0 /dev/ttyACM0"
    exit 1
fi

SERIAL_PORT="$1"

echo "=============================================="
echo "ESP32-S3-EYE Upload Instructions"
echo "=============================================="
echo "1. Hold the BOOT button on the ESP32-S3-EYE"
echo "2. Press the EN (reset) button once"
echo "3. Release the BOOT button"
echo "4. Press Enter to continue..."
echo "=============================================="
read

echo "Uploading firmware to ESP32-S3-EYE on $SERIAL_PORT..."
pio run -e esp32s3eye --upload-port "$SERIAL_PORT"

echo "Upload complete!"
