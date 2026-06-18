# MQTT Control Channel

Secure remote control for the cameras — reboot, live diagnostics, and an
on-demand OTA check — over an authenticated, encrypted MQTT channel.

## Why it exists

The cameras are outbound-push clients with no inbound listener, so a wedged
camera previously had no remote recovery path short of a physical power cycle.
This channel gives the command-module a way to reach a camera that is still
associated to WiFi but otherwise unresponsive.

## Security model

Threat model: a compromised IoT device pivoting on the LAN, plus accidents — not
the public internet (only WireGuard is port-forwarded). Defenses, in layers:

1. **No anonymous access.** `allow_anonymous false`; every client authenticates.
2. **Per-device credentials.** Each camera authenticates as its own user
   (`= camera_id`), so a leaked credential is revocable for one device.
3. **ACL isolation.** A camera may only read its own `peekaboo/cmd/<id>` topic
   and write its own `peekaboo/status/<id>`. The command-module is the only
   principal allowed to publish commands. A compromised camera cannot command,
   impersonate, or snoop on another camera. (Verified: a camera subscribing to
   `peekaboo/cmd/#` receives only its own messages.)
4. **TLS on the LAN.** Cameras connect on 8883 over TLS and verify the broker
   against an embedded CA. The command-module uses a loopback-only plaintext
   listener (1883, `127.0.0.1`) — that traffic never leaves the host.
5. **Command hardening in firmware.** Only `reboot` / `diag` / `ota_check` are
   accepted. Each command carries a random nonce and a unix timestamp; the
   firmware rejects replayed nonces and (once its clock is SNTP-synced) stale
   timestamps. Commands are published non-retained, so a reconnecting camera
   never replays an old command. Reboot is debounced for the first 60s after
   boot to prevent a reboot loop.

## Topic layout

```
peekaboo/cmd/<camera_id>      command-module -> camera   {"cmd","nonce","ts"}
peekaboo/status/<camera_id>   camera -> command-module   {"event",...} / diag
```

## One-time setup

```bash
# 1. Generate the CA + broker server cert (SAN bound to the broker/host IP).
tools/gen-mqtt-certs.sh 192.168.1.105

# 2. Generate per-device passwords. Capture the printed values.
tools/gen-mqtt-passwd.sh
#    -> put the command-module password in .env as MQTT_COMMAND_PASSWORD
#    -> put each camera password in camera/.env as MQTT_PASSWORD_<CAMERA_ID>

# 3. Bring up the hardened broker + command-module.
docker compose up -d --build mqtt command-module

# 4. Flash each camera once over USB to ship the MQTT firmware + embedded CA.
cd camera && pio run -e esp32s3eye -t upload   # (and xiao_s3_01, etc.)
```

The CA, broker keys, and password file are git-ignored (`mosquitto/certs/`,
`mosquitto/config/passwd`, `camera/certs/`). If the broker host IP changes,
re-run `gen-mqtt-certs.sh` with the new IP and re-flash the cameras.

## Usage

From a camera's detail page in the Command Console: **Diagnostics** (RSSI,
uptime, free heap, firmware, reset reason) and **Reboot**. Or via API:

```
POST /api/cameras/<id>/reboot
POST /api/cameras/<id>/diag        # waits for the response, 504 if offline
POST /api/cameras/<id>/ota-check
GET  /api/cameras/<id>/status      # last status message received
```
