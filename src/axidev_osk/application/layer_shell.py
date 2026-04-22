from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path

import PySide6
from PySide6.QtCore import QMargins, QObject, QLibraryInfo
from PySide6.QtWidgets import QWidget


ANCHOR_TOP = 1
ANCHOR_BOTTOM = 2
ANCHOR_LEFT = 4
ANCHOR_RIGHT = 8

LAYER_BACKGROUND = 0
LAYER_BOTTOM = 1
LAYER_TOP = 2
LAYER_OVERLAY = 3

KEYBOARD_INTERACTIVITY_NONE = 0
KEYBOARD_INTERACTIVITY_EXCLUSIVE = 1
KEYBOARD_INTERACTIVITY_ON_DEMAND = 2

_COMMON_QT_PLUGIN_ROOTS = (
    Path("/usr/lib64/qt6/plugins"),
    Path("/usr/lib/qt6/plugins"),
    Path("/usr/lib/x86_64-linux-gnu/qt6/plugins"),
    Path("/usr/local/lib64/qt6/plugins"),
    Path("/usr/local/lib/qt6/plugins"),
)
def configure_wayland_layer_shell_environment() -> bool:
    if not is_wayland_session():
        return False

    requested_integration = os.environ.get("QT_WAYLAND_SHELL_INTEGRATION")
    if requested_integration:
        return requested_integration == "layer-shell"

    plugin_root = _find_layer_shell_plugin_root()
    if plugin_root is None:
        return False

    if not _compositor_supports_layer_shell():
        return False

    if not _layer_shell_plugin_is_compatible(plugin_root):
        return False

    prepend_plugin_root(plugin_root)
    os.environ["QT_WAYLAND_SHELL_INTEGRATION"] = "layer-shell"
    return True

def apply_wayland_layer_shell(
    window: QWidget,
    *,
    anchors: int,
    layer: int,
    keyboard_interactivity: int,
    activate_on_show: bool,
    wants_to_be_on_active_screen: bool,
    exclusion_zone: int,
    margins: QMargins,
) -> bool:
    if not is_wayland_session():
        return False

    handle = window.windowHandle()
    if handle is None:
        window.winId()
        handle = window.windowHandle()

    if handle is None:
        return False

    layer_shell_window = _find_layer_shell_window(handle)
    if layer_shell_window is None:
        return False

    layer_shell_window.setProperty("anchors", anchors)
    layer_shell_window.setProperty("layer", layer)
    layer_shell_window.setProperty("keyboardInteractivity", keyboard_interactivity)
    layer_shell_window.setProperty("activateOnShow", activate_on_show)
    layer_shell_window.setProperty("wantsToBeOnActiveScreen", wants_to_be_on_active_screen)
    layer_shell_window.setProperty("exclusionZone", exclusion_zone)
    layer_shell_window.setProperty("margins", margins)
    return True


def is_wayland_session() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def _find_layer_shell_plugin_root() -> Path | None:
    seen_roots: set[Path] = set()

    for plugin_root in _candidate_plugin_roots():
        if plugin_root in seen_roots:
            continue
        seen_roots.add(plugin_root)

        plugin_dir = plugin_root / "wayland-shell-integration"
        if not plugin_dir.is_dir():
            continue

        for candidate in plugin_dir.iterdir():
            if candidate.is_file() and "layer-shell" in candidate.name:
                return plugin_root

    return None


def find_qt_platform_plugin_root() -> Path | None:
    seen_roots: set[Path] = set()

    for plugin_root in _candidate_plugin_roots():
        if plugin_root in seen_roots:
            continue
        seen_roots.add(plugin_root)

        plugin_dir = plugin_root / "platforms"
        if not plugin_dir.is_dir():
            continue

        for candidate in plugin_dir.iterdir():
            if candidate.is_file() and "qxcb" in candidate.name:
                return plugin_root

    return None


def _candidate_plugin_roots() -> list[Path]:
    plugin_roots: list[Path] = []

    plugin_roots.extend(_runtime_qt_plugin_roots())

    qt_plugin_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)
    if qt_plugin_path:
        plugin_roots.append(Path(qt_plugin_path))

    for env_name in ("QT_PLUGIN_PATH",):
        raw_paths = os.environ.get(env_name, "")
        if not raw_paths:
            continue
        for raw_path in raw_paths.split(os.pathsep):
            if raw_path:
                plugin_roots.append(Path(raw_path))

    plugin_roots.extend(_COMMON_QT_PLUGIN_ROOTS)
    return plugin_roots


def _runtime_qt_plugin_roots() -> list[Path]:
    roots: list[Path] = []
    executable_dir = Path(sys.executable).absolute().parent
    package_root = Path(PySide6.__file__).absolute().parent
    pyinstaller_root = getattr(sys, "_MEIPASS", "")

    roots.extend(
        (
            executable_dir / "_internal" / "PySide6" / "Qt" / "plugins",
            executable_dir / "PySide6" / "Qt" / "plugins",
            package_root / "Qt" / "plugins",
        )
    )

    if pyinstaller_root:
        frozen_root = Path(pyinstaller_root)
        roots.extend(
            (
                frozen_root / "PySide6" / "Qt" / "plugins",
                frozen_root / "qt6_plugins",
            )
        )

    return roots


def prepend_plugin_root(plugin_root: Path) -> None:
    existing = [entry for entry in os.environ.get("QT_PLUGIN_PATH", "").split(os.pathsep) if entry]
    root_str = str(plugin_root)
    if root_str in existing:
        return
    os.environ["QT_PLUGIN_PATH"] = os.pathsep.join((root_str, *existing))


def _compositor_supports_layer_shell() -> bool:
    if not sys.platform.startswith("linux"):
        return False

    if _is_gnome_or_mutter_desktop():
        return False

    command = shutil.which("wayland-info") or shutil.which("weston-info")
    if command is None:
        return True

    try:
        result = subprocess.run(
            [command],
            check=False,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
            timeout=5,
        )
    except subprocess.SubprocessError:
        return True

    output = "\n".join((result.stdout, result.stderr)).lower()
    return "zwlr_layer_shell_v1" in output


def _is_gnome_or_mutter_desktop() -> bool:
    desktop_markers = " ".join(
        value
        for value in (
            os.environ.get("XDG_CURRENT_DESKTOP"),
            os.environ.get("DESKTOP_SESSION"),
            os.environ.get("GDMSESSION"),
        )
        if value
    ).lower()
    return "gnome" in desktop_markers or "mutter" in desktop_markers


def _layer_shell_plugin_is_compatible(plugin_root: Path) -> bool:
    if not sys.platform.startswith("linux"):
        return True

    plugin_path = plugin_root / "wayland-shell-integration" / "liblayer-shell.so"
    if not plugin_path.is_file():
        return False

    qt_library_root = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.LibrariesPath))
    env = os.environ.copy()
    ld_library_path_entries = [str(qt_library_root)]
    existing_ld_library_path = env.get("LD_LIBRARY_PATH")
    if existing_ld_library_path:
        ld_library_path_entries.append(existing_ld_library_path)
    env["LD_LIBRARY_PATH"] = os.pathsep.join(ld_library_path_entries)

    try:
        result = subprocess.run(
            ["ldd", "-r", str(plugin_path)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return True

    output = "\n".join((result.stdout, result.stderr)).lower()
    incompatible_markers = (
        "undefined symbol",
        "private_api' not found",
        "private_api` not found",
        "version `qt_",
    )
    return not any(marker in output for marker in incompatible_markers)


def _find_layer_shell_window(root: QObject) -> QObject | None:
    pending: deque[QObject] = deque([root])

    while pending:
        current = pending.popleft()
        if _looks_like_layer_shell_window(current):
            return current
        pending.extend(child for child in current.children() if isinstance(child, QObject))

    return None


def _looks_like_layer_shell_window(candidate: QObject) -> bool:
    meta_object = candidate.metaObject()
    if meta_object is None:
        return False

    required_properties = (
        "anchors",
        "layer",
        "keyboardInteractivity",
        "activateOnShow",
        "wantsToBeOnActiveScreen",
    )
    return all(meta_object.indexOfProperty(name) >= 0 for name in required_properties)
