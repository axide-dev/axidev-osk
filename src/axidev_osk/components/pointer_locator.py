"""Non-interactive color feedback around a pointer inside a window."""

from __future__ import annotations

import math
import statistics

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QPaintEvent, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from ..config.models import ComponentConfig, PointerLocatorConfig
from ..runtime.context import Context
from ..runtime.registries import ComponentRegistry

_GRADIENT_SEGMENTS = 32
_GAP_COLOR = QColor("#242424")


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


def _rectangle_distance_squared(first: QRect, second: QRect) -> int:
    horizontal = max(first.left() - second.right(), second.left() - first.right(), 0)
    vertical = max(first.top() - second.bottom(), second.top() - first.bottom(), 0)
    return horizontal**2 + vertical**2


def _build_proximity_graph(rectangles: tuple[QRect, ...]) -> tuple[frozenset[int], ...]:
    if not rectangles:
        return ()

    typical_size = statistics.median(min(rect.width(), rect.height()) for rect in rectangles)
    nearby_distance_squared = (typical_size * 2.25) ** 2
    neighbors = [set() for _ in rectangles]
    for index, rectangle in enumerate(rectangles):
        for other_index, other in enumerate(rectangles[:index]):
            if _rectangle_distance_squared(rectangle, other) <= nearby_distance_squared:
                neighbors[index].add(other_index)
                neighbors[other_index].add(index)
    return tuple(frozenset(items) for items in neighbors)


def _greedy_dsatur_coloring(graph: tuple[frozenset[int], ...]) -> tuple[int, ...]:
    colors = [-1] * len(graph)
    while -1 in colors:
        vertex = max(
            (index for index, color in enumerate(colors) if color < 0),
            key=lambda index: (
                len({colors[neighbor] for neighbor in graph[index] if colors[neighbor] >= 0}),
                len(graph[index]),
                -index,
            ),
        )
        forbidden = {colors[neighbor] for neighbor in graph[vertex] if colors[neighbor] >= 0}
        colors[vertex] = next(color for color in range(len(graph)) if color not in forbidden)
    return tuple(colors)


def _temperature_palette(*, warm: bool, color_count: int) -> tuple[QColor, ...]:
    """Build deterministic vivid colors from one side of the hue wheel."""

    if color_count <= 0:
        return ()
    start = 330.0 if warm else 150.0
    span = 90.0 if warm else 120.0
    return tuple(
        QColor.fromHsvF(
            ((start + span * index / color_count) % 360.0) / 360.0,
            1.0,
            1.0 if index % 2 == 0 else 0.7,
        )
        for index in range(color_count)
    )


def _checkerboard_parities(rectangles: tuple[QRect, ...]) -> tuple[int, ...]:
    typical_size = statistics.median(min(rect.width(), rect.height()) for rect in rectangles)
    rows: list[list[int]] = []
    for index in sorted(
        range(len(rectangles)),
        key=lambda item: (rectangles[item].center().y(), rectangles[item].center().x()),
    ):
        if not rows or abs(rectangles[index].center().y() - rectangles[rows[-1][0]].center().y()) > typical_size / 2:
            rows.append([index])
        else:
            rows[-1].append(index)

    parities = [0] * len(rectangles)
    for row_index, row in enumerate(rows):
        row.sort(key=lambda index: rectangles[index].center().x())
        for column_index, index in enumerate(row):
            parities[index] = (row_index + column_index) % 2
    return tuple(parities)


def build_component_palette(rectangles: tuple[QRect, ...]) -> tuple[QColor, ...]:
    """Assign deterministic warm/cold checkerboard colors to components."""

    if not rectangles:
        return ()

    graph = _build_proximity_graph(rectangles)
    parities = _checkerboard_parities(rectangles)
    colors = [QColor() for _ in rectangles]
    partition_colorings: list[tuple[list[int], tuple[int, ...]]] = []
    for parity in (0, 1):
        vertices = [index for index, value in enumerate(parities) if value == parity]
        if not vertices:
            partition_colorings.append((vertices, ()))
            continue
        lookup = {vertex: index for index, vertex in enumerate(vertices)}
        subgraph = tuple(
            frozenset(lookup[neighbor] for neighbor in graph[vertex] if neighbor in lookup)
            for vertex in vertices
        )
        coloring = _greedy_dsatur_coloring(subgraph)
        partition_colorings.append((vertices, coloring))

    warm_count = max(partition_colorings[0][1], default=-1) + 1
    cold_count = max(partition_colorings[1][1], default=-1) + 1
    warm_palette = _temperature_palette(warm=True, color_count=warm_count)
    cold_palette = _temperature_palette(warm=False, color_count=cold_count)
    for parity, (vertices, coloring) in enumerate(partition_colorings):
        palette = warm_palette if parity == 0 else cold_palette
        for vertex, color in zip(vertices, coloring, strict=True):
            colors[vertex] = QColor(palette[color])
    return tuple(colors)


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
        self._color_targets: tuple[tuple[QWidget, QRect, QColor], ...] = ()
        self._color_target_signature: tuple[tuple[int, int, int, int, int], ...] = ()

        self.setObjectName("pointerLocator")
        self.setProperty("componentType", "pointer-locator")
        self.setProperty("componentId", config.id)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(parent.rect())
        self.hide()

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._poll_cursor)
        self._host.installEventFilter(self)

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

        self._refresh_color_targets()
        target = next(
            (target for target in self._color_targets if target[1].contains(local_position)),
            None,
        )
        self._color = QColor(target[2] if target is not None else _GAP_COLOR)
        self._cursor_position = local_position
        if self.geometry() != self._host.rect():
            self.setGeometry(self._host.rect())
        self.update()
        self.show()

    def _refresh_color_targets(self) -> None:
        widgets = [
            widget
            for widget in self._host.findChildren(QWidget)
            if widget.property("componentType") in {"button", "key"} and widget.isVisibleTo(self._host)
        ]
        positioned = [
            (
                widget,
                QRect(widget.mapTo(self._host, QPoint()), widget.size()),
            )
            for widget in widgets
            if widget.width() > 0 and widget.height() > 0
        ]
        positioned.sort(key=lambda item: (item[1].center().y(), item[1].center().x()))
        signature = tuple((id(widget), *rect.getRect()) for widget, rect in positioned)
        if signature == self._color_target_signature:
            return
        colors = build_component_palette(tuple(rect for _, rect in positioned))
        self._color_targets = tuple(
            (widget, rect, color) for (widget, rect), color in zip(positioned, colors, strict=True)
        )
        self._color_target_signature = signature

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
