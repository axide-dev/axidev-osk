"""Linux permission and desktop-session setup commands."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.platform.startswith("linux"):
    import grp
    import pwd
else:
    grp = None
    pwd = None


UINPUT_GROUP = "uinput"
UDEV_RULE_NAME = "70-axidev-io-uinput.rules"
UDEV_RULE_TEXT = 'KERNEL=="uinput", MODE="0660", GROUP="uinput", OPTIONS+="static_node=uinput"\n'
UDEV_RULE_PATH = Path("/etc/udev/rules.d") / UDEV_RULE_NAME
VENDOR_UDEV_RULE_PATHS = (
    Path("/usr/lib/udev/rules.d") / UDEV_RULE_NAME,
    Path("/lib/udev/rules.d") / UDEV_RULE_NAME,
)
UINPUT_PATH = Path("/dev/uinput")
AUTOSTART_RELATIVE_PATH = Path(".config/autostart/axidev-osk.desktop")
AUTOSTART_MANAGED_LINE = "X-Axidev-OSK-Managed=true\n"


class LinuxSetupError(RuntimeError):
    """Raised when Linux integration cannot reach the requested state."""


@dataclass(frozen=True)
class Account:
    """Validated local account used by Linux setup commands."""

    name: str
    uid: int
    gid: int
    home: Path


def register_commands(parser: argparse.ArgumentParser) -> None:
    """Register Linux lifecycle commands on an argparse platform parser."""

    commands = parser.add_subparsers(dest="linux_command", required=True)
    definitions = (
        ("setup-permissions", "setup", "permissions", True, "configure uinput access"),
        ("status-permissions", "status", "permissions", True, "check uinput access"),
        ("remove-permissions", "remove", "permissions", False, "disable the Axidev OSK udev rule"),
        ("setup-autostart", "setup", "autostart", True, "start Axidev OSK with a desktop session"),
        ("status-autostart", "status", "autostart", True, "check desktop-session autostart"),
        ("remove-autostart", "remove", "autostart", True, "remove desktop-session autostart"),
    )
    for name, action, resource, accepts_user, help_text in definitions:
        command = commands.add_parser(name, help=help_text, description=help_text)
        if accepts_user:
            command.add_argument("--user", help="local account to configure")
        command.set_defaults(handler=run_command, action=action, resource=resource)


def run_command(namespace: argparse.Namespace, argv: list[str]) -> int:
    """Dispatch one validated Linux setup command."""

    if not sys.platform.startswith("linux"):
        print("Axidev OSK Linux setup commands require Linux.", file=sys.stderr)
        return 2

    try:
        account = None
        if hasattr(namespace, "user"):
            account = _resolve_account(namespace.user)

        if namespace.resource == "permissions":
            return _run_permissions(namespace.action, account, argv)
        return _run_autostart(namespace.action, account, argv)
    except LinuxSetupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _run_permissions(action: str, account: Account | None, argv: list[str]) -> int:
    if action in {"setup", "remove"} and not _is_root():
        return _sudo_reexec(argv, account)
    if action == "setup":
        assert account is not None
        _setup_permissions(account)
        return _status_permissions(account)
    if action == "status":
        assert account is not None
        return _status_permissions(account)
    _remove_permissions()
    print("Linux uinput permissions are disabled by the Axidev OSK udev mask.")
    return 0


def _run_autostart(action: str, account: Account | None, argv: list[str]) -> int:
    assert account is not None
    if account.uid != _effective_uid():
        return _sudo_reexec(argv, account, run_as_account=True)
    if action == "setup":
        _setup_autostart(account)
        return _status_autostart(account)
    if action == "status":
        return _status_autostart(account)
    _remove_autostart(account)
    print(f"Autostart is removed for {account.name}.")
    return 0


def _resolve_account(requested_user: str | None) -> Account:
    if pwd is None:
        raise LinuxSetupError("local account lookup requires Linux")

    user = requested_user
    if user is None and _is_root():
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user and sudo_user != "root":
            user = sudo_user
        else:
            raise LinuxSetupError("--user is required when running directly as root")

    try:
        record = pwd.getpwnam(user) if user else pwd.getpwuid(_effective_uid())
    except KeyError as exc:
        raise LinuxSetupError(f"local user does not exist: {user}") from exc

    home = Path(record.pw_dir)
    if not home.is_dir():
        raise LinuxSetupError(f"home directory does not exist: {home}")
    return Account(record.pw_name, record.pw_uid, record.pw_gid, home)


def _sudo_reexec(argv: list[str], account: Account | None, *, run_as_account: bool = False) -> int:
    explicit_args = list(argv)
    if account is not None and "--user" not in explicit_args:
        explicit_args.extend(("--user", account.name))
    child_command = [sys.executable, "-m", "axidev_osk", *explicit_args]
    if run_as_account and _is_root():
        assert account is not None
        runuser = shutil.which("runuser")
        if runuser is None:
            raise LinuxSetupError("runuser is required to configure another user's autostart as root")
        command = [runuser, "--user", account.name, "--", *child_command]
    else:
        sudo = shutil.which("sudo")
        if sudo is None:
            raise LinuxSetupError("sudo is required for this operation")
        command = [sudo]
        if run_as_account:
            assert account is not None
            command.extend(("--user", account.name))
        command.extend(("--", *child_command))

    environment = None
    if run_as_account:
        environment = os.environ.copy()
        environment.pop("XDG_CONFIG_HOME", None)
    try:
        return subprocess.run(command, check=False, env=environment).returncode
    except OSError as exc:
        raise LinuxSetupError(str(exc)) from exc


def _setup_permissions(account: Account) -> None:
    assert grp is not None
    try:
        group = grp.getgrnam(UINPUT_GROUP)
    except KeyError:
        _run_checked(["groupadd", "--system", UINPUT_GROUP])
        group = grp.getgrnam(UINPUT_GROUP)

    _write_atomic(UDEV_RULE_PATH, UDEV_RULE_TEXT, 0o644)
    membership_added = not _account_in_group(account, group)
    if membership_added:
        _run_checked(["usermod", "-aG", UINPUT_GROUP, account.name])

    _reload_udev(ensure_device=True)
    print(f"Linux uinput permissions are configured for {account.name}.")
    if membership_added:
        print("Log out and back in before starting Axidev OSK.")


def _status_permissions(account: Account) -> int:
    assert grp is not None
    checks: list[tuple[str, bool]] = []
    try:
        group = grp.getgrnam(UINPUT_GROUP)
    except KeyError:
        group = None

    checks.append((f"group {UINPUT_GROUP}", group is not None))
    checks.append(("udev rule", _permission_rule_is_enabled()))
    checks.append(("group membership", group is not None and _account_in_group(account, group)))
    checks.append(("/dev/uinput mode", group is not None and _uinput_mode_is_ready(group.gr_gid)))
    if account.uid == _effective_uid():
        checks.append(("current session access", os.access(UINPUT_PATH, os.W_OK)))

    for label, passed in checks:
        print(f"{'ok' if passed else 'missing'}: {label}")
    return 0 if all(passed for _, passed in checks) else 1


def _remove_permissions() -> None:
    UDEV_RULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if UDEV_RULE_PATH.exists() or UDEV_RULE_PATH.is_symlink():
        UDEV_RULE_PATH.unlink()
    try:
        UDEV_RULE_PATH.symlink_to("/dev/null")
    except OSError as exc:
        raise LinuxSetupError(f"cannot mask {UDEV_RULE_PATH}: {exc}") from exc
    _reload_udev()


def _permission_rule_is_enabled() -> bool:
    if UDEV_RULE_PATH.is_symlink():
        return False
    paths = (UDEV_RULE_PATH, *VENDOR_UDEV_RULE_PATHS)
    return any(_read_text(path) == UDEV_RULE_TEXT for path in paths)


def _account_in_group(account: Account, group: Any) -> bool:
    return account.gid == group.gr_gid or account.name in group.gr_mem


def _uinput_mode_is_ready(group_gid: int) -> bool:
    try:
        details = UINPUT_PATH.stat()
    except OSError:
        return False
    required = stat.S_IWGRP | stat.S_IRGRP
    return details.st_gid == group_gid and details.st_mode & required == required


def _reload_udev(*, ensure_device: bool = False) -> None:
    _run_checked(["udevadm", "control", "--reload-rules"])
    if ensure_device and not UINPUT_PATH.exists():
        _run_checked(["modprobe", "uinput"])
        _run_checked(["udevadm", "settle"])
    if UINPUT_PATH.exists():
        _run_checked(["udevadm", "trigger", str(UINPUT_PATH)])
        _run_checked(["udevadm", "settle"])


def _setup_autostart(account: Account) -> None:
    path = _autostart_path(account)
    _ensure_directory(path.parent)
    _write_atomic(path, _autostart_text(), 0o644)
    print(f"Autostart is configured for {account.name}.")


def _status_autostart(account: Account) -> int:
    path = _autostart_path(account)
    current = _read_text(path)
    if current is None:
        print(f"missing: {path}")
        return 1
    if current != _autostart_text():
        print(f"conflict: {path}")
        return 1
    print(f"ok: {path}")
    return 0


def _remove_autostart(account: Account) -> None:
    path = _autostart_path(account)
    current = _read_text(path)
    if current is None:
        return
    if AUTOSTART_MANAGED_LINE not in current.splitlines(keepends=True):
        raise LinuxSetupError(f"refusing to remove conflicting file: {path}")
    try:
        path.unlink()
    except OSError as exc:
        raise LinuxSetupError(f"cannot remove {path}: {exc}") from exc


def _autostart_text() -> str:
    executable = shutil.which("axidev-osk")
    if executable is None:
        raise LinuxSetupError("axidev-osk must be installed on PATH before enabling autostart")
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Axidev OSK\n"
        "Comment=Start the Axidev OSK on-screen keyboard\n"
        f"Exec={_desktop_exec_arg(executable)}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        f"{AUTOSTART_MANAGED_LINE}"
    )


def _desktop_exec_arg(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return f'"{escaped}"'


def _autostart_path(account: Account) -> Path:
    configured_home = os.environ.get("XDG_CONFIG_HOME")
    if configured_home and Path(configured_home).is_absolute():
        config_home = Path(configured_home)
    else:
        config_home = account.home / ".config"
    return config_home / "autostart" / "axidev-osk.desktop"


def _ensure_directory(path: Path) -> None:
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    if not current.is_dir():
        raise LinuxSetupError(f"autostart parent is not a directory: {current}")
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)


def _write_atomic(path: Path, contents: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except OSError as exc:
        raise LinuxSetupError(f"cannot write {path}: {exc}") from exc
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise LinuxSetupError(f"cannot read {path}: {exc}") from exc


def _run_checked(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise LinuxSetupError(f"required command is missing: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise LinuxSetupError(f"command failed with status {exc.returncode}: {' '.join(command)}") from exc


def _effective_uid() -> int:
    return os.geteuid()


def _is_root() -> bool:
    return _effective_uid() == 0


__all__ = ["LinuxSetupError", "register_commands", "run_command"]
