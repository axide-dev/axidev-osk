"""Fail-safe Linux login-screen integration and process supervision."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TextIO

from . import linux

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - imported by Windows unit tests
    termios = None
    tty = None


STATE_PATH = Path("/etc/axidev-osk/greeter.json")
GREETD_CONFIG_PATH = Path("/etc/greetd/config.toml")
PLASMA_SERVICE_PATH = Path("/etc/systemd/user/axidev-osk-greeter.service")
PLASMA_WANTS_PATH = Path(
    "/etc/systemd/user/plasma-login-wayland.target.wants/axidev-osk-greeter.service"
)
PLASMA_INPUT_METHOD_PATH = Path(
    "/usr/local/share/applications/axidev-osk-input-panel.desktop"
)
KWIN_CONFIG_PATH = Path("/etc/xdg/kwinrc")
PLASMA_LOCK_SCREEN_UI_PATH = Path(
    "/usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/LockScreenUi.qml"
)
PLASMA_KWIN_UNIT_PATHS = (
    Path("/usr/local/lib/systemd/user/plasma-login-kwin_wayland.service"),
    Path("/usr/lib/systemd/user/plasma-login-kwin_wayland.service"),
    Path("/lib/systemd/user/plasma-login-kwin_wayland.service"),
)
PLASMA_KWIN_DROPIN_PATH = Path(
    "/etc/systemd/user/plasma-login-kwin_wayland.service.d/50-axidev-osk.conf"
)
LIGHTDM_CONFIG_PATH = Path("/etc/lightdm/lightdm.conf.d/99-axidev-osk.conf")
LIGHTDM_WRAPPER_PATH = Path("/etc/axidev-osk/lightdm-greeter-wrapper")
GREETD_WRAPPER_PATH = Path("/etc/axidev-osk/greetd-session-wrapper")
NATIVE_SUPERVISOR_PATH = Path("/etc/axidev-osk/greeter-keyboard-supervisor")
DEFAULT_LAUNCHER_PATH = Path("/usr/local/bin/axidev-osk")
MANAGED_GREETD_COMMAND = str(GREETD_WRAPPER_PATH)
MANAGED_GREETD_COMMENT = (
    "# Managed by Axidev OSK. Run 'sudo axidev-osk linux remove-greeter' before "
    "editing. You can add it back at any time with "
    "'sudo axidev-osk linux setup-greeter --manager greetd'."
)
RETRY_DELAYS = (1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0)
HEALTHY_RUNTIME_SECONDS = 60.0
POLL_SECONDS = 0.1

PLASMA_LOCK_SCREEN_PATCH_START = "// BEGIN AXIDEV OSK MANAGED"
PLASMA_LOCK_SCREEN_PATCH_END = "// END AXIDEV OSK MANAGED"
PLASMA_LOCK_SCREEN_ROOT_PATCH_START = "// BEGIN AXIDEV OSK ROOT MANAGED"
PLASMA_LOCK_SCREEN_ROOT_PATCH_END = "// END AXIDEV OSK ROOT MANAGED"
PLASMA_LOCK_SCREEN_BUTTON_PATCH_START = "// BEGIN AXIDEV OSK BUTTON MANAGED"
PLASMA_LOCK_SCREEN_BUTTON_PATCH_END = "// END AXIDEV OSK BUTTON MANAGED"
PLASMA_LOCK_SCREEN_MIN_VERSION = (6, 7, 0)
PLASMA_LOCK_SCREEN_MAX_VERSION = (7, 0, 0)
PLASMA_LOCK_SCREEN_LEGACY_PATCH = (
    "        // BEGIN AXIDEV OSK MANAGED\n"
    "        Connections {\n"
    "            target: lockScreenRoot\n"
    "            Component.onCompleted: lockScreenRoot.uiVisible = true\n\n"
    "            function onUiVisibleChanged() {\n"
    "                if (!lockScreenRoot.uiVisible) {\n"
    "                    lockScreenRoot.uiVisible = true;\n"
    "                }\n"
    "            }\n"
    "        }\n"
    "        // END AXIDEV OSK MANAGED\n"
)
PLASMA_LOCK_SCREEN_PREVIOUS_PATCH = (
    "        // BEGIN AXIDEV OSK MANAGED\n"
    "        Connections {\n"
    "            target: lockScreenRoot\n"
    "            Component.onCompleted: Qt.callLater(function() {\n"
    "                lockScreenRoot.uiVisible = true;\n"
    "            })\n\n"
    "            function onUiVisibleChanged() {\n"
    "                if (!lockScreenRoot.uiVisible) {\n"
    "                    lockScreenRoot.uiVisible = true;\n"
    "                }\n"
    "            }\n"
    "        }\n"
    "        // END AXIDEV OSK MANAGED\n"
)
PLASMA_LOCK_SCREEN_AUTO_PATCH = (
    "        // BEGIN AXIDEV OSK MANAGED\n"
    "        Connections {\n"
    "            target: lockScreenRoot\n"
    "            Component.onCompleted: Qt.callLater(function() {\n"
    "                lockScreenRoot.uiVisible = true;\n"
    "                if (inputPanel.status === Loader.Ready && !inputPanel.keyboardActive) {\n"
    "                    mainBlock.mainPasswordBox.forceActiveFocus();\n"
    "                    inputPanel.showHide();\n"
    "                }\n"
    "            })\n\n"
    "            function onUiVisibleChanged() {\n"
    "                if (!lockScreenRoot.uiVisible) {\n"
    "                    lockScreenRoot.uiVisible = true;\n"
    "                }\n"
    "            }\n"
    "        }\n\n"
    "        Connections {\n"
    "            target: inputPanel\n\n"
    "            function onStatusChanged() {\n"
    "                if (inputPanel.status === Loader.Ready && !inputPanel.keyboardActive) {\n"
    "                    mainBlock.mainPasswordBox.forceActiveFocus();\n"
    "                    inputPanel.showHide();\n"
    "                }\n"
    "            }\n"
    "        }\n"
    "        // END AXIDEV OSK MANAGED\n"
)
PLASMA_LOCK_SCREEN_STACKED_BUTTON_PATCH = (
    "        // BEGIN AXIDEV OSK MANAGED\n"
    "        Connections {\n"
    "            target: lockScreenRoot\n"
    "            Component.onCompleted: Qt.callLater(function() {\n"
    "                lockScreenRoot.uiVisible = true;\n"
    "            })\n\n"
    "            function onUiVisibleChanged() {\n"
    "                if (!lockScreenRoot.uiVisible) {\n"
    "                    lockScreenRoot.uiVisible = true;\n"
    "                }\n"
    "            }\n"
    "        }\n\n"
    "        PlasmaComponents3.ToolButton {\n"
    "            id: axidevOskButton\n"
    "            parent: footer\n"
    "            Component.onCompleted: axidevOskButton.stackBefore(virtualKeyboardButton)\n"
    "            focusPolicy: Qt.TabFocus\n"
    "            text: \"Axidev OSK\"\n"
    "            icon.name: \"input-keyboard-virtual-on\"\n"
    "            visible: inputPanel.status === Loader.Ready\n"
    "            Layout.fillHeight: true\n\n"
    "            onClicked: {\n"
    "                mainBlock.mainPasswordBox.forceActiveFocus();\n"
    "                if (inputPanel.keyboardActive) {\n"
    "                    inputPanel.showHide();\n"
    "                }\n"
    "                Qt.callLater(function() {\n"
    "                    mainBlock.mainPasswordBox.forceActiveFocus();\n"
    "                    if (!inputPanel.keyboardActive) {\n"
    "                        inputPanel.showHide();\n"
    "                    }\n"
    "                })\n"
    "            }\n"
    "        }\n"
    "        // END AXIDEV OSK MANAGED\n"
)
PLASMA_LOCK_SCREEN_UNQUALIFIED_BUTTON_PATCH = PLASMA_LOCK_SCREEN_STACKED_BUTTON_PATCH.replace(
    "            Component.onCompleted: axidevOskButton.stackBefore(virtualKeyboardButton)\n",
    "            Component.onCompleted: stackBefore(virtualKeyboardButton)\n",
    1,
)
PLASMA_LOCK_SCREEN_UNORDERED_BUTTON_PATCH = PLASMA_LOCK_SCREEN_STACKED_BUTTON_PATCH.replace(
    "            id: axidevOskButton\n"
    "            parent: footer\n"
    "            Component.onCompleted: axidevOskButton.stackBefore(virtualKeyboardButton)\n",
    "            parent: footer\n",
    1,
)
PLASMA_LOCK_SCREEN_ROOT_PATCH = (
    "        // BEGIN AXIDEV OSK ROOT MANAGED\n"
    "        Connections {\n"
    "            target: lockScreenRoot\n"
    "            Component.onCompleted: Qt.callLater(function() {\n"
    "                lockScreenRoot.uiVisible = true;\n"
    "            })\n\n"
    "            function onUiVisibleChanged() {\n"
    "                if (!lockScreenRoot.uiVisible) {\n"
    "                    lockScreenRoot.uiVisible = true;\n"
    "                }\n"
    "            }\n"
    "        }\n"
    "        // END AXIDEV OSK ROOT MANAGED\n"
)
PLASMA_LOCK_SCREEN_BUTTON_PATCH = (
    "            // BEGIN AXIDEV OSK BUTTON MANAGED\n"
    "            PlasmaComponents3.ToolButton {\n"
    "                id: axidevOskButton\n\n"
    "                focusPolicy: Qt.TabFocus\n"
    "                text: \"Axidev OSK\"\n"
    "                icon.name: \"input-keyboard-virtual-on\"\n"
    "                visible: inputPanel.status === Loader.Ready\n"
    "                Layout.fillHeight: true\n\n"
    "                onClicked: {\n"
    "                    mainBlock.mainPasswordBox.forceActiveFocus();\n"
    "                    if (inputPanel.keyboardActive) {\n"
    "                        inputPanel.showHide();\n"
    "                    }\n"
    "                    Qt.callLater(function() {\n"
    "                        mainBlock.mainPasswordBox.forceActiveFocus();\n"
    "                        if (!inputPanel.keyboardActive) {\n"
    "                            inputPanel.showHide();\n"
    "                        }\n"
    "                    })\n"
    "                }\n"
    "            }\n"
    "            // END AXIDEV OSK BUTTON MANAGED\n\n"
)
PLASMA_LOCK_SCREEN_PREVIOUS_BUTTON_PATCH = PLASMA_LOCK_SCREEN_BUTTON_PATCH.replace(
    "                    if (inputPanel.keyboardActive) {\n"
    "                        inputPanel.showHide();\n"
    "                    }\n"
    "                    Qt.callLater(function() {\n"
    "                        mainBlock.mainPasswordBox.forceActiveFocus();\n"
    "                        if (!inputPanel.keyboardActive) {\n"
    "                            inputPanel.showHide();\n"
    "                        }\n"
    "                    })\n",
    "                    inputPanel.showHide();\n",
    1,
)

@dataclass(frozen=True)
class GreetdConfig:
    """The exact greetd command assignment that setup may replace."""

    account: str
    command: str
    line_index: int
    original_line: str
    newline: str


class _FileTransaction:
    """Restore touched files when a multi-file integration write fails."""

    def __init__(self) -> None:
        self._originals: list[tuple[Path, str, bytes | str | None, int | None]] = []

    def _remember(self, path: Path) -> None:
        if any(item[0] == path for item in self._originals):
            return
        if path.is_symlink():
            self._originals.append((path, "symlink", os.readlink(path), None))
        elif path.exists():
            self._originals.append((path, "file", path.read_bytes(), path.stat().st_mode & 0o777))
        else:
            self._originals.append((path, "missing", None, None))

    def write(self, path: Path, contents: str, mode: int = 0o644) -> None:
        self._remember(path)
        linux._write_atomic(path, contents, mode)

    def symlink(self, path: Path, target: Path) -> None:
        self._remember(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
        path.symlink_to(target)

    def remove(self, path: Path) -> None:
        self._remember(path)
        path.unlink(missing_ok=True)

    def rollback(self) -> None:
        for path, kind, value, mode in reversed(self._originals):
            try:
                if path.exists() or path.is_symlink():
                    path.unlink()
                if kind == "file":
                    assert isinstance(value, bytes)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(value)
                    assert mode is not None
                    path.chmod(mode)
                elif kind == "symlink":
                    assert isinstance(value, str)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.symlink_to(value)
            except OSError:
                pass


@dataclass(frozen=True)
class _ManagerAdapter:
    label: str
    unit: str
    prepare: Callable[[Path], tuple[linux.Account, dict[str, Any]]]
    install: Callable[[_FileTransaction, Path, dict[str, Any]], dict[str, Any]]
    checks: Callable[[Path, dict[str, Any]], list[tuple[str, bool]]]
    remove: Callable[[Path, dict[str, Any]], None]


def register_runtime_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register internal commands used by display-manager startup hooks."""

    keyboard = commands.add_parser("run-greeter-keyboard")
    keyboard.add_argument("--manager", choices=tuple(_MANAGER_ADAPTERS), required=True)
    keyboard.add_argument("--parent-pid", type=int)
    keyboard.add_argument("--discover-display", action="store_true")
    keyboard.set_defaults(handler=run_runtime_command, runtime="keyboard")


def run_setup_command(namespace: argparse.Namespace, argv: list[str]) -> int:
    """Run setup, status, or removal with root escalation where required."""

    if namespace.action in {"setup", "remove"} and not linux._is_root():
        return linux._sudo_reexec(argv, None)
    if namespace.action == "setup":
        return _setup(namespace.manager)
    if namespace.action == "status":
        return _status()
    return _remove()


def run_runtime_command(namespace: argparse.Namespace, argv: list[str]) -> int:
    """Run an internal greeter process without administrative dispatch."""

    del argv
    try:
        if namespace.parent_pid is not None:
            environment = None if namespace.discover_display else os.environ.copy()
            return _run_attached_supervisor(namespace.manager, namespace.parent_pid, environment)
        if namespace.discover_display:
            raise linux.LinuxSetupError("--discover-display requires --parent-pid")
        return _run_keyboard_supervisor(namespace.manager, os.environ.copy())
    except linux.LinuxSetupError as exc:
        _log_error("runtime", "startup", str(exc))
        return 1


def _setup(requested_manager: str | None) -> int:
    existing = _load_state(required=False)
    legacy_plasma = existing is not None and _is_legacy_plasma_state(existing)
    if existing is not None and not legacy_plasma:
        if requested_manager is not None and existing["manager"] != requested_manager:
            raise linux.LinuxSetupError(
                f"greeter integration already manages {existing['manager']}; remove it first"
            )
        if existing["manager"] == "plasma-login":
            _require_supported_plasma_lock_screen_version()
        repaired_lock_screen = _repair_plasma_lock_screen_patch(existing)
        if repaired_lock_screen:
            print("Restored the managed Plasma lock-screen visibility block.")
        if _status_state(existing) == 0:
            print(f"Greeter startup is already configured for {existing['manager']}.")
            return 0
        raise linux.LinuxSetupError("managed greeter state is incomplete; remove it before setup")

    if legacy_plasma:
        assert existing is not None
        if requested_manager is not None and requested_manager != "plasma-login":
            raise linux.LinuxSetupError(
                "greeter integration already manages plasma-login; remove it first"
            )
        manager = "plasma-login"
    else:
        manager = requested_manager or _select_manager(_installed_managers())
    adapter = _manager_adapter(manager)
    if not _manager_installed(adapter):
        raise linux.LinuxSetupError(f"{adapter.label} is not installed")

    launcher = _installed_launcher()
    account, details = adapter.prepare(launcher)
    details["legacy_plasma"] = legacy_plasma

    linux._setup_permissions(account)
    _install_manager(manager, adapter, account, launcher, details)
    print(
        f"Greeter startup is configured for {adapter.label}. "
        "Reboot or restart the display manager to activate it."
    )
    return 0


def _status() -> int:
    state = _load_state(required=True)
    assert state is not None
    return _status_state(state)


def _status_state(state: dict[str, Any]) -> int:
    manager = _state_manager(state)
    adapter = _manager_adapter(manager)
    account = linux._resolve_account(_state_string(state, "account"), require_home=False)
    checks = [("manager installed", _manager_installed(adapter))]
    checks.extend(adapter.checks(_runtime_launcher(), state))
    for label, passed in checks:
        print(f"{'ok' if passed else 'missing'}: {label}")
    permission_status = linux._status_permissions(account)
    return 0 if permission_status == 0 and all(passed for _, passed in checks) else 1


def _repair_plasma_lock_screen_patch(state: dict[str, Any]) -> bool:
    """Restore a missing managed QML block independently of other status checks."""

    if _state_manager(state) != "plasma-login":
        return False
    if _plasma_lock_screen_patch_is_current(linux._read_text(PLASMA_LOCK_SCREEN_UI_PATH)):
        return False
    lock_screen_ui = linux._read_text(PLASMA_LOCK_SCREEN_UI_PATH)
    if lock_screen_ui is None:
        raise linux.LinuxSetupError(
            f"Plasma lock-screen QML does not exist: {PLASMA_LOCK_SCREEN_UI_PATH}"
        )
    _require_writable_regular_file(PLASMA_LOCK_SCREEN_UI_PATH)
    managed = _plasma_lock_screen_ui_text(lock_screen_ui)
    linux._write_atomic(
        PLASMA_LOCK_SCREEN_UI_PATH,
        managed,
        PLASMA_LOCK_SCREEN_UI_PATH.stat().st_mode & 0o777,
    )
    return True


def _remove() -> int:
    state = _load_state(required=False)
    if state is None:
        print("Greeter startup is not configured.")
        return 0
    manager = _state_manager(state)
    adapter = _manager_adapter(manager)
    adapter.remove(_runtime_launcher(), state)
    try:
        STATE_PATH.unlink()
        STATE_PATH.parent.rmdir()
    except FileNotFoundError:
        pass
    except OSError as exc:
        if STATE_PATH.exists():
            raise linux.LinuxSetupError(f"cannot remove {STATE_PATH}: {exc}") from exc
    print(
        f"Greeter startup is removed for {adapter.label}. "
        "Shared uinput group memberships were preserved."
    )
    return 0


def _installed_managers() -> list[str]:
    managers = [
        manager
        for manager, adapter in _MANAGER_ADAPTERS.items()
        if _manager_installed(adapter)
    ]
    if not managers:
        raise linux.LinuxSetupError("no supported display manager is installed")
    return managers


def _manager_installed(adapter: _ManagerAdapter) -> bool:
    systemctl = shutil.which("systemctl")
    if systemctl is None:
        return False
    try:
        completed = subprocess.run(
            [systemctl, "show", "--property=LoadState", "--value", adapter.unit],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return completed.returncode == 0 and completed.stdout.strip() == "loaded"


def _select_manager(
    managers: list[str],
    *,
    key_reader: Callable[[], str] | None = None,
    output: TextIO | None = None,
) -> str:
    output = output or sys.stdout
    if key_reader is None:
        if not sys.stdin.isatty() or not output.isatty():
            raise linux.LinuxSetupError("--manager is required without an interactive terminal")
        key_reader = _terminal_key_reader

    selected = 0
    output.write("Select the login manager to configure:\n")
    output.flush()
    while True:
        for index, manager in enumerate(managers):
            marker = ">" if index == selected else " "
            output.write(f"\r\x1b[2K{marker} {_manager_adapter(manager).label}\n")
        output.write(f"\x1b[{len(managers)}A")
        output.flush()
        key = key_reader()
        if key == "up":
            selected = (selected - 1) % len(managers)
        elif key == "down":
            selected = (selected + 1) % len(managers)
        elif key == "enter":
            output.write(f"\x1b[{len(managers)}B")
            output.flush()
            return managers[selected]
        elif key in {"escape", "interrupt"}:
            output.write(f"\x1b[{len(managers)}B")
            output.flush()
            raise linux.LinuxSetupError("greeter setup was cancelled")


def _terminal_key_reader() -> str:
    if termios is None or tty is None:
        raise linux.LinuxSetupError("interactive selection is unavailable in this terminal")
    descriptor = sys.stdin.fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setraw(descriptor)
        first = os.read(descriptor, 1)
        if first in {b"\r", b"\n"}:
            return "enter"
        if first == b"\x03":
            return "interrupt"
        if first != b"\x1b":
            return "unknown"
        second = os.read(descriptor, 1)
        if second != b"[":
            return "escape"
        third = os.read(descriptor, 1)
        return {b"A": "up", b"B": "down"}.get(third, "unknown")
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def _installed_launcher() -> Path:
    launcher = shutil.which("axidev-osk")
    path = Path(launcher).resolve() if launcher else DEFAULT_LAUNCHER_PATH
    if not path.is_file():
        raise linux.LinuxSetupError("axidev-osk must be installed before greeter setup")
    return path


def _prepare_plasma(launcher: Path) -> tuple[linux.Account, dict[str, Any]]:
    _require_supported_plasma_lock_screen_version()
    account = linux._resolve_account("plasmalogin", require_home=False)
    original_kwinrc = linux._read_text(KWIN_CONFIG_PATH)
    lock_screen_ui = linux._read_text(PLASMA_LOCK_SCREEN_UI_PATH)
    if lock_screen_ui is None:
        raise linux.LinuxSetupError(
            f"Plasma lock-screen QML does not exist: {PLASMA_LOCK_SCREEN_UI_PATH}"
        )
    managed_kwinrc = _plasma_kwin_config_text(original_kwinrc)
    managed_lock_screen_ui = _plasma_lock_screen_ui_text(lock_screen_ui)
    _require_compatible_file(PLASMA_INPUT_METHOD_PATH, _plasma_input_method_text(launcher))
    _require_compatible_file(PLASMA_KWIN_DROPIN_PATH, _plasma_kwin_dropin_text(launcher))
    if PLASMA_INPUT_METHOD_PATH.exists() or PLASMA_INPUT_METHOD_PATH.is_symlink():
        _require_writable_regular_file(PLASMA_INPUT_METHOD_PATH)
    if original_kwinrc is not None:
        _require_writable_regular_file(KWIN_CONFIG_PATH)
    _require_writable_regular_file(PLASMA_LOCK_SCREEN_UI_PATH)
    return account, {
        "kwinrc_existed": original_kwinrc is not None,
        "kwinrc_mode": KWIN_CONFIG_PATH.stat().st_mode & 0o777 if original_kwinrc is not None else 0o644,
        "original_kwinrc": original_kwinrc or "",
        "managed_kwinrc": managed_kwinrc,
        "lock_screen_ui_mode": PLASMA_LOCK_SCREEN_UI_PATH.stat().st_mode & 0o777,
        "managed_lock_screen_ui": managed_lock_screen_ui,
    }


def _prepare_lightdm(launcher: Path) -> tuple[linux.Account, dict[str, Any]]:
    account = linux._resolve_account("lightdm", require_home=False)
    _require_compatible_file(LIGHTDM_WRAPPER_PATH, _lightdm_wrapper_text(launcher))
    _require_compatible_file(LIGHTDM_CONFIG_PATH, _lightdm_config_text())
    effective = _lightdm_effective_wrapper()
    if effective not in {None, str(LIGHTDM_WRAPPER_PATH)}:
        raise linux.LinuxSetupError(f"LightDM already uses a greeter wrapper: {effective}")
    return account, {}


def _prepare_greetd(launcher: Path) -> tuple[linux.Account, dict[str, Any]]:
    config_text = linux._read_text(GREETD_CONFIG_PATH)
    if config_text is None:
        raise linux.LinuxSetupError(f"greetd config does not exist: {GREETD_CONFIG_PATH}")
    parsed = _parse_greetd_config(config_text)
    if parsed.command == MANAGED_GREETD_COMMAND:
        raise linux.LinuxSetupError("greetd already contains an untracked Axidev wrapper")
    account = linux._resolve_account(parsed.account, require_home=False)
    lines = config_text.splitlines(keepends=True)
    indentation = re.match(r"^\s*", parsed.original_line).group(0)  # type: ignore[union-attr]
    comment_newline = parsed.newline or "\n"
    lines[parsed.line_index] = f"{indentation}{MANAGED_GREETD_COMMENT}{comment_newline}"
    lines.insert(
        parsed.line_index + 1,
        f"{indentation}command = {json.dumps(MANAGED_GREETD_COMMAND)}{parsed.newline}",
    )
    return account, {
        "config_text": config_text,
        "managed_text": "".join(lines),
        "original_command": parsed.command,
        "original_line": parsed.original_line,
        "wrapper_text": _greetd_wrapper_text(launcher, parsed.command),
    }


def _install_manager(
    manager: str,
    adapter: _ManagerAdapter,
    account: linux.Account,
    launcher: Path,
    details: dict[str, Any],
) -> None:
    state: dict[str, Any] = {"schema": 1, "manager": manager, "account": account.name}
    transaction = _FileTransaction()
    try:
        state.update(adapter.install(transaction, launcher, details))
        transaction.write(STATE_PATH, json.dumps(state, indent=2, sort_keys=True) + "\n", 0o644)
    except Exception:
        transaction.rollback()
        raise


def _install_plasma(
    transaction: _FileTransaction,
    launcher: Path,
    details: dict[str, Any],
) -> dict[str, Any]:
    if bool(details.get("legacy_plasma")):
        _require_removable_symlink(PLASMA_WANTS_PATH, PLASMA_SERVICE_PATH)
        _require_removable_file(PLASMA_SERVICE_PATH, _plasma_service_text())
        _require_removable_file(NATIVE_SUPERVISOR_PATH, _native_supervisor_text(launcher))
        transaction.remove(PLASMA_WANTS_PATH)
        transaction.remove(PLASMA_SERVICE_PATH)
        transaction.remove(NATIVE_SUPERVISOR_PATH)
    transaction.write(PLASMA_INPUT_METHOD_PATH, _plasma_input_method_text(launcher))
    transaction.write(PLASMA_KWIN_DROPIN_PATH, _plasma_kwin_dropin_text(launcher))
    transaction.write(KWIN_CONFIG_PATH, _state_string(details, "managed_kwinrc"))
    transaction.write(
        PLASMA_LOCK_SCREEN_UI_PATH,
        _state_string(details, "managed_lock_screen_ui"),
        int(details["lock_screen_ui_mode"]),
    )
    return {
        "kwinrc_existed": bool(details["kwinrc_existed"]),
        "kwinrc_mode": int(details["kwinrc_mode"]),
        "original_kwinrc": _state_text(details, "original_kwinrc"),
    }


def _install_lightdm(
    transaction: _FileTransaction,
    launcher: Path,
    details: dict[str, Any],
) -> dict[str, Any]:
    del details
    transaction.write(LIGHTDM_WRAPPER_PATH, _lightdm_wrapper_text(launcher), 0o755)
    transaction.write(LIGHTDM_CONFIG_PATH, _lightdm_config_text())
    if _lightdm_effective_wrapper() != str(LIGHTDM_WRAPPER_PATH):
        raise linux.LinuxSetupError("LightDM did not select the Axidev greeter wrapper")
    return {}


def _install_greetd(
    transaction: _FileTransaction,
    launcher: Path,
    details: dict[str, Any],
) -> dict[str, Any]:
    del launcher
    transaction.write(GREETD_WRAPPER_PATH, _state_string(details, "wrapper_text"), 0o755)
    transaction.write(GREETD_CONFIG_PATH, _state_string(details, "managed_text"))
    return {
        "original_command": _state_string(details, "original_command"),
        "original_line": _state_string(details, "original_line"),
    }


def _check_plasma(launcher: Path, state: dict[str, Any]) -> list[tuple[str, bool]]:
    version_check = (
        "Plasma version >=6.7.0,<7.0.0",
        _plasma_lock_screen_version_supported(),
    )
    if _is_legacy_plasma_state(state):
        service_ok = linux._read_text(PLASMA_SERVICE_PATH) == _plasma_service_text()
        link_ok = (
            PLASMA_WANTS_PATH.is_symlink()
            and PLASMA_WANTS_PATH.resolve() == PLASMA_SERVICE_PATH.resolve()
        )
        return [
            version_check,
            (
                str(NATIVE_SUPERVISOR_PATH),
                linux._read_text(NATIVE_SUPERVISOR_PATH) == _native_supervisor_text(launcher),
            ),
            (str(PLASMA_SERVICE_PATH), service_ok),
            (str(PLASMA_WANTS_PATH), link_ok),
        ]
    original_kwinrc = _state_text(state, "original_kwinrc")
    return [
        version_check,
        (
            str(PLASMA_INPUT_METHOD_PATH),
            linux._read_text(PLASMA_INPUT_METHOD_PATH) == _plasma_input_method_text(launcher),
        ),
        (
            str(PLASMA_KWIN_DROPIN_PATH),
            linux._read_text(PLASMA_KWIN_DROPIN_PATH) == _plasma_kwin_dropin_text(launcher),
        ),
        (
            str(KWIN_CONFIG_PATH),
            linux._read_text(KWIN_CONFIG_PATH) == _plasma_kwin_config_text(original_kwinrc or None),
        ),
        (
            str(PLASMA_LOCK_SCREEN_UI_PATH),
            _plasma_lock_screen_patch_is_current(linux._read_text(PLASMA_LOCK_SCREEN_UI_PATH)),
        ),
    ]


def _check_lightdm(launcher: Path, state: dict[str, Any]) -> list[tuple[str, bool]]:
    del state
    return [
        (str(LIGHTDM_WRAPPER_PATH), linux._read_text(LIGHTDM_WRAPPER_PATH) == _lightdm_wrapper_text(launcher)),
        (str(LIGHTDM_CONFIG_PATH), linux._read_text(LIGHTDM_CONFIG_PATH) == _lightdm_config_text()),
        ("effective LightDM wrapper", _lightdm_effective_wrapper() == str(LIGHTDM_WRAPPER_PATH)),
    ]


def _check_greetd(launcher: Path, state: dict[str, Any]) -> list[tuple[str, bool]]:
    config = linux._read_text(GREETD_CONFIG_PATH)
    managed = False
    if config is not None:
        try:
            managed = _parse_greetd_config(config).command == MANAGED_GREETD_COMMAND
        except linux.LinuxSetupError:
            managed = False
    original = state.get("original_command")
    wrapper_ok = isinstance(original, str) and linux._read_text(GREETD_WRAPPER_PATH) == _greetd_wrapper_text(launcher, original)
    return [
        (str(GREETD_CONFIG_PATH), managed),
        (str(GREETD_WRAPPER_PATH), wrapper_ok),
        ("saved greetd command", bool(original)),
    ]


def _remove_plasma(launcher: Path, state: dict[str, Any]) -> None:
    if _is_legacy_plasma_state(state):
        _require_removable_symlink(PLASMA_WANTS_PATH, PLASMA_SERVICE_PATH)
        _require_removable_file(PLASMA_SERVICE_PATH, _plasma_service_text())
        _require_removable_file(NATIVE_SUPERVISOR_PATH, _native_supervisor_text(launcher))
        _remove_owned_symlink(PLASMA_WANTS_PATH, PLASMA_SERVICE_PATH)
        linux._remove_owned_file(PLASMA_SERVICE_PATH, _plasma_service_text())
        linux._remove_owned_file(NATIVE_SUPERVISOR_PATH, _native_supervisor_text(launcher))
        return
    original_kwinrc = _state_text(state, "original_kwinrc")
    managed_kwinrc = _plasma_kwin_config_text(original_kwinrc or None)
    _require_removable_file(PLASMA_INPUT_METHOD_PATH, _plasma_input_method_text(launcher))
    _require_removable_file(PLASMA_KWIN_DROPIN_PATH, _plasma_kwin_dropin_text(launcher))
    _require_removable_file(KWIN_CONFIG_PATH, managed_kwinrc)
    lock_screen_ui = linux._read_text(PLASMA_LOCK_SCREEN_UI_PATH)
    unmanaged_lock_screen_ui = (
        _plasma_lock_screen_ui_without_patch(lock_screen_ui)
        if lock_screen_ui is not None
        else None
    )
    linux._remove_owned_file(PLASMA_INPUT_METHOD_PATH, _plasma_input_method_text(launcher))
    linux._remove_owned_file(PLASMA_KWIN_DROPIN_PATH, _plasma_kwin_dropin_text(launcher))
    try:
        PLASMA_KWIN_DROPIN_PATH.parent.rmdir()
    except OSError:
        pass
    if bool(state.get("kwinrc_existed")):
        linux._write_atomic(KWIN_CONFIG_PATH, original_kwinrc, _state_mode(state, "kwinrc_mode"))
    else:
        linux._remove_owned_file(KWIN_CONFIG_PATH, managed_kwinrc)
    if lock_screen_ui is not None and unmanaged_lock_screen_ui != lock_screen_ui:
        linux._write_atomic(
            PLASMA_LOCK_SCREEN_UI_PATH,
            unmanaged_lock_screen_ui,
            PLASMA_LOCK_SCREEN_UI_PATH.stat().st_mode & 0o777,
        )


def _remove_lightdm(launcher: Path, state: dict[str, Any]) -> None:
    del state
    _require_removable_file(LIGHTDM_CONFIG_PATH, _lightdm_config_text())
    _require_removable_file(LIGHTDM_WRAPPER_PATH, _lightdm_wrapper_text(launcher))
    linux._remove_owned_file(LIGHTDM_CONFIG_PATH, _lightdm_config_text())
    linux._remove_owned_file(LIGHTDM_WRAPPER_PATH, _lightdm_wrapper_text(launcher))


def _remove_greetd(launcher: Path, state: dict[str, Any]) -> None:
    config = linux._read_text(GREETD_CONFIG_PATH)
    if config is None:
        raise linux.LinuxSetupError(f"greetd config does not exist: {GREETD_CONFIG_PATH}")
    parsed = _parse_greetd_config(config)
    if parsed.command != MANAGED_GREETD_COMMAND:
        raise linux.LinuxSetupError("refusing to replace a changed greetd command")
    original_line = _state_string(state, "original_line")
    lines = config.splitlines(keepends=True)
    indentation = re.match(r"^\s*", parsed.original_line).group(0)  # type: ignore[union-attr]
    comment_newline = parsed.newline or "\n"
    expected_comment = f"{indentation}{MANAGED_GREETD_COMMENT}{comment_newline}"
    if parsed.line_index == 0 or lines[parsed.line_index - 1] != expected_comment:
        raise linux.LinuxSetupError("refusing to remove a changed greetd management comment")
    expected_wrapper = _greetd_wrapper_text(
        launcher, _state_string(state, "original_command")
    )
    _require_removable_file(GREETD_WRAPPER_PATH, expected_wrapper)
    lines[parsed.line_index - 1 : parsed.line_index + 1] = [original_line]
    linux._write_atomic(GREETD_CONFIG_PATH, "".join(lines), 0o644)
    linux._remove_owned_file(GREETD_WRAPPER_PATH, expected_wrapper)


_MANAGER_ADAPTERS = {
    "plasma-login": _ManagerAdapter(
        "Plasma Login Manager",
        "plasmalogin.service",
        _prepare_plasma,
        _install_plasma,
        _check_plasma,
        _remove_plasma,
    ),
    "greetd": _ManagerAdapter(
        "greetd",
        "greetd.service",
        _prepare_greetd,
        _install_greetd,
        _check_greetd,
        _remove_greetd,
    ),
    "lightdm": _ManagerAdapter(
        "LightDM",
        "lightdm.service",
        _prepare_lightdm,
        _install_lightdm,
        _check_lightdm,
        _remove_lightdm,
    ),
}


def _manager_adapter(manager: str) -> _ManagerAdapter:
    try:
        return _MANAGER_ADAPTERS[manager]
    except KeyError as exc:
        raise linux.LinuxSetupError(f"unsupported managed greeter: {manager}") from exc


def _plasma_service_text() -> str:
    return (
        "[Unit]\n"
        "Description=Axidev OSK login-screen keyboard\n"
        "PartOf=plasma-login-wayland.target\n"
        "After=plasma-login-kwin_wayland.service\n\n"
        "[Service]\n"
        f"ExecStart={NATIVE_SUPERVISOR_PATH} plasma-login\n"
        "Slice=session.slice\n"
    )


def _plasma_input_method_text(launcher: Path) -> str:
    return (
        "[Desktop Entry]\n"
        "Name=Axidev OSK\n"
        f"Exec={launcher}\n"
        "Type=Application\n"
        "X-KDE-Wayland-VirtualKeyboard=true\n"
        "NoDisplay=true\n"
        "Icon=axidev-osk\n"
    )


def _plasma_kwin_dropin_text(launcher: Path) -> str:
    unit_path = next((path for path in PLASMA_KWIN_UNIT_PATHS if path.is_file()), None)
    if unit_path is None:
        raise linux.LinuxSetupError("Plasma Login Manager KWin service is missing")
    unit_text = linux._read_text(unit_path)
    assert unit_text is not None
    command = _systemd_service_command(unit_text, "ExecStart")
    try:
        arguments = shlex.split(command)
    except ValueError as exc:
        raise linux.LinuxSetupError("Plasma Login Manager KWin command is invalid") from exc
    try:
        input_method_index = arguments.index("--inputmethod")
    except ValueError as exc:
        raise linux.LinuxSetupError(
            "Plasma Login Manager KWin command has no --inputmethod option"
        ) from exc
    if input_method_index + 1 >= len(arguments):
        raise linux.LinuxSetupError("Plasma Login Manager KWin input method is missing")
    arguments[input_method_index + 1] = str(launcher)
    return (
        "[Service]\n"
        "Environment=AXIDEV_OSK_GREETER=1\n"
        "ExecStart=\n"
        f"ExecStart={shlex.join(arguments)}\n"
    )


def _systemd_service_command(unit_text: str, key: str) -> str:
    section = ""
    matches: list[str] = []
    for raw_line in unit_text.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section == "Service" and line.startswith(f"{key}="):
            value = line.split("=", 1)[1].strip()
            if value:
                matches.append(value)
    if len(matches) != 1:
        raise linux.LinuxSetupError(
            f"Plasma Login Manager KWin service requires exactly one {key} command"
        )
    return matches[0]


def _plasma_kwin_config_text(original: str | None) -> str:
    lines = [] if original is None else original.splitlines(keepends=True)
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += "\n"

    section_start = next(
        (index for index, line in enumerate(lines) if line.strip() == "[Wayland]"),
        None,
    )
    if section_start is None:
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.extend(
            (
                "[Wayland]\n",
                f"InputMethod={PLASMA_INPUT_METHOD_PATH}\n",
                "VirtualKeyboardMode=2\n",
            )
        )
        return "".join(lines)

    section_end = next(
        (
            index
            for index in range(section_start + 1, len(lines))
            if lines[index].lstrip().startswith("[")
        ),
        len(lines),
    )
    managed = {
        "InputMethod": f"InputMethod={PLASMA_INPUT_METHOD_PATH}\n",
        "VirtualKeyboardMode": "VirtualKeyboardMode=2\n",
    }
    found: set[str] = set()
    rewritten: list[str] = []
    for line in lines[section_start + 1 : section_end]:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key not in managed:
            rewritten.append(line)
        elif key not in found:
            rewritten.append(managed[key])
            found.add(key)
    for key, line in managed.items():
        if key not in found:
            rewritten.append(line)
    lines[section_start + 1 : section_end] = rewritten
    return "".join(lines)


def _plasma_lock_screen_patch_is_current(text: str | None) -> bool:
    """Return whether QML contains both unmodified managed blocks."""

    return bool(
        text is not None
        and text.count(PLASMA_LOCK_SCREEN_ROOT_PATCH) == 1
        and text.count(PLASMA_LOCK_SCREEN_BUTTON_PATCH) == 1
        and text.count(PLASMA_LOCK_SCREEN_ROOT_PATCH_START) == 1
        and text.count(PLASMA_LOCK_SCREEN_ROOT_PATCH_END) == 1
        and text.count(PLASMA_LOCK_SCREEN_BUTTON_PATCH_START) == 1
        and text.count(PLASMA_LOCK_SCREEN_BUTTON_PATCH_END) == 1
    )


def _plasma_lock_screen_patch_is_legacy(text: str | None) -> bool:
    """Return whether QML contains the previous exact managed block."""

    return bool(
        text is not None
        and any(
            text.count(patch) == 1
            for patch in (
                PLASMA_LOCK_SCREEN_LEGACY_PATCH,
                PLASMA_LOCK_SCREEN_PREVIOUS_PATCH,
                PLASMA_LOCK_SCREEN_AUTO_PATCH,
                PLASMA_LOCK_SCREEN_STACKED_BUTTON_PATCH,
                PLASMA_LOCK_SCREEN_UNQUALIFIED_BUTTON_PATCH,
                PLASMA_LOCK_SCREEN_UNORDERED_BUTTON_PATCH,
            )
        )
        and text.count(PLASMA_LOCK_SCREEN_PATCH_START) == 1
        and text.count(PLASMA_LOCK_SCREEN_PATCH_END) == 1
    )


def _plasma_lock_screen_patch_is_previous_split(text: str | None) -> bool:
    """Return whether QML contains the previous structural button block."""

    return bool(
        text is not None
        and text.count(PLASMA_LOCK_SCREEN_ROOT_PATCH) == 1
        and text.count(PLASMA_LOCK_SCREEN_PREVIOUS_BUTTON_PATCH) == 1
        and text.count(PLASMA_LOCK_SCREEN_ROOT_PATCH_START) == 1
        and text.count(PLASMA_LOCK_SCREEN_ROOT_PATCH_END) == 1
        and text.count(PLASMA_LOCK_SCREEN_BUTTON_PATCH_START) == 1
        and text.count(PLASMA_LOCK_SCREEN_BUTTON_PATCH_END) == 1
    )


def _plasma_version() -> tuple[int, int, int] | None:
    """Return the version of the package that owns Plasma's lock-screen QML."""

    path = str(PLASMA_LOCK_SCREEN_UI_PATH)
    version_text: str | None = None
    rpm = shutil.which("rpm")
    dpkg_query = shutil.which("dpkg-query")
    pacman = shutil.which("pacman")
    if rpm is not None:
        version_text = _command_output([rpm, "-qf", "--queryformat", "%{VERSION}", path])
    elif dpkg_query is not None:
        owner = _command_output([dpkg_query, "-S", path])
        if owner is not None and ": " in owner:
            package = owner.split(": ", 1)[0]
            version_text = _command_output([dpkg_query, "-W", "-f=${Version}", package])
    elif pacman is not None:
        package = _command_output([pacman, "-Qqo", path])
        if package is not None:
            installed = _command_output([pacman, "-Q", package])
            if installed is not None and " " in installed:
                version_text = installed.split(" ", 1)[1]
    if version_text is None:
        return None
    version_text = version_text.strip().split(":", 1)[-1]
    match = re.search(r"\b(\d+)\.(\d+)(?:\.(\d+))?\b", version_text)
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def _command_output(arguments: list[str]) -> str | None:
    """Run a metadata command and return non-empty stdout on success."""

    try:
        completed = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    output = completed.stdout.strip()
    return output if completed.returncode == 0 and output else None


def _plasma_lock_screen_version_supported() -> bool:
    version = _plasma_version()
    return bool(
        version is not None
        and PLASMA_LOCK_SCREEN_MIN_VERSION <= version < PLASMA_LOCK_SCREEN_MAX_VERSION
    )


def _require_supported_plasma_lock_screen_version() -> None:
    version = _plasma_version()
    if version is None:
        raise linux.LinuxSetupError("cannot determine the installed Plasma version")
    if not PLASMA_LOCK_SCREEN_MIN_VERSION <= version < PLASMA_LOCK_SCREEN_MAX_VERSION:
        rendered = ".".join(str(part) for part in version)
        raise linux.LinuxSetupError(
            f"Plasma lock-screen integration supports versions >=6.7.0 and <7.0.0; found {rendered}"
        )


def _plasma_lock_screen_ui_text(original: str) -> str:
    """Add the managed always-visible unlock UI block to Plasma QML."""

    if _plasma_lock_screen_patch_is_current(original):
        return original
    if _plasma_lock_screen_patch_is_previous_split(original):
        return original.replace(
            PLASMA_LOCK_SCREEN_PREVIOUS_BUTTON_PATCH,
            PLASMA_LOCK_SCREEN_BUTTON_PATCH,
            1,
        )
    if _plasma_lock_screen_patch_is_legacy(original):
        legacy_patch = next(
            patch
            for patch in (
                PLASMA_LOCK_SCREEN_LEGACY_PATCH,
                PLASMA_LOCK_SCREEN_PREVIOUS_PATCH,
                PLASMA_LOCK_SCREEN_AUTO_PATCH,
                PLASMA_LOCK_SCREEN_STACKED_BUTTON_PATCH,
                PLASMA_LOCK_SCREEN_UNQUALIFIED_BUTTON_PATCH,
                PLASMA_LOCK_SCREEN_UNORDERED_BUTTON_PATCH,
            )
            if patch in original
        )
        original = original.replace("\n" + legacy_patch, "", 1)
    markers = (
        PLASMA_LOCK_SCREEN_PATCH_START,
        PLASMA_LOCK_SCREEN_PATCH_END,
        PLASMA_LOCK_SCREEN_ROOT_PATCH_START,
        PLASMA_LOCK_SCREEN_ROOT_PATCH_END,
        PLASMA_LOCK_SCREEN_BUTTON_PATCH_START,
        PLASMA_LOCK_SCREEN_BUTTON_PATCH_END,
    )
    if any(marker in original for marker in markers):
        raise linux.LinuxSetupError("refusing to replace a changed Axidev lock-screen QML block")
    root_anchor = "    MouseArea {\n        id: lockScreenRoot\n"
    button_anchor = "            PlasmaComponents3.ToolButton {\n                id: virtualKeyboardButton\n"
    if original.count(root_anchor) != 1:
        raise linux.LinuxSetupError(
            "Plasma lock-screen QML does not contain the supported lockScreenRoot structure"
        )
    if original.count(button_anchor) != 1:
        raise linux.LinuxSetupError(
            "Plasma lock-screen QML does not contain the supported virtualKeyboardButton structure"
        )
    managed = original.replace(
        root_anchor,
        root_anchor + "\n" + PLASMA_LOCK_SCREEN_ROOT_PATCH,
        1,
    )
    return managed.replace(button_anchor, PLASMA_LOCK_SCREEN_BUTTON_PATCH + button_anchor, 1)


def _plasma_lock_screen_ui_without_patch(managed: str) -> str:
    """Remove only the exact managed block from Plasma QML."""

    if _plasma_lock_screen_patch_is_current(managed):
        unmanaged = managed.replace("\n" + PLASMA_LOCK_SCREEN_ROOT_PATCH, "", 1)
        return unmanaged.replace(PLASMA_LOCK_SCREEN_BUTTON_PATCH, "", 1)
    if _plasma_lock_screen_patch_is_previous_split(managed):
        unmanaged = managed.replace("\n" + PLASMA_LOCK_SCREEN_ROOT_PATCH, "", 1)
        return unmanaged.replace(PLASMA_LOCK_SCREEN_PREVIOUS_BUTTON_PATCH, "", 1)
    if _plasma_lock_screen_patch_is_legacy(managed):
        legacy_patch = next(
            patch
            for patch in (
                PLASMA_LOCK_SCREEN_LEGACY_PATCH,
                PLASMA_LOCK_SCREEN_PREVIOUS_PATCH,
                PLASMA_LOCK_SCREEN_AUTO_PATCH,
                PLASMA_LOCK_SCREEN_STACKED_BUTTON_PATCH,
                PLASMA_LOCK_SCREEN_UNQUALIFIED_BUTTON_PATCH,
                PLASMA_LOCK_SCREEN_UNORDERED_BUTTON_PATCH,
            )
            if patch in managed
        )
        return managed.replace("\n" + legacy_patch, "", 1)
    markers = (
        PLASMA_LOCK_SCREEN_PATCH_START,
        PLASMA_LOCK_SCREEN_PATCH_END,
        PLASMA_LOCK_SCREEN_ROOT_PATCH_START,
        PLASMA_LOCK_SCREEN_ROOT_PATCH_END,
        PLASMA_LOCK_SCREEN_BUTTON_PATCH_START,
        PLASMA_LOCK_SCREEN_BUTTON_PATCH_END,
    )
    if any(marker in managed for marker in markers):
        raise linux.LinuxSetupError("refusing to remove a changed Axidev lock-screen QML block")
    return managed


def _lightdm_config_text() -> str:
    return f"[Seat:*]\ngreeter-wrapper={LIGHTDM_WRAPPER_PATH}\n"


def _lightdm_wrapper_text(launcher: Path) -> str:
    return (
        "#!/bin/sh\n"
        '"$@" &\n'
        "greeter_pid=$!\n"
        "stop_children() {\n"
        '    kill -TERM "${keyboard_pid:-}" 2>/dev/null || true\n'
        '    kill -TERM "${greeter_pid}" 2>/dev/null || true\n'
        "}\n"
        "trap stop_children HUP INT TERM\n"
        "(\n"
        "    for fd in \"${LIGHTDM_TO_SERVER_FD:-}\" \"${LIGHTDM_FROM_SERVER_FD:-}\"; do\n"
        "        case \"${fd}\" in\n"
        "            ''|*[!0-9]*) ;;\n"
        "            *) eval \"exec ${fd}>&-\" ;;\n"
        "        esac\n"
        "    done\n"
        '    account=${USER:-${LOGNAME:-unknown}}\n'
        "    protocol=unknown\n"
        '    [ -z "${WAYLAND_DISPLAY:-}" ] || protocol=wayland\n'
        '    [ -n "${WAYLAND_DISPLAY:-}" ] || [ -z "${DISPLAY:-}" ] || protocol=x11\n'
        "    delay=1\n"
        '    while kill -0 "${greeter_pid}" 2>/dev/null; do\n'
        f'        "{launcher}" linux run-greeter-keyboard --manager lightdm '
        '--parent-pid "${greeter_pid}"\n'
        "        status=$?\n"
        '        kill -0 "${greeter_pid}" 2>/dev/null || exit 0\n'
        '        message=$(printf \'axidev-osk greeter error: manager=lightdm account=%s protocol=%s '
        "stage=supervisor-exit detail=status=%s retry_seconds=%s\' \"${account}\" "
        '"${protocol}" "${status}" "${delay}")\n'
        '        printf \'%s\\n\' "${message}" >&2\n'
        "        command -v systemd-cat >/dev/null 2>&1 && "
        'printf \'%s\\n\' "${message}" | systemd-cat -t axidev-osk-greeter -p err\n'
        '        sleep "${delay}"\n'
        '        [ "${delay}" -ge 60 ] || delay=$((delay * 2))\n'
        '        [ "${delay}" -le 60 ] || delay=60\n'
        "    done\n"
        ") &\n"
        "keyboard_pid=$!\n"
        'wait "${greeter_pid}"\n'
        "status=$?\n"
        'kill -TERM "${keyboard_pid}" 2>/dev/null || true\n'
        'wait "${keyboard_pid}" 2>/dev/null || true\n'
        'exit "${status}"\n'
    )


def _native_supervisor_text(launcher: Path) -> str:
    return (
        "#!/bin/sh\n"
        "trap 'exit 0' HUP INT TERM\n"
        'manager="${1:?missing login manager}"\n'
        'account=${USER:-${LOGNAME:-unknown}}\n'
        "protocol=unknown\n"
        '[ -z "${WAYLAND_DISPLAY:-}" ] || protocol=wayland\n'
        '[ -n "${WAYLAND_DISPLAY:-}" ] || [ -z "${DISPLAY:-}" ] || protocol=x11\n'
        "delay=1\n"
        "while :; do\n"
        f'    "{launcher}" linux run-greeter-keyboard --manager "${{manager}}"\n'
        "    status=$?\n"
        '    message=$(printf \'axidev-osk greeter error: manager=%s account=%s protocol=%s '
        "stage=supervisor-exit detail=status=%s retry_seconds=%s\' \"${manager}\" "
        '"${account}" "${protocol}" "${status}" "${delay}")\n'
        '    printf \'%s\\n\' "${message}" >&2\n'
        "    command -v systemd-cat >/dev/null 2>&1 && "
        'printf \'%s\\n\' "${message}" | systemd-cat -t axidev-osk-greeter -p err\n'
        '    sleep "${delay}"\n'
        '    [ "${delay}" -ge 60 ] || delay=$((delay * 2))\n'
        '    [ "${delay}" -le 60 ] || delay=60\n'
        "done\n"
    )


def _greetd_wrapper_text(launcher: Path, original_command: str) -> str:
    command = shlex.quote(original_command)
    return (
        "#!/bin/sh\n"
        f"/bin/sh -c {command} &\n"
        "greeter_pid=$!\n"
        "stop_children() {\n"
        '    kill -TERM "${keyboard_pid:-}" 2>/dev/null || true\n'
        '    kill -TERM "${greeter_pid}" 2>/dev/null || true\n'
        "}\n"
        "trap stop_children HUP INT TERM\n"
        "(\n"
        '    account=${USER:-${LOGNAME:-unknown}}\n'
        "    delay=1\n"
        '    while kill -0 "${greeter_pid}" 2>/dev/null; do\n'
        f'        "{launcher}" linux run-greeter-keyboard --manager greetd '
        '--parent-pid "${greeter_pid}" --discover-display\n'
        "        status=$?\n"
        '        kill -0 "${greeter_pid}" 2>/dev/null || exit 0\n'
        '        message=$(printf \'axidev-osk greeter error: manager=greetd account=%s protocol=unknown '
        "stage=supervisor-exit detail=status=%s retry_seconds=%s\' \"${account}\" "
        '"${status}" "${delay}")\n'
        '        printf \'%s\\n\' "${message}" >&2\n'
        "        command -v systemd-cat >/dev/null 2>&1 && "
        'printf \'%s\\n\' "${message}" | systemd-cat -t axidev-osk-greeter -p err\n'
        '        sleep "${delay}"\n'
        '        [ "${delay}" -ge 60 ] || delay=$((delay * 2))\n'
        '        [ "${delay}" -le 60 ] || delay=60\n'
        "    done\n"
        ") &\n"
        "keyboard_pid=$!\n"
        'wait "${greeter_pid}"\n'
        "status=$?\n"
        'kill -TERM "${keyboard_pid}" 2>/dev/null || true\n'
        'wait "${keyboard_pid}" 2>/dev/null || true\n'
        'exit "${status}"\n'
    )


def _lightdm_effective_wrapper() -> str | None:
    executable = shutil.which("lightdm")
    if executable is None:
        raise linux.LinuxSetupError("LightDM executable is missing")
    try:
        completed = subprocess.run(
            [executable, "--show-config"], check=False, capture_output=True, text=True
        )
    except OSError as exc:
        raise linux.LinuxSetupError(f"cannot inspect LightDM configuration: {exc}") from exc
    if completed.returncode != 0:
        raise linux.LinuxSetupError("LightDM rejected its effective configuration")
    values = []
    for line in "\n".join((completed.stdout, completed.stderr)).splitlines():
        match = re.search(r"\bgreeter-wrapper\s*=\s*(\S.*)$", line)
        if match:
            values.append(match.group(1).strip())
    return values[-1] if values else None


def _parse_greetd_config(contents: str) -> GreetdConfig:
    lines = contents.splitlines(keepends=True)
    in_default = False
    command_match: tuple[int, str, str, str] | None = None
    account: str | None = None
    assignment = re.compile(r"^\s*(command|user)\s*=\s*(\"(?:[^\"\\]|\\.)*\")\s*(?:#.*)?(?:\r?\n)?$")
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_default = stripped == "[default_session]"
            continue
        if not in_default:
            continue
        match = assignment.match(line)
        if not match:
            if re.match(r"^\s*(command|user)\s*=", line):
                raise linux.LinuxSetupError("greetd default-session values must use one-line quoted strings")
            continue
        try:
            value = json.loads(match.group(2))
        except json.JSONDecodeError as exc:
            raise linux.LinuxSetupError("greetd default-session string is unsupported") from exc
        if match.group(1) == "command":
            if command_match is not None:
                raise linux.LinuxSetupError("greetd has multiple default-session commands")
            newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            command_match = (index, value, line, newline)
        else:
            account = value
    if command_match is None or not account:
        raise linux.LinuxSetupError("greetd default_session requires one command and user")
    index, command, original_line, newline = command_match
    return GreetdConfig(account, command, index, original_line, newline)


def _require_compatible_file(path: Path, expected: str) -> None:
    current = linux._read_text(path)
    if current is not None and current != expected:
        raise linux.LinuxSetupError(f"refusing to replace conflicting file: {path}")


def _require_writable_regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise linux.LinuxSetupError(f"refusing to replace a non-regular file: {path}")


def _require_compatible_symlink(path: Path, target: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if not path.is_symlink() or path.resolve() != target.resolve():
        raise linux.LinuxSetupError(f"refusing to replace conflicting link: {path}")


def _remove_owned_symlink(path: Path, target: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if not path.is_symlink() or path.resolve() != target.resolve():
        raise linux.LinuxSetupError(f"refusing to remove conflicting link: {path}")
    path.unlink()


def _require_removable_file(path: Path, expected: str) -> None:
    current = linux._read_text(path)
    if current is not None and current != expected:
        raise linux.LinuxSetupError(f"refusing to remove conflicting file: {path}")


def _require_removable_symlink(path: Path, target: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if not path.is_symlink() or path.resolve() != target.resolve():
        raise linux.LinuxSetupError(f"refusing to remove conflicting link: {path}")


def _load_state(*, required: bool) -> dict[str, Any] | None:
    text = linux._read_text(STATE_PATH)
    if text is None:
        if required:
            raise linux.LinuxSetupError("greeter startup is not configured")
        return None
    try:
        state = json.loads(text)
    except json.JSONDecodeError as exc:
        raise linux.LinuxSetupError(f"invalid managed greeter state: {STATE_PATH}") from exc
    if not isinstance(state, dict) or state.get("schema") != 1:
        raise linux.LinuxSetupError(f"unsupported managed greeter state: {STATE_PATH}")
    _state_manager(state)
    _state_string(state, "account")
    return state


def _state_manager(state: dict[str, Any]) -> str:
    manager = _state_string(state, "manager")
    _manager_adapter(manager)
    return manager


def _state_string(state: dict[str, Any], key: str) -> str:
    value = state.get(key)
    if not isinstance(value, str) or not value:
        raise linux.LinuxSetupError(f"managed greeter state is missing {key}")
    return value


def _state_text(state: dict[str, Any], key: str) -> str:
    value = state.get(key)
    if not isinstance(value, str):
        raise linux.LinuxSetupError(f"managed greeter state is missing {key}")
    return value


def _state_mode(state: dict[str, Any], key: str) -> int:
    value = state.get(key)
    if not isinstance(value, int) or not 0 <= value <= 0o777:
        raise linux.LinuxSetupError(f"managed greeter state is missing {key}")
    return value


def _is_legacy_plasma_state(state: dict[str, Any]) -> bool:
    return state.get("manager") == "plasma-login" and "original_kwinrc" not in state


def _runtime_launcher() -> Path:
    launcher = shutil.which("axidev-osk")
    return Path(launcher).resolve() if launcher else DEFAULT_LAUNCHER_PATH


class _KeyboardSupervisor:
    def __init__(self, manager: str, environment: dict[str, str]) -> None:
        self.manager = manager
        self.environment = environment
        self.process: subprocess.Popen[Any] | None = None
        self.started_at = 0.0
        self.next_start = 0.0
        self.delay_index = 0

    def tick(self, now: float) -> None:
        if self.process is not None:
            status = self.process.poll()
            if status is None:
                return
            runtime = now - self.started_at
            if runtime >= HEALTHY_RUNTIME_SECONDS:
                self.delay_index = 0
            delay = RETRY_DELAYS[self.delay_index]
            self.delay_index = min(self.delay_index + 1, len(RETRY_DELAYS) - 1)
            self.next_start = now + delay
            _log_error(self.manager, "keyboard-exit", f"status={status} retry_seconds={delay:g}")
            self.process = None
        if now < self.next_start:
            return
        try:
            self.process = subprocess.Popen([str(_runtime_launcher())], env=self.environment)
            self.started_at = now
        except OSError as exc:
            delay = RETRY_DELAYS[self.delay_index]
            self.delay_index = min(self.delay_index + 1, len(RETRY_DELAYS) - 1)
            self.next_start = now + delay
            _log_error(self.manager, "keyboard-start", f"{exc} retry_seconds={delay:g}")

    def stop(self) -> None:
        if self.process is not None:
            _terminate_process(self.process)
            self.process = None


def _run_keyboard_supervisor(manager: str, environment: dict[str, str]) -> int:
    stopping = False

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    previous = _install_signal_handlers(stop)
    supervisor = _KeyboardSupervisor(manager, environment)
    try:
        while not stopping:
            supervisor.tick(time.monotonic())
            time.sleep(POLL_SECONDS)
    finally:
        supervisor.stop()
        _restore_signal_handlers(previous)
    return 0


def _run_attached_supervisor(
    manager: str,
    parent_pid: int,
    display_environment: dict[str, str] | None,
) -> int:
    stopping = False

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    previous = _install_signal_handlers(stop)
    identity = _process_identity(parent_pid)
    if identity is None:
        _restore_signal_handlers(previous)
        raise linux.LinuxSetupError(f"greeter process does not exist: pid={parent_pid}")
    supervisor: _KeyboardSupervisor | None = None
    last_discovery_error: str | None = None
    try:
        while _process_identity(parent_pid) == identity and not stopping:
            if supervisor is None:
                try:
                    discovered = display_environment or _discover_display_environment(parent_pid)
                except linux.LinuxSetupError as exc:
                    message = str(exc)
                    if message != last_discovery_error:
                        _log_error(manager, "display-discovery", message)
                        last_discovery_error = message
                    discovered = None
                if discovered is not None:
                    supervisor = _KeyboardSupervisor(manager, discovered)
            if supervisor is not None:
                supervisor.tick(time.monotonic())
            time.sleep(POLL_SECONDS)
        if supervisor is None and not stopping:
            _log_error(manager, "display-discovery", "greeter exited before a unique display was found")
        return 0
    finally:
        if supervisor is not None:
            supervisor.stop()
        _restore_signal_handlers(previous)


def _process_identity(pid: int) -> str | None:
    try:
        contents = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except OSError:
        return None
    command_end = contents.rfind(")")
    if command_end < 0:
        return None
    fields = contents[command_end + 1 :].split()
    return fields[19] if len(fields) > 19 else None


def _discover_display_environment(root_pid: int) -> dict[str, str] | None:
    candidates: dict[tuple[str, ...], dict[str, str]] = {}
    for pid in _descendant_pids(root_pid):
        environment = _read_process_environment(pid)
        if environment is None:
            continue
        if environment.get("WAYLAND_DISPLAY") and environment.get("XDG_RUNTIME_DIR"):
            signature = (
                "wayland",
                environment["XDG_RUNTIME_DIR"],
                environment["WAYLAND_DISPLAY"],
            )
        elif environment.get("DISPLAY") and environment.get("XAUTHORITY"):
            signature = ("x11", environment["DISPLAY"], environment["XAUTHORITY"])
        else:
            continue
        allowed = {
            key: value
            for key, value in environment.items()
            if key
            in {
                "WAYLAND_DISPLAY",
                "XDG_RUNTIME_DIR",
                "DISPLAY",
                "XAUTHORITY",
                "DBUS_SESSION_BUS_ADDRESS",
                "XDG_SESSION_TYPE",
                "XDG_CURRENT_DESKTOP",
                "QT_QPA_PLATFORM",
            }
        }
        candidates[signature] = allowed
    if len(candidates) > 1:
        protocols = ",".join(sorted(signature[0] for signature in candidates))
        raise linux.LinuxSetupError(f"multiple greeter displays found: protocols={protocols}")
    if not candidates:
        return None
    result = os.environ.copy()
    result.update(next(iter(candidates.values())))
    return result


def _descendant_pids(root_pid: int) -> list[int]:
    result: list[int] = []
    pending = [root_pid]
    visited = {root_pid}
    while pending:
        parent = pending.pop()
        path = Path(f"/proc/{parent}/task/{parent}/children")
        try:
            values = path.read_text(encoding="ascii").split()
        except OSError:
            continue
        for value in values:
            try:
                child = int(value)
            except ValueError:
                continue
            if child in visited:
                continue
            visited.add(child)
            result.append(child)
            pending.append(child)
    return result


def _read_process_environment(pid: int) -> dict[str, str] | None:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return None
    environment: dict[str, str] = {}
    for item in raw.split(b"\0"):
        if b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        environment[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    return environment


def _install_signal_handlers(handler: Callable[[int, Any], None]) -> dict[int, Any]:
    previous = {}
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        previous[signum] = signal.signal(signum, handler)
    return previous


def _restore_signal_handlers(previous: dict[int, Any]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def _terminate_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _log_error(manager: str, stage: str, detail: str) -> None:
    clean = " ".join(detail.replace("\x00", "").split())
    account = os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown"
    if os.environ.get("WAYLAND_DISPLAY"):
        protocol = "wayland"
    elif os.environ.get("DISPLAY"):
        protocol = "x11"
    else:
        protocol = "unknown"
    message = (
        f"axidev-osk greeter error: manager={manager} account={account} "
        f"protocol={protocol} stage={stage} detail={clean}"
    )
    print(message, file=sys.stderr, flush=True)
    systemd_cat = shutil.which("systemd-cat")
    if systemd_cat is None:
        return
    try:
        subprocess.run(
            [systemd_cat, "-t", "axidev-osk-greeter", "-p", "err"],
            input=message + "\n",
            text=True,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


__all__ = ["register_runtime_commands", "run_runtime_command", "run_setup_command"]
