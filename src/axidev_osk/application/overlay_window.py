from __future__ import annotations

import ctypes
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

from PySide6.QtCore import QMargins, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from .layer_shell import (
    ANCHOR_BOTTOM,
    ANCHOR_LEFT,
    ANCHOR_RIGHT,
    ANCHOR_TOP,
    KEYBOARD_INTERACTIVITY_NONE,
    LAYER_OVERLAY,
    apply_wayland_layer_shell,
    configure_wayland_layer_shell_environment,
    find_qt_platform_plugin_root,
    is_wayland_session,
    prepend_plugin_root,
)


OVERLAY_BACKEND_ENV = "AXIDEV_OSK_OVERLAY_BACKEND"
OVERLAY_DEBUG_ENV = "AXIDEV_OSK_OVERLAY_DEBUG"
TWindow = TypeVar("TWindow", bound=QWidget)


_logger = logging.getLogger(__name__)


class OverlayBackend(str, Enum):
    NATIVE = "native"
    WINDOWS_NATIVE = "windows-native"
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
    manage_position: bool = True


if sys.platform == "win32":
    _GWL_EXSTYLE = -20
    _HWND_TOPMOST = -1
    _SWP_NOMOVE = 0x0002
    _SWP_NOSIZE = 0x0001
    _SWP_NOACTIVATE = 0x0010
    _SWP_FRAMECHANGED = 0x0020
    _SWP_NOOWNERZORDER = 0x0200
    _WS_EX_NOACTIVATE = 0x08000000
    _DWMWA_WINDOW_CORNER_PREFERENCE = 33
    _DWMWA_BORDER_COLOR = 34
    _DWMWCP_DONOTROUND = 1
    _DWMWA_COLOR_NONE = 0xFFFFFFFE

    _user32 = ctypes.windll.user32
    _dwmapi = ctypes.windll.dwmapi
    _get_window_long_ptr = _user32.GetWindowLongPtrW
    _set_window_long_ptr = _user32.SetWindowLongPtrW
    _set_window_pos = _user32.SetWindowPos
    _dwm_set_window_attribute = _dwmapi.DwmSetWindowAttribute

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
    _dwm_set_window_attribute.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    _dwm_set_window_attribute.restype = ctypes.c_long
else:
    _dwm_set_window_attribute = None


def prepare_always_on_top_window_environment(
    *,
    prefer_layer_shell: bool = True,
    prefer_x11_bridge: bool = True,
) -> OverlayBackend:
    if sys.platform == "win32":
        return _set_overlay_backend(OverlayBackend.WINDOWS_NATIVE)

    if not sys.platform.startswith("linux"):
        return _set_overlay_backend(OverlayBackend.NATIVE)

    forced_platforms = _qt_platform_entries(os.environ.get("QT_QPA_PLATFORM", ""))
    if forced_platforms[:1] == ["xcb"]:
        if is_wayland_session():
            return _set_overlay_backend(OverlayBackend.X11_UTILITY_BRIDGE)
        return _set_overlay_backend(OverlayBackend.X11_UTILITY)

    if forced_platforms and "wayland" not in forced_platforms:
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
        _warn_wayland_fallback(
            "Wayland layer-shell support is unavailable; falling back to the X11/XWayland overlay backend."
        )
        return _set_overlay_backend(OverlayBackend.X11_UTILITY_BRIDGE)

    raise RuntimeError(
        "Wayland overlay support requires a compatible Qt layer-shell plugin, and the X11/XWayland fallback backend could not be enabled."
    )


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
        self._layer_shell_anchors = ANCHOR_LEFT | ANCHOR_BOTTOM
        self._layer_shell_margins = QMargins(0, 0, 0, 0)
        self._layer_shell_left_margin = 0
        self._layer_shell_bottom_margin = 0
        self._layer_shell_position_initialized = False
        self._floating_position_initialized = False
        self._show_adjustments_applied = False
        self._layer_shell_startup_refresh_applied = False

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
        self._window.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._window.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)

        if self.uses_custom_chrome:
            self._window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        if self._backend in {OverlayBackend.X11_UTILITY, OverlayBackend.X11_UTILITY_BRIDGE}:
            self._window.setWindowFlag(Qt.WindowType.Tool, True)
            self._window.setAttribute(Qt.WidgetAttribute.WA_X11DoNotAcceptFocus, True)

        self._debug_log(
            "configure-window",
            backend=self._backend.value,
            manage_position=self._config.manage_position,
            placement=self._config.placement.value,
            screen_margin=self._config.screen_margin,
        )

    def handle_show(self) -> bool:
        if self._backend == OverlayBackend.WINDOWS_NATIVE:
            self._apply_windows_window_styles()
            self._position_floating_window_if_needed()
            return True

        if self._backend == OverlayBackend.WAYLAND_LAYER_SHELL:
            applied = self._apply_wayland_layer_shell_if_needed()
            self._refresh_wayland_layer_shell_surface_after_startup()
            return applied

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

    def prepare_show(self) -> bool:
        if self._backend == OverlayBackend.WAYLAND_LAYER_SHELL:
            return self._sync_wayland_layer_shell()
        if self._backend in {OverlayBackend.WINDOWS_NATIVE, OverlayBackend.X11_UTILITY, OverlayBackend.X11_UTILITY_BRIDGE, OverlayBackend.NATIVE}:
            self._position_floating_window_if_needed()
            return True
        return False

    def move_to(self, position: QPoint, *, screen_geometry: QRect | None = None) -> None:
        target = QPoint(position)
        if self._backend == OverlayBackend.WAYLAND_LAYER_SHELL:
            geometry = QRect(screen_geometry) if screen_geometry is not None else self._current_screen_geometry(for_layer_shell=True)
            self._layer_shell_left_margin = target.x() - geometry.x()
            self._layer_shell_bottom_margin = 0
            self._layer_shell_anchors = ANCHOR_LEFT | ANCHOR_TOP
            self._layer_shell_margins = QMargins(
                self._layer_shell_left_margin,
                target.y() - geometry.y(),
                0,
                0,
            )
            self._layer_shell_position_initialized = True
            self._window.move(target)
            self._debug_log(
                "move-to-layer-shell",
                target=target,
                screen_geometry=geometry,
                anchors=self._layer_shell_anchors,
                margins=self._layer_shell_margins,
            )
            self._sync_wayland_layer_shell_with(
                anchors=self._layer_shell_anchors,
                margins=self._layer_shell_margins,
            )
            return

        self._window.move(target)
        self._floating_position_initialized = True

    def move_to_anchored(
        self,
        position: QPoint,
        *,
        anchors: int,
        screen_geometry: QRect | None = None,
    ) -> None:
        if self._backend != OverlayBackend.WAYLAND_LAYER_SHELL:
            self.move_to(position, screen_geometry=screen_geometry)
            return

        target = QPoint(position)
        geometry = QRect(screen_geometry) if screen_geometry is not None else self._current_screen_geometry(for_layer_shell=True)
        left_margin = target.x() - geometry.x() if anchors & ANCHOR_LEFT else 0
        top_margin = target.y() - geometry.y() if anchors & ANCHOR_TOP else 0
        right_margin = geometry.right() - target.x() - self._window.width() + 1 if anchors & ANCHOR_RIGHT else 0
        bottom_margin = geometry.bottom() - target.y() - self._window.height() + 1 if anchors & ANCHOR_BOTTOM else 0

        self._layer_shell_left_margin = left_margin
        self._layer_shell_bottom_margin = bottom_margin
        self._layer_shell_anchors = anchors
        self._layer_shell_margins = QMargins(left_margin, top_margin, right_margin, bottom_margin)
        self._layer_shell_position_initialized = True
        self._window.move(target)
        self._debug_log(
            "move-to-anchored-layer-shell",
            target=target,
            screen_geometry=geometry,
            anchors=self._layer_shell_anchors,
            margins=self._layer_shell_margins,
        )
        self._sync_wayland_layer_shell_with(
            anchors=self._layer_shell_anchors,
            margins=self._layer_shell_margins,
        )

    def move_by(self, dx: int, dy: int) -> None:
        if self._backend == OverlayBackend.WAYLAND_LAYER_SHELL:
            self._move_layer_shell_by(dx, dy)
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
            raise RuntimeError(
                "Wayland overlay backend was initialized without layer-shell support."
            )

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

    def _refresh_wayland_layer_shell_surface_after_startup(self) -> None:
        if self._layer_shell_startup_refresh_applied:
            return
        self._layer_shell_startup_refresh_applied = True
        QTimer.singleShot(0, self._refresh_wayland_layer_shell_surface)

    def _refresh_wayland_layer_shell_surface(self) -> None:
        if self._backend != OverlayBackend.WAYLAND_LAYER_SHELL:
            return
        if not self._window.isVisible():
            return
        self._window.hide()
        self._sync_wayland_layer_shell()
        self._window.show()

    def _sync_wayland_layer_shell(self) -> bool:
        if not self._layer_shell_position_initialized:
            self._initialize_layer_shell_position()

        return self._sync_wayland_layer_shell_with(
            anchors=self._layer_shell_anchors,
            margins=self._layer_shell_margins,
        )

    def _sync_wayland_layer_shell_with(self, *, anchors: int, margins: QMargins) -> bool:
        self._debug_log(
            "apply-layer-shell",
            anchors=anchors,
            margins=margins,
            window_size=(self._window.width(), self._window.height()),
            screen_geometry=self._current_screen_geometry(for_layer_shell=True),
        )
        return apply_wayland_layer_shell(
            self._window,
            anchors=anchors,
            layer=LAYER_OVERLAY,
            keyboard_interactivity=KEYBOARD_INTERACTIVITY_NONE,
            activate_on_show=False,
            wants_to_be_on_active_screen=True,
            exclusion_zone=0,
            margins=margins,
        )

    def _move_layer_shell_by(self, dx: int, dy: int) -> None:
        if not self._layer_shell_position_initialized:
            self._initialize_layer_shell_position()

        self._layer_shell_left_margin += dx
        self._layer_shell_bottom_margin -= dy
        self._layer_shell_anchors = ANCHOR_LEFT | ANCHOR_BOTTOM
        self._layer_shell_margins = QMargins(self._layer_shell_left_margin, 0, 0, self._layer_shell_bottom_margin)
        self._layer_shell_position_initialized = True
        self._debug_log(
            "move-by-layer-shell",
            delta=(dx, dy),
            anchors=self._layer_shell_anchors,
            margins=self._layer_shell_margins,
        )
        self._sync_wayland_layer_shell()

    def _resize_layer_shell_by(self, dx: int, dy: int) -> None:
        if not self._layer_shell_position_initialized:
            self._initialize_layer_shell_position()

        screen_size = self._current_screen_geometry(for_layer_shell=True).size()
        top_offset = max(0, screen_size.height() - self._layer_shell_bottom_margin - self._window.height())
        max_width = max(self._window.minimumWidth(), screen_size.width() - self._layer_shell_left_margin)
        max_height = max(self._window.minimumHeight(), screen_size.height() - top_offset)

        next_width = max(self._window.minimumWidth(), min(self._window.width() + dx, max_width))
        next_height = max(self._window.minimumHeight(), min(self._window.height() + dy, max_height))
        self._layer_shell_bottom_margin = max(
            0,
            min(screen_size.height() - top_offset - next_height, screen_size.height()),
        )
        self._layer_shell_anchors = ANCHOR_LEFT | ANCHOR_BOTTOM
        self._layer_shell_margins = QMargins(self._layer_shell_left_margin, 0, 0, self._layer_shell_bottom_margin)
        self._layer_shell_position_initialized = True
        self._window.resize(next_width, next_height)
        self._debug_log(
            "resize-layer-shell",
            delta=(dx, dy),
            window_size=(next_width, next_height),
            anchors=self._layer_shell_anchors,
            margins=self._layer_shell_margins,
        )
        self._sync_wayland_layer_shell()

    def _initialize_layer_shell_position(self) -> None:
        screen_size = self._current_screen_geometry(for_layer_shell=True).size()

        if self._config.placement == OverlayPlacement.CENTER:
            self._layer_shell_left_margin = (screen_size.width() - self._window.width()) // 2
            self._layer_shell_bottom_margin = (screen_size.height() - self._window.height()) // 2
        else:
            margin = self._config.screen_margin
            self._layer_shell_left_margin = screen_size.width() - self._window.width() - margin
            self._layer_shell_bottom_margin = screen_size.height() - self._window.height() - margin

        self._layer_shell_anchors = ANCHOR_LEFT | ANCHOR_BOTTOM
        self._layer_shell_margins = QMargins(self._layer_shell_left_margin, 0, 0, self._layer_shell_bottom_margin)
        self._layer_shell_position_initialized = True
        self._debug_log(
            "initialize-layer-shell-position",
            anchors=self._layer_shell_anchors,
            margins=self._layer_shell_margins,
            screen_size=(screen_size.width(), screen_size.height()),
        )

    def _position_floating_window_if_needed(self) -> None:
        if self._floating_position_initialized:
            return
        if not self._config.manage_position:
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

    def _current_screen_geometry(self, *, for_layer_shell: bool = False) -> QRect:
        screen = self._window.screen()
        if screen is None:
            app = QGuiApplication.instance()
            screen = app.primaryScreen() if app is not None else None
        if screen is None:
            geometry = None
        elif for_layer_shell:
            geometry = screen.geometry()
        else:
            geometry = screen.availableGeometry()
        if geometry is None:
            return QRect(0, 0, 1920, 1080)
        return geometry

    def _debug_log(self, message: str, **context: object) -> None:
        if not _overlay_debug_enabled():
            return
        details = ", ".join(f"{key}={value!r}" for key, value in context.items())
        _logger.warning("overlay %s: %s", message, details)

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
        self._apply_windows_frameless_chrome(hwnd)

    def _apply_windows_frameless_chrome(self, hwnd: int) -> None:
        if _dwm_set_window_attribute is None:
            return
        if not bool(self._window.windowFlags() & Qt.WindowType.FramelessWindowHint):
            return

        corner_preference = ctypes.c_uint(_DWMWCP_DONOTROUND)
        border_color = ctypes.c_uint(_DWMWA_COLOR_NONE)
        _dwm_set_window_attribute(
            hwnd,
            _DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(corner_preference),
            ctypes.sizeof(corner_preference),
        )
        _dwm_set_window_attribute(
            hwnd,
            _DWMWA_BORDER_COLOR,
            ctypes.byref(border_color),
            ctypes.sizeof(border_color),
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


def _qt_platform_entries(raw_value: str) -> list[str]:
    return [entry.strip().lower() for entry in raw_value.split(";") if entry.strip()]


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


def _overlay_debug_enabled() -> bool:
    return os.environ.get(OVERLAY_DEBUG_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _warn_wayland_fallback(message: str) -> None:
    _logger.warning(message)
