"""Shared render-only button widget with uniform pointer activation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import cast

from PySide6.QtCore import QEvent, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QFontInfo,
    QFontMetrics,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QRegion,
)
from PySide6.QtWidgets import QPushButton, QStyle, QStyleOptionButton, QWidget

_TEXT_FLAGS = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextShowMnemonic
_SAMPLE_SIZE = 32


class Button(QPushButton):
    """Application button that treats right clicks like left clicks.

    The widget keeps no interaction state of its own. Callers render
    pressed and latched state from runtime snapshots.

    Its label is never cut: the font its style gives it is the largest size
    used, and a label that does not fit its content area, or its shape, is
    drawn smaller, at the largest size that fits. A single label is drawn by
    the style itself, scaled down when it must shrink, so every stylesheet
    text rule still applies to it. A label given as several parts is spread
    over the shape in rows, each row holding as many parts as the widest
    stretch the shape covers there, and each part is drawn by the style the
    same way, so state rules such as a pressed text color apply to it too.
    When no row layout fits even at the smallest size, the parts are drawn
    as one label.

    A parent may give the button a shape (``set_shape``): the button is then
    clipped to it and draws its border along it, in the color its style
    gives a rectangular button's border in the same state. That color is
    read from the left edge of a small rectangular sample, so it assumes a
    solid left border, no margin, and a corner radius under half the sample.
    """

    def __init__(self, label: str = "", parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self._parts: tuple[str, ...] | None = None
        self._outline: QPainterPath | None = None
        self._border_colors: dict[int, QColor] = {}

    def set_parts(self, parts: tuple[str, ...] | None) -> None:
        """Show ``parts`` spread over the button, or, given ``None``, the one label set with ``setText``."""

        self._parts = parts
        if parts is not None:
            self.setText(" ".join(parts).replace("&", "&&"))
        self.update()

    def set_shape(self, outline: QPainterPath) -> None:
        """Clip the button to ``outline``, in its own coordinates, and draw its border along it."""

        self._outline = outline
        self.setMask(QRegion(outline.toFillPolygon().toPolygon()))
        self.update()

    def event(self, event: QEvent) -> bool:
        # A new stylesheet or state property can change every border color.
        if event.type() in (QEvent.Type.Polish, QEvent.Type.StyleChange, QEvent.Type.PaletteChange):
            self._border_colors.clear()
        return super().event(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        option = QStyleOptionButton()
        self.initStyleOption(option)
        text = option.text
        option.text = ""
        painter = QPainter(self)
        style = self.style()
        style.drawControl(QStyle.ControlElement.CE_PushButtonBevel, option, painter, self)
        if self._outline is not None:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            # The mask cuts the outer half of the pen, leaving a one pixel border.
            painter.setPen(QPen(self._border_color(option), 2))
            painter.drawPath(self._outline)
            painter.restore()
        area = style.subElementRect(QStyle.SubElement.SE_PushButtonContents, option, self)
        placed: list[tuple[QRect, str]] = []
        if self._parts is not None:
            font, placed = self.spread(self._parts, area)
            for box, part in placed:
                self._draw_label(painter, option, part.replace("&", "&&"), box, self._scale(font.pixelSize()))
        if not placed and text:
            self._draw_label(painter, option, text, area, self._scale(self.fitted_font(text, area).pixelSize()))

    def _scale(self, pixel_size: int) -> float:
        return pixel_size / max(1, QFontInfo(self.font()).pixelSize())

    def _draw_label(self, painter: QPainter, option: QStyleOptionButton, text: str, box: QRect, scale: float) -> None:
        """Draw ``text`` centered in ``box`` through the style, scaled down by ``scale``.

        The style ignores any font but its own, so a label that must shrink
        is drawn scaled down instead.
        """

        painter.save()
        center = QRectF(box).center()
        painter.translate(center)
        painter.scale(scale, scale)
        painter.translate(-center)
        option.rect = QRectF(
            center.x() - box.width() / (2 * scale),
            center.y() - box.height() / (2 * scale),
            box.width() / scale,
            box.height() / scale,
        ).toAlignedRect()
        option.text = text
        self.style().drawControl(QStyle.ControlElement.CE_PushButtonLabel, option, painter, self)
        painter.restore()

    def fitted_font(self, text: str, area: QRect) -> QFont:
        """The style's font, made smaller until ``text`` fits ``area`` and the button's mask."""

        font = QFont(self.font())
        mask = self.mask()

        def fits(size: int) -> bool:
            font.setPixelSize(size)
            needed = QFontMetrics(font).boundingRect(QRect(), _TEXT_FLAGS, text)
            box = QRect(0, 0, needed.width(), needed.height())
            box.moveCenter(area.center())
            if not area.contains(box):
                return False
            return mask.isEmpty() or mask.intersected(box) == QRegion(box)

        font.setPixelSize(self._largest_fitting(fits))
        return font

    def spread(self, parts: tuple[str, ...], area: QRect) -> tuple[QFont, list[tuple[QRect, str]]]:
        """Place ``parts`` in rows over ``area`` and the button's mask, at the largest size that fits them all."""

        font = QFont(self.font())
        mask = self.mask()

        def span(top: int, bottom: int) -> tuple[int, int] | None:
            # The widest stretch the shape covers on every line of the row, so a part never lands in a gap.
            runs = [(area.left(), area.right())]
            if not mask.isEmpty():
                for y in range(top, bottom + 1):
                    # PySide6 iterates a region's rectangles, which its type stubs do not declare.
                    pieces = cast(Iterable[QRect], mask.intersected(QRect(area.left(), y, area.width(), 1)))
                    line = [(rect.left(), rect.right()) for rect in pieces]
                    runs = [
                        (max(left, line_left), min(right, line_right))
                        for left, right in runs
                        for line_left, line_right in line
                        if max(left, line_left) < min(right, line_right)
                    ]
                    if not runs:
                        return None
            return max(runs, key=lambda run: run[1] - run[0])

        def place(size: int, top: int) -> list[tuple[QRect, str]] | None:
            font.setPixelSize(size)
            metrics = QFontMetrics(font)
            height, gap = metrics.height(), metrics.horizontalAdvance(" ")
            placed: list[tuple[QRect, str]] = []
            index, y = 0, top
            while index < len(parts):
                if y + height - 1 > area.bottom():
                    return None
                free = span(y, y + height - 1)
                row: list[tuple[str, int]] = []
                used = 0
                while free is not None and index < len(parts):
                    width = metrics.horizontalAdvance(parts[index])
                    needed = width if not row else used + gap + width
                    if needed > free[1] - free[0] + 1:
                        break
                    row.append((parts[index], width))
                    used, index = needed, index + 1
                if free is not None and row:
                    x = free[0] + (free[1] - free[0] + 1 - used) // 2
                    for part, width in row:
                        placed.append((QRect(x, y, width, height), part))
                        x += width + gap
                y += height
            return placed

        size = self._largest_fitting(lambda candidate: place(candidate, area.top()) is not None)
        placed = place(size, area.top()) or []
        if placed:
            # Center the rows vertically when they still fit there.
            slack = area.bottom() - max(box.bottom() for box, _ in placed)
            placed = place(size, area.top() + slack // 2) or place(size, area.top()) or []
        font.setPixelSize(size)
        return font, placed

    def _largest_fitting(self, fits: Callable[[int], bool]) -> int:
        """The largest pixel size up to the style's that ``fits``, by bisection; 1 when none does."""

        low, high = 1, max(1, QFontInfo(self.font()).pixelSize())
        while low < high:
            middle = (low + high + 1) // 2
            if fits(middle):
                low = middle
            else:
                high = middle - 1
        return low

    def _border_color(self, option: QStyleOptionButton) -> QColor:
        """The border color the style draws for this button's state, read off a small rectangular sample once per state."""

        key = option.state.value
        if key not in self._border_colors:
            self._border_colors[key] = self._sample_border(option)
        return self._border_colors[key]

    def _sample_border(self, option: QStyleOptionButton) -> QColor:
        sample = QImage(_SAMPLE_SIZE, _SAMPLE_SIZE, QImage.Format.Format_ARGB32_Premultiplied)
        sample.fill(Qt.GlobalColor.transparent)
        painter = QPainter(sample)
        rectangle = QStyleOptionButton(option)
        rectangle.rect = QRect(0, 0, _SAMPLE_SIZE, _SAMPLE_SIZE)
        self.style().drawControl(QStyle.ControlElement.CE_PushButtonBevel, rectangle, painter, self)
        painter.end()
        return sample.pixelColor(0, _SAMPLE_SIZE // 2)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Treat a right-button press as a left-button press."""

        self._forward_mouse_event(event, super().mousePressEvent)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Preserve left-button drag semantics while the right button is held."""

        self._forward_mouse_event(event, super().mouseMoveEvent)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Treat a right-button release as a left-button release."""

        self._forward_mouse_event(event, super().mouseReleaseEvent)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Treat a right-button double click as a left-button double click."""

        self._forward_mouse_event(event, super().mouseDoubleClickEvent)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Suppress the context-menu event produced by an activating right click."""

        event.accept()

    @staticmethod
    def _left_mouse_event(event: QMouseEvent) -> QMouseEvent:
        button = event.button()
        buttons = event.buttons()
        if button == Qt.MouseButton.RightButton:
            button = Qt.MouseButton.LeftButton
        if buttons & Qt.MouseButton.RightButton:
            buttons = (buttons & ~Qt.MouseButton.RightButton) | Qt.MouseButton.LeftButton
        return QMouseEvent(
            event.type(),
            event.position(),
            event.globalPosition(),
            button,
            buttons,
            event.modifiers(),
        )

    def _forward_mouse_event(
        self,
        event: QMouseEvent,
        handler: Callable[[QMouseEvent], None],
    ) -> None:
        if event.button() != Qt.MouseButton.RightButton and not (
            event.buttons() & Qt.MouseButton.RightButton
        ):
            handler(event)
            return
        left_event = self._left_mouse_event(event)
        handler(left_event)
        event.setAccepted(left_event.isAccepted())
