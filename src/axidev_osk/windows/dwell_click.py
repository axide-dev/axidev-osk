"""Pointer dwell activation for configured windows."""

from __future__ import annotations

import math
from time import monotonic

from PySide6.QtCore import QObject, QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QPaintEvent,
    QPainter,
    QPalette,
)
from PySide6.QtWidgets import QApplication, QAbstractButton, QWidget

from ..config.models import DwellClickConfig

_POLL_INTERVAL_MS = 16
_INDICATOR_SIZE_PX = 30
_MINIMUM_DOT_SIZE_PX = 4
_MAXIMUM_DOT_SIZE_PX = 24


class DwellClickIndicator(QWidget):
    """Paint growing dwell progress without intercepting pointer input."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._progress = 0.0
        self.setObjectName("dwellClickIndicator")
        self.setProperty("componentType", "dwell-click-indicator")
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(_INDICATOR_SIZE_PX, _INDICATOR_SIZE_PX)
        self.hide()

    @property
    def progress(self) -> float:
        """Return the displayed progress from zero through one."""

        return self._progress

    @property
    def progress_color(self) -> QColor:
        """Return the theme accent used for the progress arc."""

        color = self.palette().color(QPalette.ColorRole.Highlight)
        color.setAlpha(240)
        return color

    def show_progress(self, global_position: QPoint, progress: float) -> None:
        """Place the dot behind a screen point and display its progress."""

        if progress <= 0:
            self.clear()
            return
        parent = self.parentWidget()
        if parent is None:
            return
        center = parent.mapFromGlobal(global_position)
        self.move(
            center.x() - self.width() // 2,
            center.y() - self.height() // 2,
        )
        self._progress = min(1.0, max(0.0, progress))
        self.raise_()
        self.show()
        self.update()

    def clear(self) -> None:
        """Hide the ring and clear its progress."""

        self._progress = 0.0
        self.hide()

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        """Paint a theme-colored dot that grows with dwell progress."""

        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        diameter = _MINIMUM_DOT_SIZE_PX + (
            (_MAXIMUM_DOT_SIZE_PX - _MINIMUM_DOT_SIZE_PX) * self._progress
        )
        inset = (self.width() - diameter) / 2
        bounds = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.progress_color)
        painter.drawEllipse(bounds)


class DwellClickController(QObject):
    """Activate the key exactly under a pointer that has come to rest."""

    def __init__(
        self,
        window: QWidget,
        surface: QWidget,
        config: DwellClickConfig,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._config = config
        self.indicator = DwellClickIndicator(surface)
        self._anchor: QPoint | None = None
        self._clicked_position: QPoint | None = None
        self._target: QAbstractButton | None = None
        self._last_position: QPoint | None = None
        self._last_sample_time = 0.0
        self._progress = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll_cursor)

    def start(self) -> None:
        """Begin sampling while the configured window is visible."""

        if not self._config.enabled or self._timer.isActive():
            return
        self._reset()
        self._timer.start()
        self._poll_cursor()

    def stop(self) -> None:
        """Stop sampling and discard the current dwell."""

        self._timer.stop()
        self._reset()

    def _reset(self) -> None:
        self._anchor = None
        self._clicked_position = None
        self._target = None
        self._last_position = None
        self._last_sample_time = 0.0
        self._progress = 0.0
        self.indicator.clear()

    def _poll_cursor(self) -> None:
        if not self._window.isVisible():
            self.stop()
            return
        self.update_from_global_position(QCursor.pos(), now=monotonic())

    def update_from_global_position(
        self,
        position: QPoint,
        *,
        now: float,
    ) -> None:
        """Consume a pointer sample with a monotonic timestamp in seconds."""

        if self._clicked_position is not None:
            self.indicator.clear()
            if (
                self._distance_squared(position, self._clicked_position)
                <= self._dead_zone_squared
            ):
                return
            self._clicked_position = None
            self._anchor = position
            self._target = self._key_at(position)
            self._last_position = position
            self._last_sample_time = now
            self._progress = 0.0
            return

        target = self._key_at(position)
        if target is None:
            self._anchor = None
            self._target = None
            self._last_position = None
            self._progress = 0.0
            self.indicator.clear()
            return

        if (
            self._anchor is None
            or target is not self._target
            or self._distance_squared(position, self._anchor)
            > self._dead_zone_squared
        ):
            self._anchor = position
            self._target = target
            self._last_position = position
            self._last_sample_time = now
            self._progress = 0.0
            self.indicator.clear()
            return

        elapsed = max(0.0, now - self._last_sample_time)
        previous_position = self._last_position
        distance = (
            math.sqrt(self._distance_squared(position, previous_position))
            if previous_position is not None
            else 0.0
        )
        speed = distance / elapsed if elapsed > 0 else 0.0
        rate = self._progress_rate(speed)
        self._progress += elapsed * 1000 / self._config.delay_ms * rate
        self._last_position = position
        self._last_sample_time = now
        if rate > 0:
            self.indicator.show_progress(position, self._progress)
        else:
            self.indicator.clear()
        if self._progress < 1.0 and not math.isclose(
            self._progress,
            1.0,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            return
        self._progress = 1.0
        target.click()
        self._clicked_position = position
        self._anchor = None
        self._target = None
        self.indicator.clear()

    @property
    def _dead_zone_squared(self) -> int:
        return self._config.dead_zone_px**2

    def _progress_rate(self, speed: float) -> float:
        if speed <= self._config.full_speed_px_s:
            return 1.0
        if speed >= self._config.stop_speed_px_s:
            return 0.0
        speed_range = (
            self._config.stop_speed_px_s - self._config.full_speed_px_s
        )
        return (self._config.stop_speed_px_s - speed) / speed_range

    @staticmethod
    def _distance_squared(first: QPoint, second: QPoint) -> int:
        delta = first - second
        return delta.x() ** 2 + delta.y() ** 2

    def _key_at(self, position: QPoint) -> QAbstractButton | None:
        target = QApplication.widgetAt(position)
        if target is None or target.window() is not self._window:
            return None
        while target is not None and target is not self._window:
            if (
                isinstance(target, QAbstractButton)
                and target.property("componentType") == "key"
                and target.isEnabled()
            ):
                return target
            target = target.parentWidget()
        return None
