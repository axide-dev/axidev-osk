#!/usr/bin/env bash
# Axidev OSK uninstaller for Linux.
#
# Wipes /opt/axidev-osk, removes the launcher in /usr/local/bin, and removes
# the udev rule (reloading udev so the rule is no longer active).
#
# Does NOT remove the user from the 'input' group; that group is shared with
# other system uses and removing membership would be too aggressive.

set -euo pipefail

readonly INSTALL_PREFIX="/opt/axidev-osk"
readonly LAUNCHER_PATH="/usr/local/bin/axidev-osk"
readonly UDEV_RULE_PATH="/etc/udev/rules.d/70-axidev-io-uinput.rules"

log()  { printf '[uninstall] %s\n' "$*"; }
warn() { printf '[uninstall] WARNING: %s\n' "$*" >&2; }

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log "Re-executing with sudo..."
        exec sudo -E -- "$0" "$@"
    fi
}

main() {
    require_root "$@"

    if [ -d "${INSTALL_PREFIX}" ]; then
        log "Removing ${INSTALL_PREFIX}..."
        rm -rf "${INSTALL_PREFIX}"
    else
        log "${INSTALL_PREFIX} not present, skipping."
    fi

    if [ -e "${LAUNCHER_PATH}" ] || [ -L "${LAUNCHER_PATH}" ]; then
        log "Removing ${LAUNCHER_PATH}..."
        rm -f "${LAUNCHER_PATH}"
    else
        log "${LAUNCHER_PATH} not present, skipping."
    fi

    if [ -f "${UDEV_RULE_PATH}" ]; then
        log "Removing ${UDEV_RULE_PATH}..."
        rm -f "${UDEV_RULE_PATH}"
        if command -v udevadm >/dev/null 2>&1; then
            log "Reloading udev rules..."
            udevadm control --reload-rules || warn "udevadm control --reload-rules failed."
            udevadm trigger /dev/uinput 2>/dev/null || true
        fi
    else
        log "${UDEV_RULE_PATH} not present, skipping."
    fi

    log "Uninstall complete."
    log "Note: your membership in the 'input' group has been left untouched."
}

main "$@"
