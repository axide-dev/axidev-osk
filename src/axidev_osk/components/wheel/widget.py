"""A round container that shapes its children into wedges around a center disc."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRect, QRectF, QSize
from PySide6.QtGui import QPolygon, QPolygonF, QRegion, QResizeEvent
from PySide6.QtWidgets import QWidget

_ARC_POINTS = 32


class Wheel(QWidget):
    """Lay children out as the slices of a disc, slice 0 on top, numbered clockwise.

    Each child gets the rectangle centered on its slice's middle, so a widget
    that centers its content, such as a button label, centers it inside the
    wedge, and a mask clipped to the wedge. Clicks, hover, and dwell targeting
    follow the mask, so the child behaves as if it had the wedge's shape.
    """

    def __init__(self, slices: int) -> None:
        super().__init__()
        self._slices = slices
        self._children: list[tuple[QWidget, int | None]] = []
        self._inner_fraction = 0.25
        self._spacing = 0

    def add_slice(self, widget: QWidget, slice_index: int) -> None:
        self._add(widget, slice_index)

    def add_center(self, widget: QWidget) -> None:
        self._add(widget, None)

    def set_shape(self, inner_fraction: float, spacing: int) -> None:
        """Set the center disc's radius as a fraction of the wheel's, and the gap between parts."""

        if (inner_fraction, spacing) == (self._inner_fraction, self._spacing):
            return
        self._inner_fraction = inner_fraction
        self._spacing = spacing
        self._arrange()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        side = max(self.minimumWidth(), self.minimumHeight())
        return QSize(side, side)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._arrange()

    def _add(self, widget: QWidget, slice_index: int | None) -> None:
        widget.setParent(self)
        self._children.append((widget, slice_index))
        self._arrange()

    def _arrange(self) -> None:
        outer = min(self.width(), self.height()) / 2
        if outer <= 0:
            return
        center = QPointF(self.width() / 2, self.height() / 2)
        gap = self._spacing / 2
        inner = outer * self._inner_fraction
        for widget, slice_index in self._children:
            if slice_index is None:
                outline = _disc(center, max(1.0, inner - gap))
                anchor = center
            else:
                outline = _wedge(center, slice_index, self._slices, inner + gap, outer, gap)
                anchor = _polar(center, (inner + outer) / 2, _slice_angle(slice_index, self._slices))
            rect = _rect_around(anchor, outline.boundingRect())
            widget.setGeometry(rect)
            widget.setMask(QRegion(QPolygon(outline.translated(-QPointF(rect.topLeft())).toPolygon())))


def _slice_angle(slice_index: int, slices: int) -> float:
    return slice_index * 2 * math.pi / slices


def _polar(center: QPointF, radius: float, angle: float) -> QPointF:
    """The point at ``radius`` from ``center``, ``angle`` radians clockwise from straight up."""

    return QPointF(center.x() + radius * math.sin(angle), center.y() - radius * math.cos(angle))


def _arc(center: QPointF, radius: float, start: float, end: float) -> list[QPointF]:
    return [_polar(center, radius, start + (end - start) * step / _ARC_POINTS) for step in range(_ARC_POINTS + 1)]


def _disc(center: QPointF, radius: float) -> QPolygonF:
    return QPolygonF(_arc(center, radius, 0, 2 * math.pi))


def _wedge(center: QPointF, slice_index: int, slices: int, inner: float, outer: float, gap: float) -> QPolygonF:
    """The ring sector of one slice, with its straight edges moved ``gap`` pixels inward."""

    middle = _slice_angle(slice_index, slices)
    half = math.pi / slices

    def edge(radius: float) -> float:
        # The angle that keeps a ``gap``-wide margin at this radius, never past the slice's middle.
        return half - math.asin(min(1.0, gap / radius)) if radius > 0 else 0.0

    outer_half, inner_half = edge(outer), edge(inner)
    points = _arc(center, outer, middle - outer_half, middle + outer_half)
    points += _arc(center, inner, middle + inner_half, middle - inner_half)
    return QPolygonF(points)


def _rect_around(anchor: QPointF, bounds: QRectF) -> QRect:
    """The smallest rectangle centered on ``anchor`` that contains ``bounds``."""

    half_width = max(anchor.x() - bounds.left(), bounds.right() - anchor.x())
    half_height = max(anchor.y() - bounds.top(), bounds.bottom() - anchor.y())
    return QRectF(anchor.x() - half_width, anchor.y() - half_height, 2 * half_width, 2 * half_height).toAlignedRect()
