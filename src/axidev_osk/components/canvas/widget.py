"""A container that places each child by a polygon and clips it to that polygon."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, QSize
from PySide6.QtGui import QPainterPath, QPolygonF, QRegion
from PySide6.QtWidgets import QSizePolicy, QWidget

Point = tuple[float, float]
"""A point in pixels, relative to the canvas's top-left corner."""
Shape = tuple[Point, ...]
"""A polygon's corners."""


class Canvas(QWidget):
    """Place each child over its polygon and clip it to the polygon.

    The child's box is the polygon's bounding box, or, given an anchor, the
    smallest box centered on the anchor that holds the polygon, so a widget
    that centers its content centers it on the anchor. A child with a
    ``set_shape(outline)`` method, such as a button, takes the polygon as its
    shape and draws its border along it; any other widget gets a mask. Clicks, hover, and dwell targeting follow
    the clipped shape. The canvas never sizes itself from its children: its
    size comes from its own limits and its parent's layout, and whoever sets
    the polygons decides how they follow that size.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def place(self, widget: QWidget, shape: Shape, anchor: Point | None = None) -> None:
        """Make ``widget`` a child placed and clipped by ``shape``, centered on ``anchor`` when given."""

        if widget.parentWidget() is not self:
            widget.setParent(self)
        polygon = QPolygonF([QPointF(x, y) for x, y in shape])
        bounds = polygon.boundingRect()
        rect = _box_around(QPointF(*anchor), bounds) if anchor is not None else bounds.toAlignedRect()
        widget.setGeometry(rect)
        outline = QPainterPath()
        outline.addPolygon(polygon.translated(-rect.x(), -rect.y()))
        outline.closeSubpath()
        set_shape = getattr(widget, "set_shape", None)
        if callable(set_shape):
            set_shape(outline)
        else:
            widget.setMask(QRegion(outline.toFillPolygon().toPolygon()))

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self.minimumSize()


def _box_around(anchor: QPointF, bounds: QRectF) -> QRect:
    """The smallest box centered on ``anchor`` that holds ``bounds``."""

    half_width = max(anchor.x() - bounds.left(), bounds.right() - anchor.x())
    half_height = max(anchor.y() - bounds.top(), bounds.bottom() - anchor.y())
    return QRectF(anchor.x() - half_width, anchor.y() - half_height, 2 * half_width, 2 * half_height).toAlignedRect()
