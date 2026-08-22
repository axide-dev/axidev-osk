#!/usr/bin/env bash
# Build the local Linux payload, then install those exact bytes system-wide.

set -euo pipefail

readonly ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly OUTPUT="${ROOT}/dist/linux-local"
readonly PAYLOAD="${OUTPUT}/axidev-osk-local.tar.gz"

python3 "${ROOT}/build.py" linux payload --output "${OUTPUT}"
tar -czf "${PAYLOAD}" -C "${OUTPUT}" axidev-osk
checksum="$(sha256sum "${PAYLOAD}" | cut -d' ' -f1)"
arguments=(
    install
    --payload "${PAYLOAD}"
    --checksum "${checksum}"
)
if [ -n "${USER:-}" ] && [ "${USER}" != root ]; then
    arguments+=(--user "${USER}")
fi
exec sudo bash "${ROOT}/packaging/linux/install.sh" "${arguments[@]}"
