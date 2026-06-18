#!/bin/bash
# Upload Seeed XIAO ESP32S3 firmware via native PlatformIO
# Usage: ./upload-esp32s3.sh [/dev/ttyACM0]

DEVICE=${1:-/dev/ttyACM0}

if [ ! -e "$DEVICE" ]; then
    echo "Device $DEVICE not found."
    echo "Run 'ls /dev/ttyACM* /dev/ttyUSB*' to find your device."
    exit 1
fi

echo "--- XIAO ESP32S3 Upload ---"
echo "The xiao_s3_01 environment uses usb_reset — no manual BOOT button needed."
echo "Uploading to $DEVICE..."

~/.platformio/penv/bin/pio run -e xiao_s3_01 --target upload --upload-port "$DEVICE"
