#!/usr/bin/env bash
# Compatibility entry point for source checkouts and older documentation.

set -euo pipefail

if [ -x /usr/local/sbin/axidev-osk-install ]; then
    exec /usr/local/sbin/axidev-osk-install uninstall "$@"
fi

printf 'Axidev OSK lifecycle command is not installed.\n' >&2
exit 1
