#!/bin/bash
# Generate self-signed certificate for command-module HTTPS
#
# Usage:
#   ./tools/gen-self-signed-cert.sh
#
# Creates:
#   - mosquitto/certs/server.key (private key)
#   - mosquitto/certs/server.crt (certificate)
#
# These are used by:
#   - docker-compose.yml: HTTPS on command-module
#   - Mosquitto broker (TLS on port 8883)
#   - Camera firmware: embedded CA cert for validation

set -e

CERT_DIR="mosquitto/certs"
VALIDITY_DAYS=3650  # 10 years

echo "🔐 Generating self-signed certificate..."

# Create directory if needed
mkdir -p "$CERT_DIR"

# Generate private key
openssl genrsa -out "$CERT_DIR/server.key" 4096

# Generate self-signed certificate
# Subject fields:
#   C = Country, ST = State, L = City, O = Organization, CN = Common Name (hostname)
openssl req -new -x509 \
  -key "$CERT_DIR/server.key" \
  -out "$CERT_DIR/server.crt" \
  -days $VALIDITY_DAYS \
  -subj "/C=US/ST=Home/L=Local/O=Peekaboo/CN=192.168.1.x"

echo "✅ Certificate created:"
echo "   - Private key: $CERT_DIR/server.key"
echo "   - Certificate: $CERT_DIR/server.crt"
echo "   - Valid for: $VALIDITY_DAYS days"

# Extract and show certificate info
echo ""
echo "📋 Certificate Info:"
openssl x509 -in "$CERT_DIR/server.crt" -text -noout | grep -E "(Subject:|Issuer:|Not Before|Not After|Public-Key)"

# Next steps
echo ""
echo "📝 Next Steps:"
echo "   1. Update docker-compose.yml to use HTTPS"
echo "   2. Copy certificate to firmware (camera/src/s3eye/ca_cert.pem)"
echo "   3. Restart services: docker-compose down && docker-compose up -d"
echo "   4. Test with curl --cacert mosquitto/certs/server.crt https://localhost:8081/health"
