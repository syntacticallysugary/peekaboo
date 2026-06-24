#!/usr/bin/env bash
# Generate a self-signed TLS certificate for the Jetson inference service.
#
# Run once on the Jetson, then copy jetson.crt to camera/certs/jetson_ca.pem
# on the dev machine so the firmware can verify the server.
#
# Usage:
#   ./tools/gen-jetson-cert.sh <JETSON_IP>
#
# The private key never leaves the Jetson. Only the certificate (public) is
# copied to the firmware tree.

set -euo pipefail

JETSON_IP="${1:?Usage: $0 <JETSON_IP>}"
CERTS_DIR="$(dirname "$0")/../inference-service/certs"
CAMERA_CERTS_DIR="$(dirname "$0")/../camera/certs"

mkdir -p "$CERTS_DIR" "$CAMERA_CERTS_DIR"

openssl req -x509 \
    -newkey rsa:2048 \
    -keyout "$CERTS_DIR/jetson.key" \
    -out    "$CERTS_DIR/jetson.crt" \
    -days   3650 \
    -nodes \
    -subj   "/CN=jetson-inference" \
    -addext "subjectAltName=IP:${JETSON_IP}"

chmod 600 "$CERTS_DIR/jetson.key"

cp "$CERTS_DIR/jetson.crt" "$CAMERA_CERTS_DIR/jetson_ca.pem"

echo ""
echo "Certificate generated:"
echo "  Private key : $CERTS_DIR/jetson.key  (do not commit)"
echo "  Certificate : $CERTS_DIR/jetson.crt  (do not commit)"
echo "  CA for firmware: $CAMERA_CERTS_DIR/jetson_ca.pem"
echo ""
echo "Next steps:"
echo "  1. Rebuild firmware (cmake will embed the new CA cert automatically)"
echo "  2. Restart the inference service: docker compose up -d --build inference"
echo "  3. Update camera/.env: JETSON_URL=https://${JETSON_IP}:8001"
