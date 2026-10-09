"""Wayland layer-shell integration helpers.

Wraps LayerShellQt so the rest of the codebase can call
``attach_wayland_layer_shell`` and ``apply_wayland_layer_shell`` without
caring whether it is installed, locatable, or missing. Each overlay window
asks for a layer surface itself, through LayerShellQt's per-window
``LayerShellQt::Window::get``, before it is first shown; other windows stay
ordinary Wayland windows. Python has no LayerShellQt bindings, so that one
function is called through ctypes. Constants mirror the ``zwlr_layer_shell_v1``
protocol so call sites remain readable.

Per the project's architectural rules, Wayland-specific branching is
isolated to this module; non-Wayland sessions short-circuit to a no-op
return so callers can treat layer-shell as an optional optimization.
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import PySide6
import shiboken6
from PySide6.QtCore import QMargins, QObject, QLibraryInfo
from PySide6.QtGui import QWindow
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

_INTERFACE_SONAME = "libLayerShellQtInterface.so.6"
_WINDOW_GET_SYMBOL = "_ZN12LayerShellQt6Window3getEP7QWindow"
"""``LayerShellQt::Window::get(QWindow*)``, the per-window entry point."""

_interface_path: str | None = None
_window_get: Callable[[int], int | None] | None = None

_COMMON_QT_PLUGIN_ROOTS = (
    Path("/usr/lib64/qt6/plugins"),
    Path("/usr/lib/qt6/plugins"),
    Path("/usr/lib/x86_64-linux-gnu/qt6/plugins"),
    Path("/usr/local/lib64/qt6/plugins"),
    Path("/usr/local/lib/qt6/plugins"),
)


def wayland_layer_shell_available() -> bool:
    """Return whether overlay windows can ask LayerShellQt for layer surfaces.

    Call this before the QApplication exists. It does not change how Qt
    creates windows: only windows passed to ``attach_wayland_layer_shell``
    become layer surfaces. A ``QT_WAYLAND_SHELL_INTEGRATION`` set by the user
    is respected as is.
    """

    global _interface_path

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

    interface_path = layer_shell_interface_path(plugin_root)
    if interface_path is None or not layer_shell_interface_has_window_get(interface_path):
        return False

    _interface_path = str(interface_path)
    return True


def attach_wayland_layer_shell(window: QWidget) -> bool:
    """Make ``window`` a layer surface; call it before the window is first shown.

    The attachment survives hiding, showing, and Qt recreating the native
    window. Properties are set later with ``apply_wayland_layer_shell``.
    """

    if not is_wayland_session():
        return False
    handle = window.windowHandle()
    if handle is None:
        window.winId()
        handle = window.windowHandle()
    return handle is not None and _layer_shell_window(handle) is not None

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
    """Apply layer-shell properties to a realized Qt window handle."""

    if not is_wayland_session():
        return False

    handle = window.windowHandle()
    if handle is None:
        window.winId()
        handle = window.windowHandle()

    if handle is None:
        return False

    layer_shell_window = _layer_shell_window(handle)
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


def update_wayland_layer_shell_margins(window: QWidget, margins: QMargins) -> bool:
    """Update only the margins of an existing layer-shell surface."""

    if not is_wayland_session():
        return False
    handle = window.windowHandle()
    if handle is None:
        return False
    layer_shell_window = _layer_shell_window(handle)
    if layer_shell_window is None:
        return False
    layer_shell_window.setProperty("margins", margins)
    return True


def is_wayland_session() -> bool:
    """Return whether the current Linux session appears to be Wayland."""

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
    """Find a Qt plugin root containing the xcb platform plugin."""

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
    """Prepend a Qt plugin root to ``QT_PLUGIN_PATH`` if needed."""

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

    try:
        result = subprocess.run(
            ["ldd", "-r", str(plugin_path)],
            check=False,
            capture_output=True,
            text=True,
            env=_qt_library_environment(),
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


def layer_shell_interface_path(plugin_root: Path) -> Path | None:
    """Find the LayerShellQt interface library the layer-shell plugin links against."""

    plugin_path = plugin_root / "wayland-shell-integration" / "liblayer-shell.so"
    try:
        result = subprocess.run(
            ["ldd", str(plugin_path)],
            check=False,
            capture_output=True,
            text=True,
            env=_qt_library_environment(),
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    match = re.search(rf"{re.escape(_INTERFACE_SONAME)} => (\S+)", result.stdout)
    return Path(match.group(1)) if match else None


def layer_shell_interface_has_window_get(interface_path: Path) -> bool:
    """Check, in a separate process, that the library exports ``LayerShellQt::Window::get``.

    Loading the library here would pull Qt's Wayland client library into the
    process before Qt chooses its own, so the check runs in a child process.
    """

    check = f"import ctypes, sys; ctypes.CDLL(sys.argv[1]).{_WINDOW_GET_SYMBOL}"
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", check, str(interface_path)],
            check=False,
            capture_output=True,
            env=_qt_library_environment(),
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _qt_library_environment() -> dict[str, str]:
    qt_library_root = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.LibrariesPath))
    env = os.environ.copy()
    entries = [str(qt_library_root)]
    if env.get("LD_LIBRARY_PATH"):
        entries.append(env["LD_LIBRARY_PATH"])
    env["LD_LIBRARY_PATH"] = os.pathsep.join(entries)
    return env


def _layer_shell_window(handle: QWindow) -> QObject | None:
    """Return LayerShellQt's per-window object, creating it on first use."""

    global _window_get

    window_get = _window_get
    if window_get is None:
        try:
            library = ctypes.CDLL(_interface_path or _INTERFACE_SONAME)
            function = getattr(library, _WINDOW_GET_SYMBOL)
        except (OSError, AttributeError):
            return None
        function.restype = ctypes.c_void_p
        function.argtypes = [ctypes.c_void_p]
        window_get = _window_get = function
    pointer = window_get(shiboken6.getCppPointer(handle)[0])
    if not pointer:
        return None
    layer_shell_window = shiboken6.wrapInstance(pointer, QObject)
    return layer_shell_window if isinstance(layer_shell_window, QObject) else None
