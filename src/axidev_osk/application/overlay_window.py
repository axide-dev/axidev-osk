from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

from PySide6.QtCore import QMargins, QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from .layer_shell import (
    ANCHOR_BOTTOM,
    ANCHOR_LEFT,
    KEYBOARD_INTERACTIVITY_NONE,
    LAYER_OVERLAY,
    apply_wayland_layer_shell,
    configure_wayland_layer_shell_environment,
    find_qt_platform_plugin_root,
    is_wayland_session,
    prepend_plugin_root,
)


OVERLAY_BACKEND_ENV = "AXIDEV_OSK_OVERLAY_BACKEND"
TWindow = TypeVar("TWindow", bound=QWidget)


class OverlayBackend(str, Enum):
    NATIVE = "native"
    WINDOWS_NATIVE = "windows-native"
    WAYLAND_BEST_EFFORT = "wayland-best-effort"
    WAYLAND_LAYER_SHELL = "wayland-layer-shell"
    X11_UTILITY = "x11-utility"
    X11_UTILITY_BRIDGE = "x11-utility-bridge"


class OverlayPlacement(str, Enum):
    CENTER = "center"
    TOP_RIGHT = "top-right"


@dataclass(slots=True)
class AlwaysOnTopWindowConfig:
    placement: OverlayPlacement = OverlayPlacement.TOP_RIGHT
    screen_margin: int = 16


if sys.platform == "win32":
    _GWL_EXSTYLE = -20
    _HWND_TOPMOST = -1
    _SWP_NOMOVE = 0x0002
    _SWP_NOSIZE = 0x0001
    _SWP_NOACTIVATE = 0x0010
    _SWP_FRAMECHANGED = 0x0020
    _SWP_NOOWNERZORDER = 0x0200
    _WS_EX_NOACTIVATE = 0x08000000

    _user32 = ctypes.windll.user32
    _get_window_long_ptr = _user32.GetWindowLongPtrW
    _set_window_long_ptr = _user32.SetWindowLongPtrW
    _set_window_pos = _user32.SetWindowPos

    _get_window_long_ptr.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _get_window_long_ptr.restype = ctypes.c_longlong
    _set_window_long_ptr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong]
    _set_window_long_ptr.restype = ctypes.c_longlong
    _set_window_pos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    _set_window_pos.restype = ctypes.c_int


def prepare_always_on_top_window_environment(
    *,
    prefer_layer_shell: bool = True,
    prefer_x11_bridge: bool = True,
) -> OverlayBackend:
    if sys.platform == "win32":
        return _set_overlay_backend(OverlayBackend.WINDOWS_NATIVE)

    if not sys.platform.startswith("linux"):
        return _set_overlay_backend(OverlayBackend.NATIVE)

    forced_platform = os.environ.get("QT_QPA_PLATFORM", "").lower()
    if forced_platform == "xcb":
        if is_wayland_session():
            return _set_overlay_backend(OverlayBackend.X11_UTILITY_BRIDGE)
        return _set_overlay_backend(OverlayBackend.X11_UTILITY)

    if forced_platform and forced_platform != "wayland":
        return _set_overlay_backend(OverlayBackend.NATIVE)

    if not is_wayland_session():
        if os.environ.get("DISPLAY"):
            return _set_overlay_backend(OverlayBackend.X11_UTILITY)
        return _set_overlay_backend(OverlayBackend.NATIVE)

    if os.environ.get("QT_WAYLAND_SHELL_INTEGRATION") == "layer-shell":
        return _set_overlay_backend(OverlayBackend.WAYLAND_LAYER_SHELL)

    if prefer_layer_shell and configure_wayland_layer_shell_environment():
        return _set_overlay_backend(OverlayBackend.WAYLAND_LAYER_SHELL)

    if prefer_x11_bridge and _configure_x11_bridge_environment():
        return _set_overlay_backend(OverlayBackend.X11_UTILITY_BRIDGE)

    return _set_overlay_backend(OverlayBackend.WAYLAND_BEST_EFFORT)


def configure_always_on_top_window(
    window: QWidget,
    *,
    config: AlwaysOnTopWindowConfig | None = None,
) -> "AlwaysOnTopWindowController":
    controller = AlwaysOnTopWindowController(window, config=config)
    controller.configure_window()
    return controller


def create_always_on_top_window(
    window_factory: Callable[[], TWindow],
    *,
    config: AlwaysOnTopWindowConfig | None = None,
) -> tuple[TWindow, "AlwaysOnTopWindowController"]:
    window = window_factory()
    controller = configure_always_on_top_window(window, config=config)
    return window, controller


class AlwaysOnTopWindowController:
    def __init__(
        self,
        window: QWidget,
        *,
        config: AlwaysOnTopWindowConfig | None = None,
    ) -> None:
        self._window = window
        self._config = config or AlwaysOnTopWindowConfig()
        self._backend = self._detect_backend()
        self._layer_shell_attempts = 0
        self._layer_shell_left_margin = 0
        self._layer_shell_bottom_margin = 0
        self._layer_shell_position_initialized = False
        self._floating_position_initialized = False
        self._show_adjustments_applied = False

    @property
    def backend(self) -> OverlayBackend:
        return self._backend

    @property
    def uses_custom_chrome(self) -> bool:
        return self._backend in {
            OverlayBackend.WAYLAND_LAYER_SHELL,
            OverlayBackend.X11_UTILITY,
            OverlayBackend.X11_UTILITY_BRIDGE,
        }

    def configure_window(self) -> None:
        self._window.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._window.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)

        if self.uses_custom_chrome:
            self._window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        if self._backend in {OverlayBackend.X11_UTILITY, OverlayBackend.X11_UTILITY_BRIDGE}:
            self._window.setWindowFlag(Qt.WindowType.Tool, True)
            self._window.setAttribute(Qt.WidgetAttribute.WA_X11DoNotAcceptFocus, True)

    def handle_show(self) -> bool:
        if self._backend == OverlayBackend.WINDOWS_NATIVE:
            self._apply_windows_window_styles()
            self._position_floating_window_if_needed()
            return True

        if self._backend == OverlayBackend.WAYLAND_LAYER_SHELL:
            return self._apply_wayland_layer_shell_if_needed()

        if self._backend in {OverlayBackend.X11_UTILITY, OverlayBackend.X11_UTILITY_BRIDGE, OverlayBackend.NATIVE}:
            self._position_floating_window_if_needed()
            return True

        if self._show_adjustments_applied:
            return False

        if self._qt_platform() in {"wayland", "xcb"}:
            self._show_adjustments_applied = True
            self._window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self._window.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
            self._window.show()

        return False

    def move_by(self, dx: int, dy: int) -> None:
        if self._backend == OverlayBackend.WAYLAND_LAYER_SHELL:
            self._move_layer_shell_by(dx, dy)
            return

        if self._backend == OverlayBackend.WAYLAND_BEST_EFFORT:
            return

        geometry = self._current_screen_geometry()
        max_x = geometry.x() + max(0, geometry.width() - self._window.width())
        max_y = geometry.y() + max(0, geometry.height() - self._window.height())

        next_x = max(geometry.x(), min(self._window.x() + dx, max_x))
        next_y = max(geometry.y(), min(self._window.y() + dy, max_y))
        self._window.move(next_x, next_y)
        self._floating_position_initialized = True

    def resize_by(self, dx: int, dy: int) -> None:
        if self._backend == OverlayBackend.WAYLAND_LAYER_SHELL:
            self._resize_layer_shell_by(dx, dy)
            return

        if self._backend == OverlayBackend.WAYLAND_BEST_EFFORT:
            return

        geometry = self._current_screen_geometry()
        max_width = max(self._window.minimumWidth(), geometry.x() + geometry.width() - self._window.x())
        max_height = max(self._window.minimumHeight(), geometry.y() + geometry.height() - self._window.y())

        next_width = max(self._window.minimumWidth(), min(self._window.width() + dx, max_width))
        next_height = max(self._window.minimumHeight(), min(self._window.height() + dy, max_height))
        self._window.resize(next_width, next_height)
        self._floating_position_initialized = True

    def _detect_backend(self) -> OverlayBackend:
        if sys.platform == "win32":
            return OverlayBackend.WINDOWS_NATIVE

        platform = self._qt_platform()
        if platform == "wayland":
            selected = _read_selected_backend()
            if selected == OverlayBackend.WAYLAND_LAYER_SHELL:
                return selected
            return OverlayBackend.WAYLAND_BEST_EFFORT

        if platform == "xcb":
            selected = _read_selected_backend()
            if selected == OverlayBackend.X11_UTILITY_BRIDGE:
                return selected
            return OverlayBackend.X11_UTILITY

        return _read_selected_backend() or OverlayBackend.NATIVE

    def _apply_wayland_layer_shell_if_needed(self) -> bool:
        if self._backend != OverlayBackend.WAYLAND_LAYER_SHELL:
            return False

        if self._sync_wayland_layer_shell():
            return True

        if self._layer_shell_attempts < 5:
            self._layer_shell_attempts += 1
            QTimer.singleShot(50, self._apply_wayland_layer_shell_if_needed)

        return False

    def _sync_wayland_layer_shell(self) -> bool:
        if not self._layer_shell_position_initialized:
            self._initialize_layer_shell_position()

        return apply_wayland_layer_shell(
            self._window,
            anchors=ANCHOR_LEFT | ANCHOR_BOTTOM,
            layer=LAYER_OVERLAY,
            keyboard_interactivity=KEYBOARD_INTERACTIVITY_NONE,
            activate_on_show=False,
            wants_to_be_on_active_screen=True,
            exclusion_zone=0,
            margins=QMargins(self._layer_shell_left_margin, 0, 0, self._layer_shell_bottom_margin),
        )

    def _move_layer_shell_by(self, dx: int, dy: int) -> None:
        screen_size = self._current_screen_geometry().size()
        max_left = max(0, screen_size.width() - self._window.width())
        max_bottom = max(0, screen_size.height() - self._window.height())

        self._layer_shell_left_margin = max(0, min(self._layer_shell_left_margin + dx, max_left))
        self._layer_shell_bottom_margin = max(0, min(self._layer_shell_bottom_margin - dy, max_bottom))
        self._layer_shell_position_initialized = True
        self._sync_wayland_layer_shell()

    def _resize_layer_shell_by(self, dx: int, dy: int) -> None:
        screen_size = self._current_screen_geometry().size()
        top_offset = max(0, screen_size.height() - self._layer_shell_bottom_margin - self._window.height())
        max_width = max(self._window.minimumWidth(), screen_size.width() - self._layer_shell_left_margin)
        max_height = max(self._window.minimumHeight(), screen_size.height() - top_offset)

        next_width = max(self._window.minimumWidth(), min(self._window.width() + dx, max_width))
        next_height = max(self._window.minimumHeight(), min(self._window.height() + dy, max_height))
        self._layer_shell_bottom_margin = max(
            0,
            min(screen_size.height() - top_offset - next_height, screen_size.height()),
        )
        self._layer_shell_position_initialized = True
        self._window.resize(next_width, next_height)
        self._sync_wayland_layer_shell()

    def _initialize_layer_shell_position(self) -> None:
        screen_size = self._current_screen_geometry().size()

        if self._config.placement == OverlayPlacement.CENTER:
            self._layer_shell_left_margin = max(0, (screen_size.width() - self._window.width()) // 2)
            self._layer_shell_bottom_margin = max(0, (screen_size.height() - self._window.height()) // 2)
        else:
            margin = self._config.screen_margin
            self._layer_shell_left_margin = max(0, screen_size.width() - self._window.width() - margin)
            self._layer_shell_bottom_margin = max(0, screen_size.height() - self._window.height() - margin)

        self._layer_shell_position_initialized = True

    def _position_floating_window_if_needed(self) -> None:
        if self._floating_position_initialized:
            return

        geometry = self._current_screen_geometry()
        if self._config.placement == OverlayPlacement.CENTER:
            target_x = geometry.x() + max(0, (geometry.width() - self._window.width()) // 2)
            target_y = geometry.y() + max(0, (geometry.height() - self._window.height()) // 2)
        else:
            margin = self._config.screen_margin
            target_x = geometry.x() + max(0, geometry.width() - self._window.width() - margin)
            target_y = geometry.y() + margin

        self._window.move(target_x, target_y)
        self._floating_position_initialized = True

    def _current_screen_geometry(self) -> QRect:
        screen = self._window.screen()
        if screen is None:
            app = QGuiApplication.instance()
            screen = app.primaryScreen() if app is not None else None
        geometry = screen.availableGeometry() if screen is not None else None
        if geometry is None:
            return QRect(0, 0, 1920, 1080)
        return geometry

    def _apply_windows_window_styles(self) -> None:
        hwnd = int(self._window.winId())
        ex_style = _get_window_long_ptr(hwnd, _GWL_EXSTYLE)

        if ex_style & _WS_EX_NOACTIVATE == 0:
            _set_window_long_ptr(hwnd, _GWL_EXSTYLE, ex_style | _WS_EX_NOACTIVATE)

        _set_window_pos(
            hwnd,
            _HWND_TOPMOST,
            0,
            0,
            0,
            0,
            _SWP_NOMOVE
            | _SWP_NOSIZE
            | _SWP_NOACTIVATE
            | _SWP_FRAMECHANGED
            | _SWP_NOOWNERZORDER,
        )

    @staticmethod
    def _qt_platform() -> str:
        app = QGuiApplication.instance()
        if app is None:
            return ""
        return QGuiApplication.platformName().lower()


def _configure_x11_bridge_environment() -> bool:
    if not os.environ.get("DISPLAY"):
        return False

    plugin_root = find_qt_platform_plugin_root()
    if plugin_root is None:
        return False

    prepend_plugin_root(plugin_root)
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    return True


def _set_overlay_backend(backend: OverlayBackend) -> OverlayBackend:
    os.environ[OVERLAY_BACKEND_ENV] = backend.value
    return backend


def _read_selected_backend() -> OverlayBackend | None:
    raw_value = os.environ.get(OVERLAY_BACKEND_ENV, "")
    if not raw_value:
        return None

    try:
        return OverlayBackend(raw_value)
    except ValueError:
        return None
