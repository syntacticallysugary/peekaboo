# MQTT Setup for Peekaboo Intelligence

Peekaboo uses MQTT for camera control commands (reboot, OTA check, diagnostics) with per-device authentication and fine-grained access control lists (ACLs).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Mosquitto Broker (192.168.x.x:8883 TLS)                    │
│                                                             │
│ Users:                                                      │
│  - command-module (central orchestrator)                   │
│  - s3eye-01, s3eye-02 (camera devices)                    │
│  - xiao-01, xiao-02 (camera devices)                      │
│                                                             │
│ Topics:                                                     │
│  - peekaboo/cmd/{camera_id}    (command-module → cameras)  │
│  - peekaboo/status/{camera_id} (cameras → command-module)  │
└─────────────────────────────────────────────────────────────┘
```

## Setup Steps

### 1. Generate Per-Device Passwords

Create random passwords for each device and the command module:

```bash
# Command module (central controller)
MQTT_COMMAND_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
echo "MQTT_COMMAND_PASSWORD=$MQTT_COMMAND_PASSWORD"

# Camera devices
MQTT_S3EYE_01=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
MQTT_S3EYE_02=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
MQTT_XIAO_01=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
MQTT_XIAO_02=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")

echo "MQTT_PASSWORD_S3EYE_01=$MQTT_S3EYE_01"
echo "MQTT_PASSWORD_S3EYE_02=$MQTT_S3EYE_02"
echo "MQTT_PASSWORD_XIAO_01=$MQTT_XIAO_01"
echo "MQTT_PASSWORD_XIAO_02=$MQTT_XIAO_02"
```

**Save these in a secure location** (password manager, encrypted file, etc.).

### 2. Update camera/.env

Add the per-device passwords:

```bash
# Replace placeholders in camera/.env
MQTT_PASSWORD_S3EYE_01=<generated-password-1>
MQTT_PASSWORD_S3EYE_02=<generated-password-2>
MQTT_PASSWORD_XIAO_01=<generated-password-3>
MQTT_PASSWORD_XIAO_02=<generated-password-4>
```

The **pre-build script** (`pre_build_espdl.py`) will automatically select the correct password for each camera based on its CAMERA_ID during firmware compilation.

**Verify**: Each environment in `camera/platformio.ini` has a unique `CAMERA_ID`:

```ini
[env:esp32s3eye]
build_flags = ... -D CAMERA_ID="\"s3eye-01\""

[env:esp32s3eye_02]
build_flags = ... -D CAMERA_ID="\"s3eye-02\""
```

### 3. Create Mosquitto Password File

Generate the password file used by the MQTT broker:

```bash
# Start fresh
rm -f mosquitto/config/passwd

# Add command-module user
mosquitto_passwd -b mosquitto/config/passwd command-module "$MQTT_COMMAND_PASSWORD"

# Add each camera user
mosquitto_passwd -b mosquitto/config/passwd s3eye-01 "$MQTT_S3EYE_01"
mosquitto_passwd -b mosquitto/config/passwd s3eye-02 "$MQTT_S3EYE_02"
mosquitto_passwd -b mosquitto/config/passwd xiao-01 "$MQTT_XIAO_01"
mosquitto_passwd -b mosquitto/config/passwd xiao-02 "$MQTT_XIAO_02"
```

**Result**: `mosquitto/config/passwd` file with hashed passwords.

### 4. Create ACL File

Copy the ACL template and customize for your devices:

```bash
cp mosquitto/config/acl.example mosquitto/config/acl
```

The template allows:
- **command-module**: read all status topics, write all command topics
- **Each camera**: read only its own command topic, write only its own status topic

Example: `s3eye-01` can:
- ✅ PUBLISH to `peekaboo/status/s3eye-01` (send status)
- ✅ SUBSCRIBE to `peekaboo/cmd/s3eye-01` (receive commands)
- ❌ PUBLISH to `peekaboo/cmd/*` (cannot send commands)
- ❌ SUBSCRIBE to `peekaboo/status/s3eye-02` (cannot spy on other cameras)

### 5. Update docker-compose.yml

Ensure the password file and ACL are mounted:

```yaml
mqtt:
  image: eclipse-mosquitto:2
  volumes:
    - ./mosquitto/config:/mosquitto/config
    - ./mosquitto/certs:/mosquitto/certs:ro
    - ./mosquitto/data:/mosquitto/data
```

The config already references:
- `password_file /mosquitto/config/passwd` (you just created)
- `acl_file /mosquitto/config/acl` (you copied from template)

### 6. Update Root .env

Set the command-module MQTT password:

```bash
# .env
MQTT_COMMAND_PASSWORD=<your-generated-command-module-password>
```

This is used by the command module to authenticate to the broker.

### 7. Rebuild Firmware

Rebuild and flash all cameras with the new per-device passwords:

```bash
cd camera

# Build for each environment
pio run -e esp32s3eye
pio run -e esp32s3eye_02
pio run -e xiao_s3_01
pio run -e xiao_s3_02

# Flash (connect camera USB)
pio run -e esp32s3eye -t upload
# Repeat for other environments
```

The **pre-build script automatically injects the per-device password** from `camera/.env` based on each environment's CAMERA_ID.

### 8. Restart Mosquitto & Services

```bash
docker-compose down mqtt command-module
docker-compose up -d mqtt command-module

# Wait for services to start
sleep 3

# Check logs
docker-compose logs mqtt | head -20
docker-compose logs command-module | head -20
```

### 9. Verify ACLs are Working

Test that ACL enforcement is active:

```bash
# Should SUCCEED: command-module reads all status topics
mosquitto_sub -h <BROKER_IP> -p 8883 \
  -u command-module -P "$MQTT_COMMAND_PASSWORD" \
  --cafile mosquitto/certs/ca.crt \
  -t "peekaboo/status/#" &

# Should SUCCEED: camera publishes its status
mosquitto_pub -h <BROKER_IP> -p 8883 \
  -u s3eye-01 -P "$MQTT_S3EYE_01" \
  --cafile mosquitto/certs/ca.crt \
  -t "peekaboo/status/s3eye-01" \
  -m '{"uptime_s": 12345}'

# Should FAIL: camera tries to publish to another camera's status (permission denied)
mosquitto_pub -h <BROKER_IP> -p 8883 \
  -u s3eye-01 -P "$MQTT_S3EYE_01" \
  --cafile mosquitto/certs/ca.crt \
  -t "peekaboo/status/xiao-01" \
  -m '{"uptime_s": 99999}' 2>&1 | grep -i "connection\|refused\|denied"
  # Should see: Connection error / Permission denied
```

## Key Security Properties

✅ **Per-Device Credentials**: Each camera has unique MQTT password
- ✅ Compromise of one device doesn't expose others
- ✅ Can revoke single device by changing its password in passwd file

✅ **Topic-Level ACLs**: Each device isolated to its own topics
- ✅ Camera can't spy on other cameras (can't read their status)
- ✅ Camera can't send commands to other cameras
- ✅ Camera can't intercept reboot/OTA commands

✅ **Automatic Password Injection**: Pre-build script handles it
- ✅ No manual secrets management per build
- ✅ camera/.env is the single source of truth
- ✅ Each environment gets correct password at compile time

✅ **TLS Encryption**: Camera→Broker communication encrypted
- ✅ Password sent over secure connection (not plaintext)
- ✅ Commands encrypted in transit

## Troubleshooting

### "Connection refused" when camera connects

Check:
1. Is Mosquitto running? `docker-compose ps | grep mqtt`
2. Is the password correct in `camera/.env`? Compare with `mosquitto/config/passwd`
3. Is the broker listening on 8883? `netstat -tlnp | grep 8883`
4. Can you reach the broker? `telnet <BROKER_IP> 8883`

### "Permission denied" when camera publishes

The camera's ACL is too restrictive:
1. Check `mosquitto/config/acl` — does `s3eye-01` have `topic write peekaboo/status/s3eye-01`?
2. Reload Mosquitto: `docker-compose restart mqtt`
3. Check Mosquitto logs: `docker-compose logs mqtt`

### Password hash mismatch after docker-compose down/up

Mosquitto persists to `mosquitto/data/`. If you change passwords:
1. Remove persistence: `rm -rf mosquitto/data/*`
2. Recreate passwd file with new passwords
3. Restart: `docker-compose down mqtt && docker-compose up -d mqtt`

## Adding a New Camera

When adding a new camera device:

1. **Choose CAMERA_ID** and add to `platformio.ini`:
   ```ini
   [env:xiao_s3_03]
   build_flags = ... -D CAMERA_ID="\"xiao-03\""
   ```

2. **Generate password**:
   ```bash
   MQTT_XIAO_03=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
   ```

3. **Add to camera/.env**:
   ```bash
   MQTT_PASSWORD_XIAO_03=$MQTT_XIAO_03
   ```

4. **Add to mosquitto/config/passwd**:
   ```bash
   mosquitto_passwd -b mosquitto/config/passwd xiao-03 "$MQTT_XIAO_03"
   ```

5. **Add to mosquitto/config/acl**:
   ```
   user xiao-03
   topic write peekaboo/status/xiao-03
   topic read peekaboo/cmd/xiao-03
   ```

6. **Build and flash firmware**:
   ```bash
   pio run -e xiao_s3_03
   pio run -e xiao_s3_03 -t upload
   ```

7. **Reload Mosquitto**:
   ```bash
   docker-compose restart mqtt
   ```

Done! The new camera can now connect with its unique credentials and topic restrictions.

## See Also

- [mosquitto.conf](mosquitto/config/mosquitto.conf) — Broker configuration
- [acl.example](mosquitto/config/acl.example) — ACL template with more examples
- [camera/pre_build_espdl.py](camera/pre_build_espdl.py) — Password injection mechanism
- [MQTT Security Guide](https://mosquitto.org/documentation/security/)
