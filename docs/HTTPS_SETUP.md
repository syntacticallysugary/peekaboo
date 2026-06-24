# HTTPS/TLS Setup for Peekaboo Intelligence

All command-module and inter-service communications use HTTPS with self-signed certificates (internal-only deployment).

## Certificate Generation

### 1. Generate Self-Signed Certificate

```bash
./tools/gen-self-signed-cert.sh
```

This creates:
- `mosquitto/certs/server.key` — Private key (keep secret)
- `mosquitto/certs/server.crt` — Certificate (valid 10 years)

### 2. Verify Certificate

```bash
# View certificate details
openssl x509 -in mosquitto/certs/server.crt -text -noout

# Check validity
openssl x509 -in mosquitto/certs/server.crt -noout -dates
```

## Docker Compose Configuration

Update `docker-compose.yml` to enable HTTPS:

```yaml
command-module:
  build: ./command-module
  container_name: peekaboo-command
  environment:
    # ... other env vars ...
    TLS_KEYFILE: /certs/server.key
    TLS_CERTFILE: /certs/server.crt
  volumes:
    - ./mosquitto/certs:/certs:ro
  ports:
    - "8081:8081"  # HTTPS endpoint
  # Note: Change uvicorn in main.py to use SSL parameters

mqtt:
  image: eclipse-mosquitto:2
  # Existing config already references TLS certs in mosquitto.conf
```

## Application Configuration

### Command Module (FastAPI)

Update `command-module/src/main.py` to enable HTTPS:

```python
if __name__ == "__main__":
    import uvicorn
    
    # Read SSL settings from environment
    ssl_keyfile = os.environ.get("TLS_KEYFILE")
    ssl_certfile = os.environ.get("TLS_CERTFILE")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8081,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
    )
```

Or pass to uvicorn in Dockerfile:

```dockerfile
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8081", \
     "--ssl-keyfile", "/certs/server.key", \
     "--ssl-certfile", "/certs/server.crt"]
```

### Mosquitto Broker

Already configured in `mosquitto/config/mosquitto.conf`:

```conf
# TLS listener for cameras
listener 8883 0.0.0.0
cafile   /mosquitto/certs/ca.crt
certfile /mosquitto/certs/server.crt
keyfile  /mosquitto/certs/server.key
tls_version tlsv1.2
require_certificate false
```

### Camera Firmware

Embed the CA certificate in firmware to validate broker identity:

1. Extract CA cert from server certificate:
   ```bash
   # For self-signed, the cert IS the CA
   cp mosquitto/certs/server.crt camera/src/s3eye/ca_cert.pem
   ```

2. Create C header for firmware:
   ```bash
   # Convert PEM to C array
   xxd -i camera/src/s3eye/ca_cert.pem > camera/src/s3eye/ca_cert.h
   ```

3. Include in firmware:
   ```c
   // camera/src/s3eye/mqtt_task.cpp
   extern const unsigned char ca_cert_pem[];
   extern const unsigned int ca_cert_pem_len;
   
   esp_mqtt_client_config_t cfg = {
       .broker = {
           .address = {
               .hostname = MQTT_BROKER_HOST,
               .port = MQTT_BROKER_PORT,
           },
           .verification = {
               .certificate = ca_cert_pem,
               .certificate_len = ca_cert_pem_len,
           },
       },
       .session = { .protocol_ver = MQTT_PROTOCOL_V_3_1_1 },
       .credentials = { .client_id = CAMERA_ID },
   };
   ```

## Testing

### Test Command Module HTTPS

```bash
# Test with curl (skip cert verification — self-signed)
curl -k https://localhost:8081/health

# Or with explicit CA cert
curl --cacert mosquitto/certs/server.crt https://localhost:8081/health

# Test with Python requests
python3 << 'EOF'
import requests
resp = requests.get(
    "https://192.168.1.105:8081/api/cameras",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    verify="mosquitto/certs/server.crt",  # Verify against our CA
)
print(resp.json())
EOF
```

### Test Mosquitto MQTT over TLS

```bash
# Subscribe to status topic
mosquitto_sub -h 192.168.1.105 -p 8883 \
  -u command-module -P "$MQTT_COMMAND_PASSWORD" \
  --cafile mosquitto/certs/server.crt \
  -t "peekaboo/status/#"

# Publish test message
mosquitto_pub -h 192.168.1.105 -p 8883 \
  -u s3eye-01 -P "$MQTT_PASSWORD_S3EYE_01" \
  --cafile mosquitto/certs/server.crt \
  -t "peekaboo/status/s3eye-01" \
  -m '{"status": "ok"}'
```

## Certificate Renewal

Self-signed certs in this setup don't need external renewal, but if cert expires:

1. Generate new certificate:
   ```bash
   ./tools/gen-self-signed-cert.sh
   ```

2. Update firmware with new CA cert (see "Camera Firmware" section above)

3. Rebuild and reflash all cameras

4. Restart services:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

## Browser Warning

When accessing the dashboard in a browser:
- **Self-signed cert warning** is expected (not a real security issue for internal LAN)
- Click "Advanced" → "Proceed" to continue
- Alternatively, import the certificate as trusted in your system

## Security Considerations

✅ **Encryption**: All communications encrypted in transit

✅ **Authentication**: Certificate used for server identity verification

✅ **Performance**: Self-signed certs no overhead vs. bought certs

❌ **No External Verification**: Cannot verify cert through public CA (by design — internal only)

## Deployment to Production

If deploying beyond LAN (e.g., exposing via Let's Encrypt):

1. **Get a real certificate**:
   ```bash
   certbot certonly --standalone -d yourdomain.com
   # Copy /etc/letsencrypt/live/yourdomain.com/privkey.pem → server.key
   # Copy /etc/letsencrypt/live/yourdomain.com/fullchain.pem → server.crt
   ```

2. **Update docker-compose.yml** to mount real cert paths

3. **Set up auto-renewal** (certbot renew via cron)

4. **Firmware CA cert update** (Let's Encrypt uses standard root CAs, most TLS libraries already have them)

## Troubleshooting

### "Certificate verify failed"

**Problem**: Camera/client can't verify broker certificate

**Solution**:
1. Ensure `ca_cert.pem` (or CA extracted from server.crt) is embedded in firmware
2. Rebuild and reflash firmware
3. Verify firmware includes cert during build:
   ```bash
   pio run -e esp32s3eye -v  # Verbose build, look for ca_cert output
   ```

### "SSL: CERTIFICATE_VERIFY_FAILED" in Python

**Problem**: `requests` library rejecting self-signed cert

**Solution**: Use `verify=False` (dev only) or pass `verify="/path/to/ca_cert.pem"`

### Mosquitto won't start

**Problem**: `mosquitto.conf` references missing cert files

**Solution**:
```bash
# Verify certs exist
ls -la mosquitto/certs/{server.key,server.crt}

# Check mosquitto.conf paths match
grep -E "^(cafile|certfile|keyfile)" mosquitto/config/mosquitto.conf

# Restart
docker-compose down mqtt
docker-compose up -d mqtt
```

## See Also

- `mosquitto/config/mosquitto.conf` — Broker TLS configuration
- `tools/gen-self-signed-cert.sh` — Certificate generation script
- [OpenSSL Docs](https://www.openssl.org/docs/)
- [Mosquitto TLS Guide](https://mosquitto.org/documentation/authentication-methods/)
