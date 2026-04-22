from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, QPoint, QRect, QRectF, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QApplication, QWidget

from .overlay_window import AlwaysOnTopWindowConfig, configure_always_on_top_window
from ..styles.theme import ThemePalette, build_theme_palette


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
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)

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


class HotCornerWindowToggleController(QObject):
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
        self._entered_at = 0.0
        self._triggered_corner: ScreenCorner | None = None
        self._hidden_windows: list[QWidget] = []
        self._indicator = HotCornerIndicator(
            size_px=self._config.indicator_size_px,
            palette=build_theme_palette(),
        )
        self._indicator_overlay = configure_always_on_top_window(
            self._indicator,
            config=AlwaysOnTopWindowConfig(manage_position=False),
        )

        self._timer = QTimer(self)
        self._timer.setInterval(self._config.poll_interval_ms)
        self._timer.timeout.connect(self._poll_cursor)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._indicator.hide()
        self._reset_corner_tracking()

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

    def _reset_corner_tracking(self) -> None:
        self._active_corner = None
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

        visible_windows = self._visible_top_level_windows()
        if not visible_windows:
            return

        self._hidden_windows = visible_windows
        for window in visible_windows:
            window.hide()

    def _restore_windows(self) -> None:
        windows_to_restore = [window for window in self._hidden_windows if window is not None]
        self._hidden_windows = []
        for window in windows_to_restore:
            if window.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose):
                continue
            window.show()

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

        self._indicator_overlay.move_to(
            self._indicator_position(screen.geometry(), corner),
            screen_geometry=screen.geometry(),
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

    def _visible_top_level_windows(self) -> list[QWidget]:
        visible_windows: list[QWidget] = []
        for window in self._app.topLevelWidgets():
            if not window.isWindow():
                continue
            if not window.isVisible():
                continue
            if window is self._indicator:
                continue
            if window.windowType() == Qt.WindowType.ToolTip:
                continue
            visible_windows.append(window)
        return visible_windows
