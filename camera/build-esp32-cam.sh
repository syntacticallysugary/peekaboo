#!/bin/bash
# Build ESP32-CAM firmware in Docker container

# Build the Docker image
docker build -f Dockerfile.esp32 -t peakaboo-esp32 .

# Run build for ESP32-CAM
docker run --rm -v $(pwd):/workspace peakaboo-esp32 pio run -e esp32cam
