#!/usr/bin/env bash
# Axidev OSK lifecycle installer for the Linux /opt payload.

set -euo pipefail

readonly INSTALL_PREFIX="/opt/axidev-osk"
readonly BACKUP_PREFIX="/opt/axidev-osk.old"
readonly APP_LINK="/usr/local/bin/axidev-osk"
readonly LIFECYCLE_PATH="/usr/local/sbin/axidev-osk-install"
readonly DESKTOP_PATH="/usr/local/share/applications/axidev-osk.desktop"
readonly ICON_PATH="/usr/local/share/icons/hicolor/scalable/apps/axidev-osk.svg"
readonly LOCK_PATH="/run/lock/axidev-osk-install.lock"
readonly RELEASE_BASE_URL="https://github.com/axide-dev/axidev-osk/releases/latest/download"
readonly PAYLOAD_NAME="axidev-osk-linux-x86_64.tar.gz"
readonly INSTALLER_NAME="axidev-osk-install"

log() { printf '[axidev-osk-install] %s\n' "$*"; }
warn() { printf '[axidev-osk-install] WARNING: %s\n' "$*" >&2; }
die() { printf '[axidev-osk-install] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Usage:
  axidev-osk-install install [--payload FILE --checksum SHA256] [--user USER]
  axidev-osk-install upgrade [--user USER]
  axidev-osk-install rollback
  axidev-osk-install uninstall [--user USER] [--force]

An install without --payload downloads the latest release and verifies its checksums.
EOF
}

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        exec sudo -E -- "$0" "$@"
    fi
}

require_commands() {
    local missing=0
    local command
    for command in "$@"; do
        if ! command -v "${command}" >/dev/null 2>&1; then
            warn "Missing required command: ${command}"
            missing=1
        fi
    done
    [ "${missing}" -eq 0 ] || die "Install the missing commands and retry."
}

resolve_user() {
    local requested="$1"
    if [ -n "${requested}" ]; then
        printf '%s' "${requested}"
    elif [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
        printf '%s' "${SUDO_USER}"
    fi
}

acquire_lock() {
    mkdir -p "$(dirname "${LOCK_PATH}")"
    exec 9>"${LOCK_PATH}"
    flock -n 9 || die "Another Axidev OSK lifecycle operation is running."
}

verify_local_payload() {
    local payload="$1"
    local expected="$2"
    [ -f "${payload}" ] || die "Payload does not exist: ${payload}"
    [ -n "${expected}" ] || die "--checksum is required with --payload"
    local actual
    actual="$(sha256sum "${payload}" | cut -d' ' -f1)"
    [ "${actual}" = "${expected}" ] || die "Payload checksum mismatch."
}

manifest_checksum() {
    local manifest="$1"
    local filename="$2"
    local digest name
    while read -r digest name; do
        name="${name#\*}"
        if [ "${name}" = "${filename}" ]; then
            printf '%s' "${digest}"
            return 0
        fi
    done < "${manifest}"
    return 1
}

download_release_files() {
    local directory="$1"
    shift
    local filename
    for filename in SHA256SUMS "$@"; do
        curl --fail --location --show-error --silent \
            --output "${directory}/${filename}" \
            "${RELEASE_BASE_URL}/${filename}"
    done
    for filename in "$@"; do
        local expected
        expected="$(manifest_checksum "${directory}/SHA256SUMS" "${filename}")" \
            || die "Checksum manifest does not contain ${filename}."
        verify_local_payload "${directory}/${filename}" "${expected}"
    done
}

validate_archive_paths() {
    local payload="$1"
    local paths entries path entry
    paths="$(tar -tzf "${payload}")" || die "Cannot inspect payload archive paths."
    entries="$(tar -tvzf "${payload}")" || die "Cannot inspect payload archive members."
    while IFS= read -r path; do
        case "${path}" in
            axidev-osk|axidev-osk/*) ;;
            *) die "Payload contains an unsafe path: ${path}" ;;
        esac
        case "/${path}/" in
            */../*) die "Payload contains a parent traversal: ${path}" ;;
        esac
    done <<< "${paths}"
    while IFS= read -r entry; do
        case "${entry:0:1}" in
            -|d) ;;
            *) die "Payload contains an unsupported archive member: ${entry}" ;;
        esac
    done <<< "${entries}"
}

stage_payload() {
    local payload="$1"
    local staging
    staging="$(mktemp -d /opt/axidev-osk.new.XXXXXX)"
    trap 'rm -rf "${staging}"' EXIT
    validate_archive_paths "${payload}"
    tar -xzf "${payload}" -C "${staging}" --no-same-owner
    local root="${staging}/axidev-osk"
    [ -x "${root}/bin/axidev-osk" ] || die "Payload is missing its native launcher."
    [ -f "${root}/release.json" ] || die "Payload is missing release metadata."
    "${root}/bin/axidev-osk" --verify-runtime >&2 \
        || die "Staged payload runtime verification failed."
    trap - EXIT
    printf '%s' "${root}"
}

activate_payload() {
    local staged="$1"
    rm -rf "${BACKUP_PREFIX}"
    if [ -e "${INSTALL_PREFIX}" ]; then
        mv "${INSTALL_PREFIX}" "${BACKUP_PREFIX}"
    fi
    if ! mv "${staged}" "${INSTALL_PREFIX}"; then
        if [ -e "${BACKUP_PREFIX}" ]; then
            mv "${BACKUP_PREFIX}" "${INSTALL_PREFIX}"
        fi
        die "Could not activate the staged payload."
    fi
    rmdir "$(dirname "${staged}")" 2>/dev/null || true
}

install_shared_files() {
    ln -sfn "${INSTALL_PREFIX}/bin/axidev-osk" "${APP_LINK}"

    if ! install -Dm0644 \
        "${INSTALL_PREFIX}/share/applications/axidev-osk.desktop" \
        "${DESKTOP_PATH}"; then
        warn "Could not install the desktop entry."
    fi
    if ! install -Dm0644 \
        "${INSTALL_PREFIX}/share/icons/hicolor/scalable/apps/axidev-osk.svg" \
        "${ICON_PATH}"; then
        warn "Could not install the desktop icon."
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database /usr/local/share/applications >/dev/null 2>&1 || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q /usr/local/share/icons/hicolor >/dev/null 2>&1 || true
    fi

    [ -f "$0" ] || die "Run this installer from a downloaded file, not a pipe."
    if [ "$(readlink -f "$0")" != "${LIFECYCLE_PATH}" ]; then
        install -Dm0755 "$0" "${LIFECYCLE_PATH}"
    fi
}

setup_permissions() {
    local target_user="$1"
    if [ -z "${target_user}" ]; then
        warn "No target user was selected."
        warn "Run: axidev-osk linux setup-permissions --user <username>"
        return 0
    fi
    if ! "${APP_LINK}" linux setup-permissions --user "${target_user}"; then
        warn "The application installed, but Linux input setup failed."
        warn "Retry: axidev-osk linux setup-permissions --user ${target_user}"
    fi
}

install_action() {
    local payload="$1"
    local checksum="$2"
    local target_user="$3"
    local temp=""
    if [ -z "${payload}" ]; then
        temp="$(mktemp -d)"
        download_release_files "${temp}" "${PAYLOAD_NAME}"
        payload="${temp}/${PAYLOAD_NAME}"
        checksum="$(manifest_checksum "${temp}/SHA256SUMS" "${PAYLOAD_NAME}")"
    fi
    trap 'rm -rf "${temp:-}"' RETURN
    verify_local_payload "${payload}" "${checksum}"
    local staged
    staged="$(stage_payload "${payload}")"
    activate_payload "${staged}"
    install_shared_files
    setup_permissions "${target_user}"
    log "Install complete. Run: axidev-osk"
}

upgrade_action() {
    local target_user="$1"
    local temp
    temp="$(mktemp -d)"
    download_release_files "${temp}" "${INSTALLER_NAME}" "${PAYLOAD_NAME}"
    local checksum
    checksum="$(manifest_checksum "${temp}/SHA256SUMS" "${PAYLOAD_NAME}")"
    local arguments=(
        install
        --payload "${temp}/${PAYLOAD_NAME}"
        --checksum "${checksum}"
    )
    if [ -n "${target_user}" ]; then
        arguments+=(--user "${target_user}")
    fi
    flock -u 9
    local status=0
    bash "${temp}/${INSTALLER_NAME}" "${arguments[@]}" || status=$?
    rm -rf "${temp}"
    return "${status}"
}

rollback_action() {
    [ -d "${BACKUP_PREFIX}" ] || die "No retained payload is available."
    [ -d "${INSTALL_PREFIX}" ] || die "The active payload is missing."
    "${BACKUP_PREFIX}/bin/axidev-osk" --verify-runtime \
        || die "The retained payload failed runtime verification."
    local temporary="/opt/axidev-osk.rollback.$$"
    [ ! -e "${temporary}" ] || die "Rollback temporary path already exists."
    mv "${INSTALL_PREFIX}" "${temporary}"
    if ! mv "${BACKUP_PREFIX}" "${INSTALL_PREFIX}"; then
        mv "${temporary}" "${INSTALL_PREFIX}"
        die "Could not activate the retained payload."
    fi
    mv "${temporary}" "${BACKUP_PREFIX}"
    install_shared_files
    log "Rollback complete."
}

cleanup_integration() {
    local target_user="$1"
    local failed=0
    if [ -x "${INSTALL_PREFIX}/bin/axidev-osk" ]; then
        "${INSTALL_PREFIX}/bin/axidev-osk" linux remove-greeter || failed=1
        if [ -n "${target_user}" ]; then
            "${INSTALL_PREFIX}/bin/axidev-osk" linux remove-autostart --user "${target_user}" \
                || failed=1
        else
            warn "Cannot remove autostart without a target user."
            failed=1
        fi
        "${INSTALL_PREFIX}/bin/axidev-osk" linux remove-permissions || failed=1
    fi
    return "${failed}"
}

uninstall_action() {
    local target_user="$1"
    local force="$2"
    if ! cleanup_integration "${target_user}"; then
        if [ "${force}" -ne 1 ]; then
            die "Integration cleanup failed. Retry, or use uninstall --force."
        fi
        warn "Continuing after incomplete integration cleanup."
    fi
    rm -rf "${INSTALL_PREFIX}" "${BACKUP_PREFIX}"
    if [ -L "${APP_LINK}" ] && [ "$(readlink "${APP_LINK}")" = "${INSTALL_PREFIX}/bin/axidev-osk" ]; then
        rm -f "${APP_LINK}"
    fi
    rm -f "${DESKTOP_PATH}" "${ICON_PATH}"
    rm -f "${LIFECYCLE_PATH}"
    log "Uninstall complete. Shared uinput group memberships were preserved."
}

main() {
    [ "$#" -gt 0 ] || set -- install
    require_root "$@"
    local action="$1"
    shift
    case "${action}" in
        install|upgrade|rollback|uninstall) ;;
        -h|--help) usage; return 0 ;;
        *) usage >&2; die "Unknown action: ${action}" ;;
    esac

    local payload="" checksum="" requested_user="" force=0
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --payload) [ "$#" -ge 2 ] || die "--payload needs a path"; payload="$2"; shift 2 ;;
            --checksum) [ "$#" -ge 2 ] || die "--checksum needs a digest"; checksum="$2"; shift 2 ;;
            --user) [ "$#" -ge 2 ] || die "--user needs a name"; requested_user="$2"; shift 2 ;;
            --force) force=1; shift ;;
            -h|--help) usage; return 0 ;;
            *) die "Unknown argument: $1" ;;
        esac
    done

    require_commands flock install sha256sum tar
    if [ -z "${payload}" ] && { [ "${action}" = install ] || [ "${action}" = upgrade ]; }; then
        require_commands curl
    fi
    acquire_lock
    local target_user
    target_user="$(resolve_user "${requested_user}")"

    case "${action}" in
        install) install_action "${payload}" "${checksum}" "${target_user}" ;;
        upgrade) upgrade_action "${target_user}" ;;
        rollback) rollback_action ;;
        uninstall) uninstall_action "${target_user}" "${force}" ;;
    esac
}

main "$@"
