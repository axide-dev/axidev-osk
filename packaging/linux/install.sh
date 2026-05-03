#!/usr/bin/env bash
# Axidev OSK system-wide installer for Linux.
#
# Downloads the latest release bundle, installs it under /opt/axidev-osk,
# registers a launcher in /usr/local/bin, and ensures the udev rule and
# group membership required to emit input events through /dev/uinput.
#
# The install is performed atomically: if any step fails before the swap,
# the previous install is left in place untouched.

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

readonly INSTALL_PREFIX="/opt/axidev-osk"
readonly STAGING_DIR="/opt/axidev-osk.new"
readonly BACKUP_DIR="/opt/axidev-osk.old"
readonly LAUNCHER_PATH="/usr/local/bin/axidev-osk"
readonly UDEV_RULE_PATH="/etc/udev/rules.d/70-axidev-io-uinput.rules"
readonly UDEV_RULE_CONTENTS='KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"'

readonly RELEASE_BASE_URL="https://github.com/axide-dev/axidev-osk/releases/latest/download"
readonly BUNDLE_NAME="axidev-osk-linux-x86_64.tar.gz"

readonly REQUIRED_ARCH="x86_64"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log()  { printf '[install] %s\n' "$*"; }
warn() { printf '[install] WARNING: %s\n' "$*" >&2; }
die()  { printf '[install] ERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log "Re-executing with sudo..."
        exec sudo -E -- "$0" "$@"
    fi
}

require_arch() {
    local arch
    arch="$(uname -m)"
    if [ "${arch}" != "${REQUIRED_ARCH}" ]; then
        die "Unsupported architecture '${arch}'. This installer currently supports ${REQUIRED_ARCH} only."
    fi
}

require_command() {
    local cmd="$1"
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        die "Required command not found: ${cmd}"
    fi
}

require_commands() {
    require_command curl
    require_command tar
    require_command python3
    require_command install
    require_command udevadm
    require_command groupadd
    require_command usermod
    require_command getent
    require_command stat
}

resolve_target_user() {
    # When invoked through sudo, $SUDO_USER is the original user we want
    # to add to the input group. When invoked directly as root we have no
    # safe way to guess, so the group-add step is skipped with a warning.
    if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
        printf '%s' "${SUDO_USER}"
    fi
}

# ---------------------------------------------------------------------------
# Download and stage
# ---------------------------------------------------------------------------

download_bundle() {
    local dest="$1"
    local url="${RELEASE_BASE_URL}/${BUNDLE_NAME}"
    log "Downloading ${BUNDLE_NAME} from latest release..."
    if ! curl --fail --location --show-error --silent --output "${dest}" "${url}"; then
        die "Failed to download ${url}"
    fi
}

stage_install() {
    local extract_dir="$1"

    # Clean any leftovers from a previous failed run.
    rm -rf "${STAGING_DIR}"
    mkdir -p "${STAGING_DIR}"

    # The release tarball contains an axidev-osk/ directory at its root with
    # the wheels and resource files inside.
    local bundle_root="${extract_dir}/axidev-osk"
    [ -d "${bundle_root}" ] || die "Release bundle layout unexpected: ${bundle_root} not found"

    log "Creating virtual environment at ${STAGING_DIR}/.venv..."
    python3 -m venv --system-site-packages "${STAGING_DIR}/.venv"

    log "Installing wheels into the virtual environment..."
    local wheels_dir="${bundle_root}/wheels"
    [ -d "${wheels_dir}" ] || die "Release bundle missing wheels/ directory"
    [ -d "${bundle_root}/packaging" ] || die "Release bundle missing packaging/ directory"

    "${STAGING_DIR}/.venv/bin/pip" install \
        --quiet \
        --no-index \
        --no-deps \
        --find-links "${wheels_dir}" \
        axidev-io \
        axidev-osk

    cp -a "${bundle_root}/packaging" "${STAGING_DIR}/"

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

# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------

install_launcher() {
    local source_launcher="${INSTALL_PREFIX}/packaging/linux/resources/launcher.sh"
    if [ ! -f "${source_launcher}" ]; then
        die "Launcher template missing from install: ${source_launcher}"
    fi
    install -m 0755 "${source_launcher}" "${LAUNCHER_PATH}"
    log "Installed launcher at ${LAUNCHER_PATH}"
}

# ---------------------------------------------------------------------------
# udev / group setup
#
# Each step checks the desired state first and only acts if a change is
# needed. Re-running the installer on a correctly-configured system will
# touch nothing in this section.
# ---------------------------------------------------------------------------

ensure_input_group() {
    if getent group input >/dev/null 2>&1; then
        return 0
    fi
    log "Creating 'input' group..."
    groupadd input
}

ensure_udev_rule() {
    local current=""
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
    [ "${state}" = "660 input" ]
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

    warn "/dev/uinput is not yet owned by group 'input' with mode 0660."
    warn "A reboot may be required for the new udev rule to take effect."
}

ensure_user_in_input_group() {
    local target_user="$1"
    if [ -z "${target_user}" ]; then
        warn "Cannot determine the target user; skipping 'input' group membership step."
        warn "Add yourself to the 'input' group manually with: sudo usermod -aG input <username>"
        return 0
    fi

    if id -nG "${target_user}" 2>/dev/null | tr ' ' '\n' | grep -qx input; then
        log "User '${target_user}' is already in the 'input' group."
        return 0
    fi

    log "Adding user '${target_user}' to the 'input' group..."
    usermod -aG input "${target_user}"
    log "Log out and back in for the new group membership to take effect."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    require_root "$@"
    require_arch
    require_commands

    local target_user
    target_user="$(resolve_target_user)"

    local tmp_dir=""
    tmp_dir="$(mktemp -d)"
    trap 'rm -rf "${tmp_dir:-}"; rm -rf "${STAGING_DIR}"' EXIT

    local archive_path="${tmp_dir}/${BUNDLE_NAME}"
    download_bundle "${archive_path}"

    log "Extracting bundle..."
    tar -xzf "${archive_path}" -C "${tmp_dir}"

    stage_install "${tmp_dir}"

    log "Swapping install into place at ${INSTALL_PREFIX}..."
    swap_install

    install_launcher

    ensure_input_group
    if ensure_udev_rule; then
        reload_udev
    fi
    ensure_uinput_node
    ensure_user_in_input_group "${target_user}"

    log "Install complete. Run: axidev-osk"
}

main "$@"
