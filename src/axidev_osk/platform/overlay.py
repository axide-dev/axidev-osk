"""Shared overlay backend selection primitives."""

from __future__ import annotations

import os
from enum import Enum

from PySide6.QtGui import QGuiApplication


OVERLAY_BACKEND_ENV = "AXIDEV_OSK_OVERLAY_BACKEND"
OVERLAY_DEBUG_ENV = "AXIDEV_OSK_OVERLAY_DEBUG"


class OverlayBackend(str, Enum):
    """Supported platform strategies for overlay windows."""

    NATIVE = "native"
    WINDOWS_NATIVE = "windows-native"
    WAYLAND_INPUT_PANEL = "wayland-input-panel"
    WAYLAND_LAYER_SHELL = "wayland-layer-shell"
    X11_UTILITY = "x11-utility"
    X11_UTILITY_BRIDGE = "x11-utility-bridge"


def read_selected_overlay_backend() -> OverlayBackend | None:
    """Return the backend selected through the process environment."""

    raw_value = os.environ.get(OVERLAY_BACKEND_ENV, "")
    if not raw_value:
        return None
    try:
        return OverlayBackend(raw_value)
    except ValueError:
        return None


def qt_platform_name() -> str:
    """Return the active Qt platform name, or an empty string before QApplication."""

    return QGuiApplication.platformName().lower() if QGuiApplication.instance() is not None else ""
