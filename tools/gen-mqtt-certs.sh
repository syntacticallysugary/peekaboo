#!/usr/bin/env bash
#
# Generate a self-signed CA and a broker server certificate for the Peekaboo
# MQTT control channel (TLS, server-auth only — cameras verify the broker, the
# broker authenticates cameras with username/password + ACLs).
#
# Outputs:
#   mosquitto/certs/ca.crt        — CA cert (also copied to camera/certs for embedding)
#   mosquitto/certs/ca.key        — CA private key (keep offline; only needed to re-sign)
#   mosquitto/certs/server.crt    — broker server cert (SAN = broker IP + hostnames)
#   mosquitto/certs/server.key    — broker server private key
#   camera/certs/mqtt_ca.pem      — CA cert embedded into firmware so cameras trust the broker
#
# Usage:  tools/gen-mqtt-certs.sh [BROKER_IP] [DAYS]
#   BROKER_IP defaults to 192.168.1.105 (the command-module / broker host).
#
set -euo pipefail

BROKER_IP="${1:-192.168.1.105}"
DAYS="${2:-3650}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="${REPO_ROOT}/mosquitto/certs"
CAM_CERT_DIR="${REPO_ROOT}/camera/certs"

mkdir -p "${CERT_DIR}" "${CAM_CERT_DIR}"

echo "Generating CA..."
openssl genrsa -out "${CERT_DIR}/ca.key" 4096
openssl req -new -x509 -days "${DAYS}" -key "${CERT_DIR}/ca.key" \
    -out "${CERT_DIR}/ca.crt" \
    -subj "/O=Peekaboo/CN=Peekaboo MQTT CA"

echo "Generating broker server key + CSR (SAN: ${BROKER_IP}, peekaboo-mqtt, localhost)..."
openssl genrsa -out "${CERT_DIR}/server.key" 2048

SAN="subjectAltName=IP:${BROKER_IP},IP:127.0.0.1,DNS:peekaboo-mqtt,DNS:localhost"
openssl req -new -key "${CERT_DIR}/server.key" \
    -out "${CERT_DIR}/server.csr" \
    -subj "/O=Peekaboo/CN=peekaboo-mqtt"

openssl x509 -req -days "${DAYS}" \
    -in "${CERT_DIR}/server.csr" \
    -CA "${CERT_DIR}/ca.crt" -CAkey "${CERT_DIR}/ca.key" -CAcreateserial \
    -out "${CERT_DIR}/server.crt" \
    -extfile <(printf "%s\n" "${SAN}")

rm -f "${CERT_DIR}/server.csr"

# Mosquitto runs as uid 1883 inside the eclipse-mosquitto image and must read the key.
chmod 640 "${CERT_DIR}/server.key" "${CERT_DIR}/ca.key" 2>/dev/null || true
chmod 644 "${CERT_DIR}/server.crt" "${CERT_DIR}/ca.crt"

cp "${CERT_DIR}/ca.crt" "${CAM_CERT_DIR}/mqtt_ca.pem"

echo
echo "Done. Broker certs in ${CERT_DIR}, CA for firmware in ${CAM_CERT_DIR}/mqtt_ca.pem"
echo "Broker SAN bound to IP ${BROKER_IP} — re-run with a different IP if the broker moves."
