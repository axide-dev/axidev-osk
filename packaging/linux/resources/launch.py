"""Isolated Python bootstrap used by the native Linux launcher."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


MINIMUM_QT = (6, 7, 0)
MAXIMUM_QT = (7, 0, 0)


def _payload_root() -> Path:
    import os

    value = os.environ.get("AXIDEV_OSK_ROOT")
    if not value:
        raise SystemExit("axidev-osk: AXIDEV_OSK_ROOT is missing")
    return Path(value)


def _prepare_imports(root: Path) -> None:
    private_packages = root / "lib" / "python"
    if not private_packages.is_dir():
        raise SystemExit(f"axidev-osk: private Python tree is missing: {private_packages}")
    sys.path.insert(0, str(private_packages))


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", value)
    if match is None:
        raise SystemExit(f"axidev-osk: cannot parse runtime version: {value}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def _require_supported_qt(label: str, value: str) -> tuple[int, int, int]:
    parsed = _version_tuple(value)
    if not MINIMUM_QT <= parsed < MAXIMUM_QT:
        raise SystemExit(
            f"axidev-osk: {label} {value} is unsupported; install version 6.7 or newer, below 7.0"
        )
    return parsed


def _runtime_details() -> dict[str, str | list[str]]:
    if sys.version_info < (3, 10):
        raise SystemExit("axidev-osk: system Python 3.10 or newer is required")
    try:
        import axidev_io
        import PySide6
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError as exc:
        raise SystemExit(
            "axidev-osk: required host runtime packages are missing; "
            "install PySide6, Qt Wayland, and LayerShellQt"
        ) from exc

    pyside_version = _require_supported_qt("PySide6", PySide6.__version__)
    qt_version_text = QtCore.qVersion()
    qt_version = _require_supported_qt("Qt", qt_version_text)
    if pyside_version[:2] != qt_version[:2]:
        raise SystemExit(
            "axidev-osk: PySide6 and Qt major/minor versions do not match: "
            f"{PySide6.__version__} and {qt_version_text}"
        )

    plugin_root = Path(
        QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.LibraryPath.PluginsPath)
    )
    platform_plugins = plugin_root / "platforms"
    platform_names = (
        [path.name for path in platform_plugins.iterdir() if path.is_file()]
        if platform_plugins.is_dir()
        else []
    )
    if not any("qxcb" in name for name in platform_names):
        raise SystemExit("axidev-osk: the Qt X11 platform plugin is missing")
    if not any("qwayland" in name for name in platform_names):
        raise SystemExit("axidev-osk: the Qt Wayland platform plugin is missing")

    from axidev_osk.platform.layer_shell import (
        _find_layer_shell_plugin_root,
        _layer_shell_plugin_is_compatible,
    )

    layer_shell_root = _find_layer_shell_plugin_root()
    if layer_shell_root is None:
        raise SystemExit("axidev-osk: the LayerShellQt plugin is missing")
    if not _layer_shell_plugin_is_compatible(layer_shell_root):
        raise SystemExit(
            "axidev-osk: LayerShellQt is incompatible with the installed Qt runtime"
        )

    return {
        "axidev_io": axidev_io.version(),
        "layer_shell_plugins": str(layer_shell_root),
        "modules": [QtCore.__name__, QtGui.__name__, QtWidgets.__name__],
        "platform_plugins": str(plugin_root),
        "pyside": PySide6.__version__,
        "python": sys.version.split()[0],
        "qt": qt_version_text,
    }


def main() -> int:
    root = _payload_root()
    _prepare_imports(root)
    details = _runtime_details()
    if sys.argv[1:] == ["--verify-runtime"]:
        print(json.dumps(details, sort_keys=True))
        return 0

    from axidev_osk.__main__ import main as application_main

    return application_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
