"""Pointer dwell activation for configured windows."""

from __future__ import annotations

import math
from time import monotonic

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPalette,
)
from PySide6.QtWidgets import QApplication, QWidget

from ..config.models import DwellClickConfig

_POLL_INTERVAL_MS = 16
_INDICATOR_SIZE_PX = 30
_MINIMUM_DOT_SIZE_PX = 4
_MAXIMUM_DOT_SIZE_PX = 24
_CANCEL_FADE_DURATION_MS = 250


def _paint_dot(widget: QWidget, progress: float, color: QColor) -> None:
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    diameter = _MINIMUM_DOT_SIZE_PX + (
        (_MAXIMUM_DOT_SIZE_PX - _MINIMUM_DOT_SIZE_PX) * progress
    )
    inset = (widget.width() - diameter) / 2
    bounds = QRectF(widget.rect()).adjusted(inset, inset, -inset, -inset)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(bounds)


class _DwellCancelFeedback(QWidget):
    """Fade an abandoned dwell dot at its last displayed position."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._progress = 0.0
        self._opacity = 0.0
        self.setObjectName("dwellClickCancelFeedback")
        self.setProperty("componentType", "dwell-click-cancel-feedback")
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(_INDICATOR_SIZE_PX, _INDICATOR_SIZE_PX)
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(_CANCEL_FADE_DURATION_MS)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.valueChanged.connect(self._set_opacity)
        self._fade.finished.connect(self.clear)
        self.hide()

    @property
    def feedback_color(self) -> QColor:
        color = self.palette().color(QPalette.ColorRole.Mid)
        color.setAlpha(round(240 * self._opacity))
        return color

    def show_feedback(self, position: QPoint, progress: float) -> None:
        self._fade.stop()
        self.move(position)
        self._progress = progress
        self._opacity = 1.0
        self.raise_()
        self.show()
        self.update()
        self._fade.start()

    def clear(self) -> None:
        self._fade.stop()
        self._progress = 0.0
        self._opacity = 0.0
        self.hide()

    def _set_opacity(self, value: object) -> None:
        self._opacity = float(value)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        del event
        _paint_dot(self, self._progress, self.feedback_color)


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
        self.cancel_feedback = _DwellCancelFeedback(parent)
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

    def hide_progress(self) -> None:
        """Hide paused progress while retaining its last visible state."""

        self.hide()

    def cancel(self) -> None:
        """Replace current progress with fading cancellation feedback."""

        if self._progress > 0:
            self.cancel_feedback.show_feedback(self.pos(), self._progress)
        self.clear()

    def clear_all(self) -> None:
        """Clear both active progress and cancellation feedback."""

        self.clear()
        self.cancel_feedback.clear()

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        """Paint a theme-colored dot that grows with dwell progress."""

        del event
        _paint_dot(self, self._progress, self.progress_color)


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
        self._last_position: QPoint | None = None
        self._last_sample_time = 0.0
        self._smoothed_speed = 0.0
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
        self._last_position = None
        self._last_sample_time = 0.0
        self._smoothed_speed = 0.0
        self._progress = 0.0
        self.indicator.clear_all()

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
            self._sample_speed(position, now)
            if (
                self._distance_squared(position, self._clicked_position)
                <= self._dead_zone_squared
            ):
                return
            self._clicked_position = None
            self._anchor = position
            if self._widget_at(position) is None:
                self._anchor = None
                self._clear_motion()
                return
            self._progress = 0.0
            return

        target = self._widget_at(position)
        if target is None:
            self._cancel_current_dwell()
            self._anchor = None
            self._clear_motion()
            self._progress = 0.0
            return

        elapsed, speed = self._sample_speed(position, now)

        if (
            self._anchor is None
            or self._distance_squared(position, self._anchor)
            > self._dead_zone_squared
        ):
            self._cancel_current_dwell()
            self._anchor = position
            self._progress = 0.0
            return

        rate = self._progress_rate(speed)
        self._progress += elapsed * 1000 / self._config.delay_ms * rate
        if rate > 0:
            self.indicator.show_progress(position, self._progress)
        else:
            self.indicator.hide_progress()
        if self._progress < 1.0 and not math.isclose(
            self._progress,
            1.0,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            return
        self._progress = 1.0
        self._click_at(position, target)
        self._clicked_position = position
        self._anchor = None
        self.indicator.clear()

    def _cancel_current_dwell(self) -> None:
        if self._progress > 0:
            self.indicator.cancel()
        else:
            self.indicator.clear()

    def _clear_motion(self) -> None:
        self._last_position = None
        self._last_sample_time = 0.0
        self._smoothed_speed = 0.0

    def _sample_speed(
        self,
        position: QPoint,
        now: float,
    ) -> tuple[float, float]:
        elapsed = max(0.0, now - self._last_sample_time)
        previous_position = self._last_position
        distance = (
            math.sqrt(self._distance_squared(position, previous_position))
            if previous_position is not None
            else 0.0
        )
        instantaneous_speed = distance / elapsed if elapsed > 0 else 0.0
        release_per_second = (
            self._config.stop_speed_px_s
            * 1000
            / self._config.velocity_release_ms
        )
        decayed_speed = max(
            0.0,
            self._smoothed_speed - release_per_second * elapsed,
        )
        self._smoothed_speed = max(
            min(instantaneous_speed, self._config.stop_speed_px_s),
            decayed_speed,
        )
        self._last_position = position
        self._last_sample_time = now
        return elapsed, self._smoothed_speed

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

    def _widget_at(self, position: QPoint) -> QWidget | None:
        target = QApplication.widgetAt(position)
        if target is None or target.window() is not self._window:
            return None
        return target

    def _click_at(self, position: QPoint, target: QWidget) -> None:
        local_position = QPointF(target.mapFromGlobal(position))
        window_position = QPointF(self._window.mapFromGlobal(position))
        global_position = QPointF(position)
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            local_position,
            window_position,
            global_position,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            local_position,
            window_position,
            global_position,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(target, press)
        QApplication.sendEvent(target, release)
