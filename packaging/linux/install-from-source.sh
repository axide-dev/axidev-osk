#!/usr/bin/env bash
# Axidev OSK system-wide source installer for Linux.
#
# Run this from a checked-out repository to install the current source tree
# under /opt/axidev-osk without downloading a release bundle.

set -euo pipefail

readonly INSTALL_PREFIX="/opt/axidev-osk"
readonly STAGING_DIR="/opt/axidev-osk.new"
readonly BACKUP_DIR="/opt/axidev-osk.old"
readonly LAUNCHER_PATH="/usr/local/bin/axidev-osk"
readonly UDEV_RULE_PATH="/etc/udev/rules.d/70-axidev-io-uinput.rules"
readonly UDEV_RULE_CONTENTS='KERNEL=="uinput", MODE="0660", GROUP="uinput", OPTIONS+="static_node=uinput"'

log()  { printf '[install-from-source] %s\n' "$*"; }
warn() { printf '[install-from-source] WARNING: %s\n' "$*" >&2; }
die()  { printf '[install-from-source] ERROR: %s\n' "$*" >&2; exit 1; }

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log "Re-executing with sudo..."
        exec sudo -E -- "$0" "$@"
    fi
}

require_command() {
    local cmd="$1"
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        die "Required command not found: ${cmd}"
    fi
}

require_commands() {
    require_command python3
    require_command install
    require_command udevadm
    require_command groupadd
    require_command usermod
    require_command getent
    require_command stat
    require_command tar
}

resolve_target_user() {
    if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
        printf '%s' "${SUDO_USER}"
    fi
}

resolve_source_root() {
    local script_dir
    script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    local source_root
    source_root="$(cd -- "${script_dir}/../.." && pwd)"

    [ -f "${source_root}/pyproject.toml" ] || die "Could not find pyproject.toml at ${source_root}"
    [ -d "${source_root}/vendor/axidev-io-python" ] || die "Missing vendor/axidev-io-python submodule"
    [ -f "${source_root}/packaging/linux/resources/launcher.sh" ] || die "Missing launcher template"

    printf '%s' "${source_root}"
}

stage_install() {
    local source_root="$1"

    rm -rf "${STAGING_DIR}"
    mkdir -p "${STAGING_DIR}"

    log "Copying source tree into ${STAGING_DIR}/source..."
    mkdir -p "${STAGING_DIR}/source"
    tar \
        --exclude-vcs \
        --exclude='./.venv' \
        --exclude='./build' \
        --exclude='./dist' \
        --exclude='./*.egg-info' \
        -cf - \
        -C "${source_root}" . | tar -xf - -C "${STAGING_DIR}/source"

    log "Creating virtual environment at ${STAGING_DIR}/.venv..."
    python3 -m venv --system-site-packages "${STAGING_DIR}/.venv"

    log "Installing source packages into the virtual environment..."
    "${STAGING_DIR}/.venv/bin/pip" install --quiet --upgrade pip setuptools wheel
    "${STAGING_DIR}/.venv/bin/pip" install \
        --quiet \
        --no-deps \
        "${STAGING_DIR}/source/vendor/axidev-io-python" \
        "${STAGING_DIR}/source"

    cp -a "${STAGING_DIR}/source/packaging" "${STAGING_DIR}/"

    log "Verifying the staged install can import its modules..."
    "${STAGING_DIR}/.venv/bin/python" -c "import axidev_osk, axidev_io" \
        || die "Staged install failed import smoke test"
}

swap_install() {
    if [ -d "${INSTALL_PREFIX}" ]; then
        rm -rf "${BACKUP_DIR}"
        mv "${INSTALL_PREFIX}" "${BACKUP_DIR}"
    fi
    mv "${STAGING_DIR}" "${INSTALL_PREFIX}"
    rm -rf "${BACKUP_DIR}"
}

install_launcher() {
    local source_launcher="${INSTALL_PREFIX}/packaging/linux/resources/launcher.sh"
    if [ ! -f "${source_launcher}" ]; then
        die "Launcher template missing from install: ${source_launcher}"
    fi
    install -m 0755 "${source_launcher}" "${LAUNCHER_PATH}"
    log "Installed launcher at ${LAUNCHER_PATH}"
}

ensure_uinput_group() {
    if getent group uinput >/dev/null 2>&1; then
        return 0
    fi
    log "Creating 'uinput' group..."
    groupadd --system uinput
}

ensure_udev_rule() {
    local current=""
    if [ -L "${UDEV_RULE_PATH}" ]; then
        log "Removing existing udev rule mask..."
        rm -f "${UDEV_RULE_PATH}"
    fi
    if [ -f "${UDEV_RULE_PATH}" ]; then
        current="$(cat "${UDEV_RULE_PATH}")"
    fi
    if [ "${current}" = "${UDEV_RULE_CONTENTS}" ]; then
        log "udev rule already present, skipping."
        return 1
    fi
    log "Installing udev rule at ${UDEV_RULE_PATH}..."
    printf '%s\n' "${UDEV_RULE_CONTENTS}" > "${UDEV_RULE_PATH}"
    chmod 0644 "${UDEV_RULE_PATH}"
    return 0
}

reload_udev() {
    log "Reloading udev rules..."
    udevadm control --reload-rules
    if [ -e /dev/uinput ]; then
        udevadm trigger /dev/uinput || true
    fi
}

uinput_state_correct() {
    [ -e /dev/uinput ] || return 1
    local state
    state="$(stat -c '%a %G' /dev/uinput 2>/dev/null || true)"
    [ "${state}" = "660 uinput" ]
}

ensure_uinput_node() {
    if uinput_state_correct; then
        log "/dev/uinput already configured correctly."
        return 0
    fi

    if [ ! -e /dev/uinput ]; then
        log "Loading uinput kernel module..."
        modprobe uinput || warn "Could not load 'uinput' kernel module."
    fi

    if uinput_state_correct; then
        return 0
    fi

    warn "/dev/uinput is not yet owned by group 'uinput' with mode 0660."
    warn "A reboot may be required for the new udev rule to take effect."
}

ensure_user_in_input_group() {
    local target_user="$1"
    if [ -z "${target_user}" ]; then
        warn "Cannot determine the target user; skipping 'uinput' group membership step."
        warn "Run: axidev-osk linux setup-permissions --user <username>"
        return 0
    fi

    if id -nG "${target_user}" 2>/dev/null | tr ' ' '\n' | grep -qx uinput; then
        log "User '${target_user}' is already in the 'uinput' group."
        return 0
    fi

    log "Adding user '${target_user}' to the 'uinput' group..."
    usermod -aG uinput "${target_user}"
    log "Log out and back in for the new group membership to take effect."
}

main() {
    require_root "$@"
    require_commands

    local target_user
    target_user="$(resolve_target_user)"

    local source_root
    source_root="$(resolve_source_root)"

    trap 'rm -rf "${STAGING_DIR}"' EXIT

    stage_install "${source_root}"

    log "Swapping install into place at ${INSTALL_PREFIX}..."
    swap_install

    install_launcher


    ensure_uinput_group
    if ensure_udev_rule; then
        reload_udev
    fi
    ensure_uinput_node
    ensure_user_in_input_group "${target_user}"

    log "Install complete. Run: axidev-osk"
}

main "$@"
