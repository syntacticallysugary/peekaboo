#!/bin/bash
# Build ESP32-S3-SPY firmware in Docker container
set -e

# Pre-generate credentials.h from .env so cmake doesn't need env vars at build time.
# cmake's $ENV{} isn't reliable inside Docker. Python reads .env without shell expansion,
# avoiding dollar-sign corruption in passwords like "!A$8ad$8ear!".
# Generate credentials.h into src/s3eye/ (already in INCLUDE_DIRS, writable by user).
# Python avoids shell expansion of special chars like $8 in passwords.
python3 - << 'PYEOF'
from pathlib import Path

env = {}
for line in Path(".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

out = Path("src/s3eye/credentials.h")  # src/s3eye is in INCLUDE_DIRS; picked up before CMAKE_BINARY_DIR
out.write_text(
    "#pragma once\n"
    f'#define WIFI_SSID "{env.get("WIFI_SSID", "")}"\n'
    f'#define WIFI_PASSWORD "{env.get("WIFI_PASSWORD", "")}"\n'
    f'#define COMMAND_MODULE_URL "{env.get("COMMAND_MODULE_URL", "")}"\n'
    f'#define JETSON_URL "{env.get("JETSON_URL", "")}"\n'
    f'#define SECRET_PSK "{env.get("SECRET_PSK", "")}"\n'
)
print("Generated", out)
PYEOF

# Use native PlatformIO for ESP-IDF framework builds.
# Docker-based builds leave root-owned files in managed_components and .pio
# that break subsequent native builds, so we avoid Docker here.
~/.platformio/penv/bin/pio run -e xiao_s3_01
