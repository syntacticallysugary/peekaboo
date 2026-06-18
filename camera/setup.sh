#!/bin/bash
# One-time environment setup for camera project on Spark (SSH dev machine)
set -e

source /home/jumbob/miniconda3/etc/profile.d/conda.sh

ENV_NAME="camera"

echo "=== Creating conda environment: $ENV_NAME ==="
conda env create -f environment.yml

echo ""
echo "=== Pre-installing ESP32 PlatformIO platform ==="
conda run -n $ENV_NAME pio platform install espressif32

echo ""
echo "=== Checking device access ==="
if [ -e /dev/ttyACM0 ]; then
    echo "ESP32 found at /dev/ttyACM0"
    if groups | grep -q dialout; then
        echo "User already in dialout group"
    else
        echo "Adding $USER to dialout group (requires sudo)..."
        sudo usermod -aG dialout "$USER"
        echo "WARNING: Group change requires logout/login to take effect."
        echo "         Run 'newgrp dialout' to activate in current session."
    fi
    ls -la /dev/ttyACM0
else
    echo "No ESP32 detected on /dev/ttyACM0 — connect device and re-run check."
fi

echo ""
echo "=== Setup complete ==="
echo "Activate with: conda activate $ENV_NAME"
