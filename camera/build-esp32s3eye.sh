#!/bin/bash
# Build ESP32-S3-EYE firmware in Docker container
# Based on Espressif ESP32-S3-EYE with OV2640 camera and 8MB Octal PSRAM

set -e

# Build the Docker image
docker build -f Dockerfile.esp32 -t peakaboo-esp32 .

# Run build for ESP32-S3-EYE
docker run --rm -v $(pwd):/workspace peakaboo-esp32 pio run -e esp32s3eye

echo "Build complete!"
echo "To upload: ./upload-esp32s3eye.sh /dev/ttyACM0"
