#!/usr/bin/env bash
#
# Create / update the Mosquitto password file with one credential per principal.
# Each camera gets its own username (= its camera_id) so a leaked credential can
# be revoked for a single device without touching the rest of the fleet. The
# command-module gets the only account allowed to publish commands (see the ACL).
#
# Passwords are generated randomly and printed once — capture them into:
#   - camera/.env   (MQTT_PASSWORD for that board's build)
#   - .env          (MQTT_PASSWORD for the command-module)
#
# Usage:  tools/gen-mqtt-passwd.sh [principal ...]
#   Defaults to: command-module s3eye-01 s3eye-02 xiao-01 xiao-02
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASSWD_FILE="${REPO_ROOT}/mosquitto/config/passwd"

PRINCIPALS=("$@")
if [ "${#PRINCIPALS[@]}" -eq 0 ]; then
    PRINCIPALS=(command-module s3eye-01 s3eye-02 xiao-01 xiao-02)
fi

mkdir -p "$(dirname "${PASSWD_FILE}")"

if ! command -v mosquitto_passwd >/dev/null 2>&1; then
    echo "mosquitto_passwd not found on host; using the broker container instead."
    USE_CONTAINER=1
else
    USE_CONTAINER=0
fi

create_flag="-c"   # first entry creates the file; subsequent ones append
[ -f "${PASSWD_FILE}" ] && create_flag=""

echo "principal,password"
for p in "${PRINCIPALS[@]}"; do
    pw="$(openssl rand -base64 18 | tr -d '/+=' | head -c 24)"
    if [ "${USE_CONTAINER}" -eq 1 ]; then
        docker exec -i peekaboo-mqtt mosquitto_passwd ${create_flag} -b /mosquitto/config/passwd "${p}" "${pw}"
    else
        mosquitto_passwd ${create_flag} -b "${PASSWD_FILE}" "${p}" "${pw}"
    fi
    create_flag=""
    echo "${p},${pw}"
done

echo
echo "Wrote ${PASSWD_FILE}. Store the passwords above now — they are not recoverable."
