# USB Device Rules for Camera Boards

To make USB device paths predictable across reboots (e.g., `/dev/s3eye` instead of `/dev/ttyACM0`), create udev rules on your workstation.

## Finding Device Serials

Each USB device has a unique serial number. Find yours:

```bash
# List all USB devices with their serial numbers
udevadm info --name=/dev/ttyACM0 --attribute-walk | grep serial

# Or use lsusb
lsusb -v | grep iSerial
```

Example output:
```
ATTRS{serial}=="ABC123DEF456"
```

## Creating the Rules File

Create `/etc/udev/rules.d/99-peekaboo-cameras.rules`:

```bash
sudo tee /etc/udev/rules.d/99-peekaboo-cameras.rules > /dev/null << 'EOF'
# Peekaboo Intelligence — USB camera device rules
# Creates predictable symlinks for ESP32-S3 boards

# ESP32-S3-EYE board (serial: ABC123DEF456)
SUBSYSTEMS=="usb", ATTRS{idVendor}=="303a", ATTRS{idProduct}=="0009", ATTRS{serial}=="ABC123DEF456", SYMLINK+="s3eye"

# XIAO ESP32-S3 Sense board (serial: XYZ789GHI012)  
SUBSYSTEMS=="usb", ATTRS{idVendor}=="303a", ATTRS{idProduct}=="0009", ATTRS{serial}=="XYZ789GHI012", SYMLINK+="ttyACM_xiao"

# Reload rules
EOF

# Apply rules immediately
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Verifying the Rules

After connecting a camera:

```bash
ls -la /dev/s3eye /dev/ttyACM_xiao
```

Should show symlinks to the actual device files.

## Using with PlatformIO

In `platformio.ini`, reference the symlinks:

```ini
[env:esp32s3eye]
upload_port = /dev/s3eye

[env:xiao_s3_01]
upload_port = /dev/ttyACM_xiao
```

## Troubleshooting

- **Symlink not created:** Check vendor/product IDs match your board (`lsusb -v`)
- **Permission denied:** Add user to `dialout` group: `sudo usermod -a -G dialout $USER` (restart shell/login)
- **Multiple boards:** Add multiple rules with different `ATTRS{serial}` and `SYMLINK+="..."` values

## See Also

- `/etc/udev/rules.d/` — System udev rules directory
- `udevadm info --name=/dev/ttyACM0 --attribute-walk` — Full device attributes
