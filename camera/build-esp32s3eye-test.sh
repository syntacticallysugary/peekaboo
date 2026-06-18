#!/bin/bash
# Build script for ESP32-S3-EYE test program

set -e

# Find the source file
SRC_FILE="${1:-src/test_usb.cpp}"

if [ ! -f "$SRC_FILE" ]; then
    echo "ERROR: Source file not found: $SRC_FILE"
    exit 1
fi

# Get the directory of the source file
SRC_DIR=$(dirname "$SRC_FILE")

# Build with PlatformIO - use lib_dir to point to the source directory
platformio run --board esp32s3eye -L "$SRC_DIR"
