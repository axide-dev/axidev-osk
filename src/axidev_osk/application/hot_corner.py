from __future__ import annotations

import os
import time
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QMargins, QObject, QPoint, QRect, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPaintEvent, QPen, QScreen
from PySide6.QtWidgets import QApplication, QWidget

from .layer_shell import (
    ANCHOR_BOTTOM,
    ANCHOR_LEFT,
    ANCHOR_TOP,
    KEYBOARD_INTERACTIVITY_NONE,
    LAYER_OVERLAY,
    apply_wayland_layer_shell,
)
from .overlay_window import OVERLAY_BACKEND_ENV, OverlayBackend
from ..styles.theme import ThemePalette, build_theme_palette


def _configure_hot_corner_window(window: QWidget, *, accepts_input: bool) -> None:
    window.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    window.setWindowFlag(Qt.WindowType.Tool, True)
    window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    window.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    window.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
    if not accepts_input:
        window.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)


def configure_hot_corner_overlay(window: QWidget) -> "HotCornerOverlayController":
    controller = HotCornerOverlayController(window)
    controller.configure_window()
    return controller


class HotCornerOverlayController:
    def __init__(self, window: QWidget) -> None:
        self._window = window
        self._backend = self._detect_backend()
        self._layer_shell_attempts = 0
        self._layer_shell_anchors = ANCHOR_LEFT | ANCHOR_BOTTOM
        self._layer_shell_margins = QMargins(0, 0, 0, 0)
        self._layer_shell_position_initialized = False

    @property
    def backend(self) -> OverlayBackend:
        return self._backend

    def configure_window(self) -> None:
        self._window.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._window.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._window.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)

        if self._backend in {
            OverlayBackend.WAYLAND_LAYER_SHELL,
            OverlayBackend.X11_UTILITY,
            OverlayBackend.X11_UTILITY_BRIDGE,
        }:
            self._window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        if self._backend in {OverlayBackend.X11_UTILITY, OverlayBackend.X11_UTILITY_BRIDGE}:
            self._window.setWindowFlag(Qt.WindowType.Tool, True)
            self._window.setAttribute(Qt.WidgetAttribute.WA_X11DoNotAcceptFocus, True)

    def move_to(self, position: QPoint, *, screen_geometry: QRect | None = None) -> None:
        target = QPoint(position)
        if self._backend == OverlayBackend.WAYLAND_LAYER_SHELL:
            geometry = QRect(screen_geometry) if screen_geometry is not None else self._current_screen_geometry()
            self._layer_shell_anchors = ANCHOR_LEFT | ANCHOR_TOP
            self._layer_shell_margins = QMargins(
                target.x() - geometry.x(),
                target.y() - geometry.y(),
                0,
                0,
            )
            self._layer_shell_position_initialized = True
            self._window.move(target)
            self._sync_wayland_layer_shell()
            return

        self._window.move(target)

    def handle_show(self) -> bool:
        if self._backend == OverlayBackend.WAYLAND_LAYER_SHELL:
            return self._apply_wayland_layer_shell_if_needed()
        return True

    def _detect_backend(self) -> OverlayBackend:
        platform = QGuiApplication.platformName().lower() if QGuiApplication.instance() is not None else ""
        selected = _read_hot_corner_backend()
        if platform == "wayland" and selected == OverlayBackend.WAYLAND_LAYER_SHELL:
            return selected
        if platform == "xcb":
            return OverlayBackend.X11_UTILITY_BRIDGE if selected == OverlayBackend.X11_UTILITY_BRIDGE else OverlayBackend.X11_UTILITY
        return selected or OverlayBackend.NATIVE

    def _apply_wayland_layer_shell_if_needed(self) -> bool:
        if self._sync_wayland_layer_shell():
            return True
        if self._layer_shell_attempts < 5:
            self._layer_shell_attempts += 1
            QTimer.singleShot(50, self._apply_wayland_layer_shell_if_needed)
        return False

    def _sync_wayland_layer_shell(self) -> bool:
        if not self._layer_shell_position_initialized:
            self._layer_shell_position_initialized = True
        return apply_wayland_layer_shell(
            self._window,
            anchors=self._layer_shell_anchors,
            layer=LAYER_OVERLAY,
            keyboard_interactivity=KEYBOARD_INTERACTIVITY_NONE,
            activate_on_show=False,
            wants_to_be_on_active_screen=True,
            exclusion_zone=0,
            margins=self._layer_shell_margins,
        )

    def _current_screen_geometry(self) -> QRect:
        screen = self._window.screen()
        if screen is None:
            app = QGuiApplication.instance()
            screen = app.primaryScreen() if app is not None else None
        if screen is None:
            return QRect(0, 0, 1920, 1080)
        return screen.geometry()


def _read_hot_corner_backend() -> OverlayBackend | None:
    raw_value = os.environ.get(OVERLAY_BACKEND_ENV, "")
    if not raw_value:
        return None
    try:
        return OverlayBackend(raw_value)
    except ValueError:
        return None


@dataclass(slots=True)
class HotCornerConfig:
    dwell_ms: int = 450
    poll_interval_ms: int = 25
    corner_size_px: int = 20
    indicator_size_px: int = 52
    indicator_margin_px: int = 14


class ScreenCorner(str, Enum):
    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"


@dataclass(slots=True)
class HotCornerSensorHandle:
    corner: ScreenCorner
    screen: QScreen
    window: "HotCornerSensorWindow"
    overlay: object


@dataclass(slots=True)
class HiddenWindowState:
    window: QWidget
    opacity: float


class HotCornerIndicator(QWidget):
    def __init__(
        self,
        *,
        size_px: int,
        palette: ThemePalette,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._progress = 0.0
        self._palette = palette

        self.setFixedSize(QSize(size_px, size_px))
        _configure_hot_corner_window(self, accepts_input=False)

    def set_progress(self, progress: float) -> None:
        clamped_progress = max(0.0, min(progress, 1.0))
        if abs(clamped_progress - self._progress) < 0.001:
            return
        self._progress = clamped_progress
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        bounds = QRectF(6, 6, self.width() - 12, self.height() - 12)
        center_bounds = QRectF(16, 16, self.width() - 32, self.height() - 32)
        shell_fill = QColor(self._palette.shell_fill)
        shell_fill.setAlpha(220)
        shell_edge = QColor(self._palette.shell_edge)
        shell_edge.setAlpha(180)
        active_edge = QColor(self._palette.active_edge)
        active_edge.setAlpha(235)
        active_fill = QColor(self._palette.active_fill)
        active_fill.setAlpha(105 + int(90 * self._progress))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shell_fill)
        painter.drawEllipse(QRectF(2, 2, self.width() - 4, self.height() - 4))

        track_pen = QPen(shell_edge, 4)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(bounds)

        progress_pen = QPen(active_edge, 5)
        progress_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(progress_pen)
        painter.drawArc(bounds, 90 * 16, int(-360 * self._progress * 16))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(active_fill)
        painter.drawEllipse(center_bounds)


class HotCornerSensorWindow(QWidget):
    entered = Signal()
    left = Signal()

    def __init__(self, *, size_px: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(QSize(size_px, size_px))
        _configure_hot_corner_window(self, accepts_input=True)

    def enterEvent(self, event: object) -> None:
        del event
        self.entered.emit()

    def leaveEvent(self, event: object) -> None:
        del event
        self.left.emit()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event


class HotCornerWindowToggleController(QObject):
    _WINDOW_REVEAL_DELAY_MS = 16

    def __init__(
        self,
        app: QApplication,
        *,
        config: HotCornerConfig | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._app = app
        self._config = config or HotCornerConfig()
        self._active_corner: ScreenCorner | None = None
        self._active_screen: QScreen | None = None
        self._entered_at = 0.0
        self._triggered_corner: ScreenCorner | None = None
        self._hidden_windows: list[HiddenWindowState] = []
        self._pending_restore_windows: list[HiddenWindowState] = []
        self._indicator = HotCornerIndicator(
            size_px=self._config.indicator_size_px,
            palette=build_theme_palette(),
        )
        self._indicator_overlay = configure_hot_corner_overlay(self._indicator)
        self._sensor_handles: list[HotCornerSensorHandle] = []
        self._use_sensor_windows = self._indicator_overlay.backend in {
            OverlayBackend.WAYLAND_LAYER_SHELL,
            OverlayBackend.X11_UTILITY_BRIDGE,
        }
        if self._use_sensor_windows:
            self._sensor_handles = self._create_sensor_handles()

        self._timer = QTimer(self)
        self._timer.setInterval(self._config.poll_interval_ms)
        self._timer.timeout.connect(self._poll)
        self._restore_timer = QTimer(self)
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self._finalize_restored_windows)

    def start(self) -> None:
        self._show_sensor_windows()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._restore_timer.stop()
        self._indicator.hide()
        self._hide_sensor_windows()
        self._reset_corner_tracking()

    def _poll(self) -> None:
        if self._use_sensor_windows:
            self._poll_active_sensor()
            return
        self._poll_cursor()

    def _poll_cursor(self) -> None:
        cursor_pos = QCursor.pos()
        corner = self._detect_corner(cursor_pos)
        if corner is None:
            self._indicator.hide()
            self._reset_corner_tracking()
            return

        now = time.monotonic()
        if corner != self._active_corner:
            self._active_corner = corner
            self._entered_at = now
            self._triggered_corner = None
            self._show_indicator(corner, cursor_pos, 0.0)
            return

        if self._triggered_corner == corner:
            self._indicator.hide()
            return

        elapsed_ms = (now - self._entered_at) * 1000
        progress = elapsed_ms / max(1, self._config.dwell_ms)
        self._show_indicator(corner, cursor_pos, progress)
        if elapsed_ms < self._config.dwell_ms:
            return

        self._triggered_corner = corner
        self._indicator.hide()
        self._toggle_app_windows()

    def _poll_active_sensor(self) -> None:
        if self._active_corner is None or self._active_screen is None:
            self._indicator.hide()
            return

        now = time.monotonic()
        if self._triggered_corner == self._active_corner:
            self._indicator.hide()
            return

        elapsed_ms = (now - self._entered_at) * 1000
        progress = elapsed_ms / max(1, self._config.dwell_ms)
        self._show_indicator_for_screen(self._active_corner, self._active_screen, progress)
        if elapsed_ms < self._config.dwell_ms:
            return

        self._triggered_corner = self._active_corner
        self._indicator.hide()
        self._toggle_app_windows()

    def _reset_corner_tracking(self) -> None:
        self._active_corner = None
        self._active_screen = None
        self._entered_at = 0.0
        self._triggered_corner = None

    def _detect_corner(self, cursor_pos: QPoint) -> ScreenCorner | None:
        screen = QGuiApplication.screenAt(cursor_pos)
        if screen is None:
            app = QGuiApplication.instance()
            screen = app.primaryScreen() if app is not None else None
        if screen is None:
            return None

        geometry = screen.geometry()
        corner_size = max(1, self._config.corner_size_px)
        x = cursor_pos.x()
        y = cursor_pos.y()

        in_left = x <= geometry.left() + corner_size - 1
        in_right = x >= geometry.right() - corner_size + 1
        in_top = y <= geometry.top() + corner_size - 1
        in_bottom = y >= geometry.bottom() - corner_size + 1

        if in_left and in_top:
            return ScreenCorner.TOP_LEFT
        if in_right and in_top:
            return ScreenCorner.TOP_RIGHT
        if in_left and in_bottom:
            return ScreenCorner.BOTTOM_LEFT
        if in_right and in_bottom:
            return ScreenCorner.BOTTOM_RIGHT
        return None

    def _toggle_app_windows(self) -> None:
        if self._hidden_windows:
            self._restore_windows()
            return
        if self._pending_restore_windows:
            self._rehide_pending_restore_windows()
            return

        visible_windows = self._visible_top_level_windows()
        if not visible_windows:
            return

        self._hidden_windows = [
            HiddenWindowState(window=window, opacity=window.windowOpacity())
            for window in visible_windows
        ]
        for window in visible_windows:
            window.hide()

    def _restore_windows(self) -> None:
        windows_to_restore = [state for state in self._hidden_windows if state.window is not None]
        self._hidden_windows = []
        self._pending_restore_windows = []
        for state in windows_to_restore:
            window = state.window
            if window.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose):
                continue
            window.setWindowOpacity(0.0)
            window.show()
            self._pending_restore_windows.append(state)
        if self._pending_restore_windows:
            self._restore_timer.start(self._WINDOW_REVEAL_DELAY_MS)

    def _finalize_restored_windows(self) -> None:
        windows_to_finalize = self._pending_restore_windows
        self._pending_restore_windows = []
        for state in windows_to_finalize:
            window = state.window
            if window.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose):
                continue
            if not window.isVisible():
                continue
            window.setWindowOpacity(state.opacity)

    def _rehide_pending_restore_windows(self) -> None:
        self._restore_timer.stop()
        windows_to_hide = self._pending_restore_windows
        self._pending_restore_windows = []
        self._hidden_windows = []
        for state in windows_to_hide:
            window = state.window
            if window.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose):
                continue
            window.hide()
            self._hidden_windows.append(state)

    def _show_indicator(
        self,
        corner: ScreenCorner,
        cursor_pos: QPoint,
        progress: float,
    ) -> None:
        screen = QGuiApplication.screenAt(cursor_pos)
        if screen is None:
            app = QGuiApplication.instance()
            screen = app.primaryScreen() if app is not None else None
        if screen is None:
            self._indicator.hide()
            return

        self._show_indicator_for_screen(corner, screen, progress)

    def _show_indicator_for_screen(
        self,
        corner: ScreenCorner,
        screen: QScreen,
        progress: float,
    ) -> None:
        geometry = screen.geometry()
        self._indicator_overlay.move_to(
            self._indicator_position(geometry, corner),
            screen_geometry=geometry,
        )
        self._indicator.set_progress(progress)
        if not self._indicator.isVisible():
            self._indicator.show()
        self._indicator_overlay.handle_show()

    def _indicator_position(self, geometry: QRect, corner: ScreenCorner) -> QPoint:
        size = self._config.indicator_size_px
        margin = self._config.indicator_margin_px

        if corner == ScreenCorner.TOP_LEFT:
            return QPoint(geometry.left() + margin, geometry.top() + margin)
        if corner == ScreenCorner.TOP_RIGHT:
            return QPoint(geometry.right() - size - margin + 1, geometry.top() + margin)
        if corner == ScreenCorner.BOTTOM_LEFT:
            return QPoint(geometry.left() + margin, geometry.bottom() - size - margin + 1)
        return QPoint(geometry.right() - size - margin + 1, geometry.bottom() - size - margin + 1)

    def _sensor_position(self, geometry: QRect, corner: ScreenCorner) -> QPoint:
        size = max(1, self._config.corner_size_px)

        if corner == ScreenCorner.TOP_LEFT:
            return QPoint(geometry.left(), geometry.top())
        if corner == ScreenCorner.TOP_RIGHT:
            return QPoint(geometry.right() - size + 1, geometry.top())
        if corner == ScreenCorner.BOTTOM_LEFT:
            return QPoint(geometry.left(), geometry.bottom() - size + 1)
        return QPoint(geometry.right() - size + 1, geometry.bottom() - size + 1)

    def _create_sensor_handles(self) -> list[HotCornerSensorHandle]:
        handles: list[HotCornerSensorHandle] = []
        for screen in self._app.screens():
            for corner in ScreenCorner:
                sensor_window = HotCornerSensorWindow(size_px=self._config.corner_size_px)
                overlay = configure_hot_corner_overlay(sensor_window)
                handle = HotCornerSensorHandle(
                    corner=corner,
                    screen=screen,
                    window=sensor_window,
                    overlay=overlay,
                )
                sensor_window.entered.connect(lambda handle=handle: self._sensor_entered(handle))
                sensor_window.left.connect(lambda handle=handle: self._sensor_left(handle))
                screen.geometryChanged.connect(lambda _geometry, handle=handle: self._position_sensor_window(handle))
                self._position_sensor_window(handle)
                handles.append(handle)
        return handles

    def _show_sensor_windows(self) -> None:
        for handle in self._sensor_handles:
            self._position_sensor_window(handle)
            if not handle.window.isVisible():
                handle.window.show()
            handle.overlay.handle_show()

    def _hide_sensor_windows(self) -> None:
        for handle in self._sensor_handles:
            handle.window.hide()

    def _position_sensor_window(self, handle: HotCornerSensorHandle) -> None:
        geometry = handle.screen.geometry()
        handle.overlay.move_to(
            self._sensor_position(geometry, handle.corner),
            screen_geometry=geometry,
        )

    def _sensor_entered(self, handle: HotCornerSensorHandle) -> None:
        if self._triggered_corner == handle.corner and self._active_screen is handle.screen:
            return

        self._active_corner = handle.corner
        self._active_screen = handle.screen
        self._entered_at = time.monotonic()
        self._triggered_corner = None
        self._show_indicator_for_screen(handle.corner, handle.screen, 0.0)

    def _sensor_left(self, handle: HotCornerSensorHandle) -> None:
        if self._active_corner != handle.corner or self._active_screen is not handle.screen:
            return
        self._indicator.hide()
        self._reset_corner_tracking()

    def _visible_top_level_windows(self) -> list[QWidget]:
        sensor_windows = {handle.window for handle in self._sensor_handles}
        visible_windows: list[QWidget] = []
        for window in self._app.topLevelWidgets():
            if not window.isWindow():
                continue
            if not window.isVisible():
                continue
            if window is self._indicator:
                continue
            if window in sensor_windows:
                continue
            if window.windowType() == Qt.WindowType.ToolTip:
                continue
            visible_windows.append(window)
        return visible_windows
