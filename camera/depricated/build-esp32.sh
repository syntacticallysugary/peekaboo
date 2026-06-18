#!/bin/bash
# Build ESP32 firmware in Docker container

# Build the Docker image
docker build -f Dockerfile.esp32 -t peakaboo-esp32 .

# Run build
docker run --rm -v $(pwd):/workspace peakaboo-esp32