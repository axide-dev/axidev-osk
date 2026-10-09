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
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget

from ..config.models import DwellClickConfig

_POLL_INTERVAL_MS = 16
_INDICATOR_SIZE_PX = 30
_MINIMUM_DOT_SIZE_PX = 4
_MAXIMUM_DOT_SIZE_PX = 24
_CANCEL_FADE_DURATION_MS = 250
_DIRECTION_REVERSAL_COSINE = -0.5


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


class _DwellFadeFeedback(QWidget):
    """Fade a dwell dot at its last displayed position."""

    def __init__(
        self,
        parent: QWidget,
        *,
        object_name: str,
        component_type: str,
        color_role: QPalette.ColorRole,
    ) -> None:
        super().__init__(parent)
        self._progress = 0.0
        self._opacity = 0.0
        self._color_role = color_role
        self.setObjectName(object_name)
        self.setProperty("componentType", component_type)
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
        color = self.palette().color(self._color_role)
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

    def __init__(self, parent: QWidget, *, visible_from_progress: float) -> None:
        super().__init__(parent)
        self._progress = 0.0
        self._visible_from_progress = visible_from_progress
        self.setObjectName("dwellClickIndicator")
        self.setProperty("componentType", "dwell-click-indicator")
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(_INDICATOR_SIZE_PX, _INDICATOR_SIZE_PX)
        self.cancel_feedback = _DwellFadeFeedback(
            parent,
            object_name="dwellClickCancelFeedback",
            component_type="dwell-click-cancel-feedback",
            color_role=QPalette.ColorRole.Mid,
        )
        self.complete_feedback = _DwellFadeFeedback(
            parent,
            object_name="dwellClickCompleteFeedback",
            component_type="dwell-click-complete-feedback",
            color_role=QPalette.ColorRole.Highlight,
        )
        self.hide()

    @property
    def progress(self) -> float:
        """Return the displayed progress from zero through one."""

        return self._progress

    @property
    def progress_color(self) -> QColor:
        """Return the theme gray used while dwell progress accumulates."""

        color = self.palette().color(QPalette.ColorRole.Mid)
        color.setAlpha(240)
        return color

    @property
    def track_color(self) -> QColor:
        """Return the translucent gray marking full progress."""

        color = self.palette().color(QPalette.ColorRole.Mid)
        color.setAlpha(130)
        return color

    def show_progress(self, global_position: QPoint, progress: float) -> None:
        """Place the dot behind a screen point and display its progress."""

        if progress < self._visible_from_progress:
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

    def complete(self) -> None:
        """Replace completed progress with a fading full accent dot."""

        self.complete_feedback.show_feedback(self.pos(), 1.0)
        self.clear()

    def clear_all(self) -> None:
        """Clear both active progress and cancellation feedback."""

        self.clear()
        self.cancel_feedback.clear()
        self.complete_feedback.clear()

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        """Paint a gray dot that grows with dwell progress."""

        del event
        _paint_dot(self, 1.0, self.track_color)
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
        self._enabled = config.enabled
        self.indicator = DwellClickIndicator(
            surface,
            visible_from_progress=config.indicator_start_progress,
        )
        self._clicked_position: QPoint | None = None
        self._target: QWidget | None = None
        self._last_position: QPoint | None = None
        self._last_sample_time = 0.0
        self._instantaneous_speed = 0.0
        self._sample_delta = QPoint()
        self._smoothed_speed = 0.0
        self._target_speed: float | None = None
        self._target_direction: QPoint | None = None
        self._deceleration_score = 0.0
        self._travel_distance_since_click: float | None = None
        self._progress = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll_cursor)

    def start(self) -> None:
        """Begin sampling while the configured window is visible."""

        if not self._enabled or self._timer.isActive():
            return
        self._reset()
        self._timer.start()
        self._poll_cursor()

    @property
    def enabled(self) -> bool:
        """Return whether dwell activation is currently enabled."""

        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable dwell activation at runtime."""

        if enabled == self._enabled:
            return
        self._enabled = enabled
        if not enabled:
            self.stop()
            return
        if not self._window.isVisible():
            return
        self._reset()
        self._clicked_position = QCursor.pos()
        self._timer.start()

    def stop(self) -> None:
        """Stop sampling and discard the current dwell."""

        self._timer.stop()
        self._reset()

    def _reset(self) -> None:
        self._clicked_position = None
        self._target = None
        self._last_position = None
        self._last_sample_time = 0.0
        self._instantaneous_speed = 0.0
        self._sample_delta = QPoint()
        self._smoothed_speed = 0.0
        self._target_speed = None
        self._target_direction = None
        self._deceleration_score = 0.0
        self._travel_distance_since_click = None
        self._progress = 0.0
        self.indicator.clear_all()

    def _poll_cursor(self) -> None:
        if not self._window.isVisible():
            self.stop()
            return
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            self._reset()
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
            self._target = self._widget_at(position)
            if self._target is None:
                self._clear_motion()
                return
            self._target_speed = self._instantaneous_speed
            self._target_direction = self._nonzero_sample_delta()
            self._deceleration_score = 0.0
            self._progress = 0.0
            return

        target = self._widget_at(position)
        if target is None:
            self._cancel_current_dwell()
            self._target = None
            self._clear_motion()
            self._progress = 0.0
            return

        elapsed, speed = self._sample_speed(position, now)

        if target is not self._target:
            self._cancel_current_dwell()
            self._target = target
            self._target_speed = self._instantaneous_speed
            self._target_direction = self._nonzero_sample_delta()
            self._deceleration_score = 0.0
            self._progress = 0.0
            return

        self._update_deceleration_score(elapsed)
        self._reduce_progress_on_direction_reversal()
        rate = self._progress_rate(speed)
        self._progress += elapsed * 1000 / self._config.delay_ms * rate
        self._apply_movement_penalty()
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
        self._target = None
        self._travel_distance_since_click = 0.0
        self.indicator.complete()

    def _apply_movement_penalty(self) -> None:
        self._progress = max(
            0.0,
            self._progress
            - math.hypot(self._sample_delta.x(), self._sample_delta.y())
            / self._config.movement_penalty_px,
        )

    def _cancel_current_dwell(self) -> None:
        if self._progress > 0:
            self.indicator.cancel()
        else:
            self.indicator.clear()

    def _clear_motion(self) -> None:
        self._last_position = None
        self._last_sample_time = 0.0
        self._instantaneous_speed = 0.0
        self._sample_delta = QPoint()
        self._smoothed_speed = 0.0
        self._target_speed = None
        self._target_direction = None
        self._deceleration_score = 0.0

    def _sample_speed(
        self,
        position: QPoint,
        now: float,
    ) -> tuple[float, float]:
        elapsed = max(0.0, now - self._last_sample_time)
        previous_position = self._last_position
        self._sample_delta = (
            position - previous_position
            if previous_position is not None
            else QPoint()
        )
        distance = math.hypot(self._sample_delta.x(), self._sample_delta.y())
        if self._travel_distance_since_click is not None:
            self._travel_distance_since_click += distance
        instantaneous_speed = distance / elapsed if elapsed > 0 else 0.0
        self._instantaneous_speed = instantaneous_speed
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

    def _update_deceleration_score(self, elapsed: float) -> None:
        previous_speed = self._target_speed
        current_speed = self._instantaneous_speed
        self._target_speed = current_speed
        if previous_speed is None or elapsed <= 0:
            return

        speed_change = previous_speed - current_speed
        speed_range = self._config.stop_speed_px_s - self._config.full_speed_px_s
        if speed_change > 0 and current_speed > 0:
            maximum_gradual_drop = (
                self._config.stop_speed_px_s
                * elapsed
                * 1000
                / self._config.velocity_release_ms
            )
            credited_drop = min(speed_change, maximum_gradual_drop)
            self._deceleration_score = min(
                1.0,
                self._deceleration_score + credited_drop / speed_range,
            )
        elif speed_change < 0:
            self._deceleration_score = max(
                0.0,
                self._deceleration_score + speed_change / speed_range,
            )

    def _reduce_progress_on_direction_reversal(self) -> None:
        current_direction = self._nonzero_sample_delta()
        if current_direction is None:
            return
        previous_direction = self._target_direction
        self._target_direction = current_direction
        if previous_direction is None:
            return

        dot_product = QPoint.dotProduct(previous_direction, current_direction)
        magnitude_product = math.sqrt(
            self._distance_squared(previous_direction, QPoint())
            * self._distance_squared(current_direction, QPoint())
        )
        if dot_product > _DIRECTION_REVERSAL_COSINE * magnitude_product:
            return
        factor = self._config.direction_reversal_progress_factor
        self._progress *= factor
        self._deceleration_score *= factor

    def _nonzero_sample_delta(self) -> QPoint | None:
        if self._sample_delta.isNull():
            return None
        return self._sample_delta

    @property
    def _dead_zone_squared(self) -> int:
        return self._config.dead_zone_px**2

    def _progress_rate(self, speed: float) -> float:
        if speed >= self._config.stop_speed_px_s:
            return 0.0
        if speed <= self._config.full_speed_px_s:
            base_rate = 1.0
        else:
            speed_range = (
                self._config.stop_speed_px_s - self._config.full_speed_px_s
            )
            base_rate = (
                self._config.stop_speed_px_s - speed
            ) / speed_range
        score_exponent = 0.5
        if self._travel_distance_since_click is not None:
            distance_ratio = min(
                1.0,
                self._travel_distance_since_click
                / self._config.distance_curve_full_px,
            )
            score_exponent = 0.25 + 0.25 * distance_ratio
        acceleration = 1 + (
            (self._config.maximum_progress_rate - 1)
            * self._deceleration_score**score_exponent
        )
        return base_rate * acceleration

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
        if isinstance(target, QAbstractButton):
            target.animateClick()
            return

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
