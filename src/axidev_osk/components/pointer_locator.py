"""Non-interactive color feedback around a pointer inside a window."""

from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QPaintEvent, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from ..config.models import ComponentConfig, PointerLocatorConfig
from ..runtime.context import Context
from ..runtime.registries import ComponentRegistry

_GRADIENT_SEGMENTS = 32


def register(registry: ComponentRegistry) -> None:
    """Register the pointer locator as a reusable background component."""

    registry.register("pointer-locator", build_pointer_locator_component)


def build_pointer_locator_component(
    config: ComponentConfig,
    context: Context,
    *,
    host: QWidget | None = None,
) -> QWidget:
    """Build pointer feedback for a root surface background."""

    del context
    if not isinstance(config, PointerLocatorConfig):
        raise TypeError(f"Expected PointerLocatorConfig, got {type(config).__name__}")
    if host is None:
        raise RuntimeError("Pointer locator components require a root surface host")

    host.setProperty("pointerLocatorEnabled", True)
    return PointerLocator(config, host)


def _circular_distance(first: int, second: int, count: int) -> int:
    distance = abs(first - second) % count
    return min(distance, count - distance)


def _palette_stride(rows: int, columns: int) -> int:
    """Choose a wheel traversal that separates both grid axes."""

    count = rows * columns
    if count == 1:
        return 1

    best_stride = 1
    best_score = (-1, -1)
    for stride in range(1, count):
        if math.gcd(stride, count) != 1:
            continue
        distances: list[int] = []
        weighted_distance = 0
        if columns > 1:
            horizontal = _circular_distance(0, stride, count)
            distances.append(horizontal)
            weighted_distance += horizontal * rows * (columns - 1)
        if rows > 1:
            vertical = _circular_distance(0, columns * stride, count)
            distances.append(vertical)
            weighted_distance += vertical * columns * (rows - 1)
        score = (min(distances), weighted_distance)
        if score > best_score:
            best_stride = stride
            best_score = score
    return best_stride


def build_pointer_palette(rows: int, columns: int) -> tuple[QColor, ...]:
    """Build a deterministic saturated hue wheel arranged for a 2D grid."""

    if rows <= 0 or columns <= 0:
        raise ValueError("Pointer palette rows and columns must be positive")
    count = rows * columns
    stride = _palette_stride(rows, columns)
    return tuple(
        QColor.fromHsvF(((position * stride) % count) / count, 1.0, 1.0)
        for position in range(count)
    )


def interpolate_pointer_color(
    palette: tuple[QColor, ...],
    *,
    rows: int,
    columns: int,
    x: float,
    y: float,
    width: float,
    height: float,
) -> QColor:
    """Interpolate the four nearest color-region centers at one position."""

    if len(palette) != rows * columns:
        raise ValueError("Pointer palette size must match rows and columns")
    if width <= 0 or height <= 0:
        return QColor(palette[0])

    grid_x = min(columns - 1.0, max(0.0, x * columns / width - 0.5))
    grid_y = min(rows - 1.0, max(0.0, y * rows / height - 0.5))
    left = int(math.floor(grid_x))
    top = int(math.floor(grid_y))
    right = min(columns - 1, left + 1)
    bottom = min(rows - 1, top + 1)
    x_weight = grid_x - left
    y_weight = grid_y - top

    top_color = _mix_color(palette[top * columns + left], palette[top * columns + right], x_weight)
    bottom_color = _mix_color(
        palette[bottom * columns + left],
        palette[bottom * columns + right],
        x_weight,
    )
    return _mix_color(top_color, bottom_color, y_weight)


def _mix_color(first: QColor, second: QColor, weight: float) -> QColor:
    if weight <= 0.0:
        return QColor(first)
    if weight >= 1.0:
        return QColor(second)
    inverse = 1.0 - weight
    return QColor.fromRgbF(
        first.redF() * inverse + second.redF() * weight,
        first.greenF() * inverse + second.greenF() * weight,
        first.blueF() * inverse + second.blueF() * weight,
        first.alphaF() * inverse + second.alphaF() * weight,
    )


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
        self._palette = build_pointer_palette(config.rows, config.columns)
        self._color = QColor(self._palette[0])
        self._cursor_position = QPoint()
        self._pointer_inside = False

        self.setObjectName("pointerLocator")
        self.setProperty("componentType", "pointer-locator")
        self.setProperty("componentId", config.id)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(parent.rect())
        self.hide()
        self._host.installEventFilter(self)

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._poll_cursor)
        self._timer.start()

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
            self.hide()
            return
        self.update_from_global_position(QCursor.pos())

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """Use real window boundary events instead of stale Wayland coordinates."""

        host = getattr(self, "_host", None)
        if watched is host:
            if event.type() == QEvent.Type.Enter:
                self._pointer_inside = True
                self._poll_cursor()
            elif event.type() in {QEvent.Type.Leave, QEvent.Type.Hide}:
                self._pointer_inside = False
                self.hide()
        return super().eventFilter(watched, event)

    def update_from_global_position(self, global_position: QPoint) -> None:
        """Update ring visibility, position, and color from a screen point."""

        if not self._host.isVisible():
            self.hide()
            return

        local_position = self._host.mapFromGlobal(global_position)
        if not self._host.rect().contains(local_position):
            self.hide()
            return

        self._color = interpolate_pointer_color(
            self._palette,
            rows=self._config.rows,
            columns=self._config.columns,
            x=local_position.x(),
            y=local_position.y(),
            width=self._host.width(),
            height=self._host.height(),
        )
        self._cursor_position = local_position
        if self.geometry() != self._host.rect():
            self.setGeometry(self._host.rect())
        self.update()
        self.show()

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
