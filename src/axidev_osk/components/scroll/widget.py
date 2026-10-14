"""A scroll area that grows with its content up to its maximum size, then scrolls.

Scrolling is an engine built-in rather than something a profile builds from
``node.wheel`` because Qt moves the content in pixels as the wheel or a touch
gesture turns, which a round trip through the queue for every step cannot
match. A profile turns wheel scrolling off with ``wheel_scrolls``, and a node
with ``reports_wheel`` still reports every turn.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QAbstractScrollArea, QFrame, QScrollArea, QWidget

_SCROLLBAR_POLICIES = {
    "as_needed": Qt.ScrollBarPolicy.ScrollBarAsNeeded,
    "always": Qt.ScrollBarPolicy.ScrollBarAlwaysOn,
    "never": Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
}
SCROLLBAR_CHOICES = frozenset(_SCROLLBAR_POLICIES)


class ScrollArea(QScrollArea):
    """Scroll ``content`` along ``direction`` (``vertical`` or ``horizontal``) and never across it.

    Along its direction, the area asks for its content's full length, capped
    by its maximum size, so a window that fits its content shows every child
    until that cap and scrolls past it. Across, it asks for what the content
    needs plus the scrollbar. The area, its viewport, and its scrollbars never
    take keyboard focus.
    """

    def __init__(self, content: QWidget, direction: str) -> None:
        super().__init__()
        self._vertical = direction == "vertical"
        self._wheel_scrolls = True
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        for bar in (self.horizontalScrollBar(), self.verticalScrollBar()):
            bar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # The content draws on whatever is behind the area, like a box's children.
        self.viewport().setAutoFillBackground(False)
        content.setAutoFillBackground(False)
        self.setWidget(content)
        content.installEventFilter(self)
        self.set_scrollbar("as_needed")

    def set_wheel_scrolls(self, scrolls: bool) -> None:
        self._wheel_scrolls = scrolls

    def set_scrollbar(self, scrollbar: str) -> None:
        """Show the scrollbar along the direction ``as_needed``, ``always``, or ``never``."""

        along, across = _SCROLLBAR_POLICIES[scrollbar], Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        self.setVerticalScrollBarPolicy(along if self._vertical else across)
        self.setHorizontalScrollBarPolicy(across if self._vertical else along)
        self.updateGeometry()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt override
        if self._wheel_scrolls:
            super().wheelEvent(event)
        else:
            # Ignored, the turn goes on to the widgets around the area.
            event.ignore()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if watched is self.widget() and event.type() == QEvent.Type.LayoutRequest:
            # The content's length changed, such as a child that shows or hides.
            self.updateGeometry()
        return super().eventFilter(watched, event)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self._fitted()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self._fitted()

    def _fitted(self) -> QSize:
        content = self.widget()
        if content is None:
            return QSize(0, 0)
        wanted, needed = content.sizeHint(), content.minimumSizeHint()
        frame = 2 * self.frameWidth()
        if self._vertical:
            bar = self.verticalScrollBar().sizeHint().width() if self._bar_shown() else 0
            return QSize(needed.width() + bar + frame, min(wanted.height() + frame, self.maximumHeight()))
        bar = self.horizontalScrollBar().sizeHint().height() if self._bar_shown() else 0
        return QSize(min(wanted.width() + frame, self.maximumWidth()), needed.height() + bar + frame)

    def _bar_shown(self) -> bool:
        """Whether the scrollbar may show, so the area keeps room for it across its direction."""

        policy = self.verticalScrollBarPolicy() if self._vertical else self.horizontalScrollBarPolicy()
        return policy != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
