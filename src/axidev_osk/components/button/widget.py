"""Shared render-only button widget with uniform pointer activation."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QPushButton, QWidget

from ..mouse_buttons import MOUSE_BUTTONS, mouse_button_name

_LEFT = Qt.MouseButton.LeftButton
_NOT_LEFT = ~Qt.MouseButton.LeftButton
"""Every mouse button but the left one; each presses the widget as the left one does, and ``pressed_with`` still names it."""


class Button(QPushButton):
    """Application button that every mouse button presses.

    It decides nothing about what each mouse button means: ``pressed_with``
    names the one behind the current press, or ``other`` for a mouse button
    with no name, the node reports it with
    ``button.pressed`` and ``button.released``, and the profile decides. The
    widget keeps no other interaction state than that and whether the pointer
    is over it, so ``entered`` and ``left`` always alternate. Profiles render
    any lasting look, such as a latched key, through style properties.
    """

    entered = Signal()
    """The pointer moved onto the button."""
    left = Signal()
    """The pointer moved off the button."""

    def __init__(self, label: str = "", parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self._hovered = False
        self._pressed_with = "left"

    @property
    def pressed_with(self) -> str:
        """The mouse button, such as ``left`` or ``right``, behind the current or last press."""

        return self._pressed_with

    def press_with(self, button: str) -> None:
        """Click the button as ``button`` would, with Qt's short visible press."""

        self._pressed_with = button if button in MOUSE_BUTTONS.values() else "left"
        self.animateClick()

    def enterEvent(self, event: QEnterEvent) -> None:
        super().enterEvent(event)
        # Qt can repeat an enter, for example when another window closes under the pointer.
        if not self._hovered:
            self._hovered = True
            self.entered.emit()

    def leaveEvent(self, event: QEvent) -> None:
        super().leaveEvent(event)
        if self._hovered:
            self._hovered = False
            self.left.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Press with any mouse button, remembering which one."""

        if not self.isDown():
            self._pressed_with = mouse_button_name(event.button())
        self._forward_mouse_event(event, super().mousePressEvent)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Preserve left-button drag semantics while another mouse button is held."""

        self._forward_mouse_event(event, super().mouseMoveEvent)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Release with the button that pressed."""

        self._forward_mouse_event(event, super().mouseReleaseEvent)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Treat a double click as a second press with the same button."""

        if not self.isDown():
            self._pressed_with = mouse_button_name(event.button())
        self._forward_mouse_event(event, super().mouseDoubleClickEvent)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Suppress the context menu a right click would open; the click is reported instead."""

        event.accept()

    @staticmethod
    def _left_mouse_event(event: QMouseEvent) -> QMouseEvent:
        button = _LEFT if event.button() & _NOT_LEFT else event.button()
        buttons = event.buttons()
        if buttons & _NOT_LEFT:
            buttons = (buttons & _LEFT) | _LEFT
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
        if not event.button() & _NOT_LEFT and not event.buttons() & _NOT_LEFT:
            handler(event)
            return
        left_event = self._left_mouse_event(event)
        handler(left_event)
        event.setAccepted(left_event.isAccepted())
