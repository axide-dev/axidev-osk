"""Non-interactive color feedback around a pointer inside a window.

The glow takes the ``locator_color`` of the widget under the pointer, and the
attachment's ``gap_color`` anywhere else. Which widget gets which color is the
profile's choice; the standard library's ``std.locator`` gives the usual
pattern.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QPaintEvent, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from ..config.models import PointerLocatorConfig
from ..widget_properties import COMPONENT_ID, COMPONENT_TYPE, LOCATOR_COLOR, POINTER_LOCATOR_ENABLED
from ..windows.surface import RootSurface

_GRADIENT_SEGMENTS = 32


def install_pointer_locator(host: RootSurface, settings: PointerLocatorConfig) -> "PointerLocator":
    """Install pointer feedback behind a root surface's content."""

    host.setProperty(POINTER_LOCATOR_ENABLED, True)
    locator = PointerLocator(settings, host)
    host.install_background_component(locator)
    return locator


def gaussian_opacity(
    normalized_distance: float,
    *,
    maximum_opacity: float,
    radius_standard_deviations: float,
) -> float:
    """Return a truncated Gaussian opacity from the center through the radius."""

    distance = min(1.0, max(0.0, normalized_distance))
    edge = math.exp(-0.5 * radius_standard_deviations**2)
    value = math.exp(-0.5 * (radius_standard_deviations * distance) ** 2)
    normalized = max(0.0, (value - edge) / (1.0 - edge))
    return maximum_opacity * normalized


class PointerLocator(QWidget):
    """Paint a mouse-transparent radial color glow around the host pointer."""

    def __init__(self, config: PointerLocatorConfig, parent: QWidget) -> None:
        super().__init__(parent)
        self._host = parent
        self._config = config
        self._color = QColor.fromHsvF(0.0, 1.0, 1.0)
        self._cursor_position = QPoint()
        self._pointer_inside = False

        self.setObjectName("pointerLocator")
        self.setProperty(COMPONENT_TYPE, "pointer-locator")
        self.setProperty(COMPONENT_ID, config.id)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(parent.rect())
        self.hide()

        self._timer = QTimer(self)
        self._timer.setInterval(config.poll_interval_ms)
        self._timer.timeout.connect(self._poll_cursor)
        self._host.installEventFilter(self)

    def set_settings(self, config: PointerLocatorConfig) -> None:
        """Paint with new glow settings from the next frame on."""

        self._config = config
        self._timer.setInterval(config.poll_interval_ms)
        self.update()

    @property
    def current_color(self) -> QColor:
        """Return the color currently painted by the glow."""

        return QColor(self._color)

    @property
    def radius(self) -> float:
        """Return the current glow radius in surface pixels."""

        return min(self._host.width(), self._host.height()) * self._config.radius_percent / 100.0

    def _poll_cursor(self) -> None:
        if not self._pointer_inside:
            self._timer.stop()
            self.hide()
            return
        self.update_from_global_position(QCursor.pos())

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """Use real window boundary events instead of stale Wayland coordinates."""

        host = getattr(self, "_host", None)
        if watched is host:
            if event.type() == QEvent.Type.Enter:
                self._pointer_inside = True
                self._timer.start()
                self._poll_cursor()
            elif event.type() in {QEvent.Type.Leave, QEvent.Type.Hide}:
                self._pointer_inside = False
                self._timer.stop()
                self.hide()
        return super().eventFilter(watched, event)

    def update_from_global_position(self, global_position: QPoint) -> None:
        """Update ring visibility, position, and color from a screen point."""

        if not self._host.isVisible():
            self._timer.stop()
            self.hide()
            return

        local_position = self._host.mapFromGlobal(global_position)
        if not self._host.rect().contains(local_position):
            self.hide()
            return

        color = self._color_at(local_position)
        self._color = QColor(color if color is not None else self._config.gap_color)
        self._cursor_position = local_position
        if self.geometry() != self._host.rect():
            self.setGeometry(self._host.rect())
        self.update()
        self.show()

    def _color_at(self, local_position: QPoint) -> str | None:
        """The locator color of the colored widget under a point of the host, if any."""

        for widget in self._host.findChildren(QWidget):
            color = widget.property(LOCATOR_COLOR)
            if not color or not widget.isVisibleTo(self._host):
                continue
            if QRect(widget.mapTo(self._host, QPoint()), widget.size()).contains(local_position):
                return str(color)
        return None

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        """Paint the configured Gaussian glow behind surface controls."""

        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gradient = QRadialGradient(QPointF(self._cursor_position), self.radius)
        maximum_opacity = self._config.maximum_opacity_percent / 100.0
        for segment in range(_GRADIENT_SEGMENTS + 1):
            position = segment / _GRADIENT_SEGMENTS
            color = QColor(self._color)
            color.setAlphaF(
                gaussian_opacity(
                    position,
                    maximum_opacity=maximum_opacity,
                    radius_standard_deviations=self._config.radius_standard_deviations,
                )
            )
            gradient.setColorAt(position, color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRect(self.rect())
