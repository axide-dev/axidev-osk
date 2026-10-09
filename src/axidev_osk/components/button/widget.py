"""Shared render-only button widget with uniform pointer activation."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import QPushButton, QWidget


class Button(QPushButton):
    """Application button that treats right clicks like left clicks.

    The widget keeps no interaction state of its own. Callers render
    pressed and latched state from runtime snapshots.
    """

    def __init__(self, label: str = "", parent: QWidget | None = None) -> None:
        super().__init__(label, parent)

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
