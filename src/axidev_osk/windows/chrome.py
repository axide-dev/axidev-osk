"""Reusable overlay chrome widgets (title bar + resize handle).

These widgets are shared by frameless overlay surfaces. They emit
``dragDelta`` / ``resizeDelta`` signals and stay decoupled from any
specific window class so multiple surface implementations can install
the same chrome via ``install_overlay_chrome``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget


MoveResizeHandler = Callable[[int, int], None]


@dataclass(slots=True)
class OverlayChromeWidgets:
    """Bundle of chrome widgets returned by ``install_overlay_chrome``.

    Attributes:
        title_bar: Frameless drag-to-move title bar.
        resize_handle: Bottom-right diagonal resize handle.
    """

    title_bar: "OverlayTitleBar"
    resize_handle: "OverlayResizeHandle"


class OverlayTitleBar(QFrame):
    """Frameless title bar supporting Qt and raw-pointer drag sources."""

    dragDelta = Signal(int, int)
    dragStarted = Signal()
    dragEnded = Signal()

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        *,
        use_runtime_drag_motion: bool = False,
    ) -> None:
        super().__init__(parent)
        self._drag_last_global: QPoint | None = None
        self._use_runtime_drag_motion = use_runtime_drag_motion

        self.setObjectName("layerShellTitleBar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        layout = QHBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(8)

        title_label = QLabel(title, self)
        title_label.setObjectName("layerShellTitleLabel")
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(title_label)
        layout.addStretch(1)

        close_button = QPushButton("x", self)
        self._close_button = close_button
        close_button.setObjectName("layerShellCloseButton")
        close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_button.setFixedSize(28, 24)
        close_button.clicked.connect(self._close_window)
        layout.addWidget(close_button)

    def add_control(self, widget: QWidget) -> None:
        """Insert a control before the close button."""

        self._layout.insertWidget(self._layout.indexOf(self._close_button), widget)

    def set_close_enabled(self, enabled: bool) -> None:
        """Set whether the title bar exposes its close control."""

        self._close_button.setVisible(enabled)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Begin a title-bar drag on left mouse press."""

        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last_global = event.globalPosition().toPoint()
            self.dragStarted.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Emit movement deltas while dragging the title bar."""

        if self._drag_last_global is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            if self._drag_last_global is not None:
                self.cancel_drag()
            super().mouseMoveEvent(event)
            return

        if self._use_runtime_drag_motion:
            event.accept()
            return

        current = event.globalPosition().toPoint()
        delta = current - self._drag_last_global
        self._drag_last_global = current
        self.dragDelta.emit(delta.x(), delta.y())
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """End an active title-bar drag."""

        if event.button() == Qt.MouseButton.LeftButton:
            self.cancel_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def event(self, event: QEvent) -> bool:
        """Cancel an active drag when Qt withdraws the mouse grab or hides the title bar."""

        if event.type() in {QEvent.Type.UngrabMouse, QEvent.Type.Hide}:
            self.cancel_drag()
        return super().event(event)

    def cancel_drag(self) -> None:
        """End the drag once if its normal release event was interrupted."""

        if self._drag_last_global is None:
            return
        self._drag_last_global = None
        self.dragEnded.emit()

    def _close_window(self) -> None:
        window = self.window()
        if window is not None:
            window.close()


class OverlayResizeHandle(QFrame):
    """Frameless resize grip that emits resize deltas."""

    resizeDelta = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_last_global: QPoint | None = None

        self.setObjectName("layerShellResizeHandle")
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setFixedSize(18, 18)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Begin a resize drag on left mouse press."""

        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last_global = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Emit resize deltas while dragging the handle."""

        if self._drag_last_global is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return

        current = event.globalPosition().toPoint()
        delta = current - self._drag_last_global
        self._drag_last_global = current
        self.resizeDelta.emit(delta.x(), delta.y())
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """End an active resize drag."""

        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last_global = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


def install_overlay_chrome(
    layout: QVBoxLayout,
    *,
    title: str,
    parent: QWidget,
    on_move: MoveResizeHandler,
    on_resize: MoveResizeHandler,
    use_runtime_drag_motion: bool = False,
    on_drag_started: Callable[[], None] | None = None,
    on_drag_ended: Callable[[], None] | None = None,
) -> OverlayChromeWidgets:
    """Install title bar + resize handle into a vertical layout.

    Args:
        layout: Top-level vertical layout of the overlay surface. The
            title bar is inserted at index 0; the resize handle is
            attached to the title bar as a trailing control.
        title: Initial title bar text.
        parent: Parent widget that hosts the chrome and receives focus
            ownership. Typically the surface widget itself.
        on_move: Callback invoked with cumulative ``(dx, dy)`` deltas
            during title-bar drag. Implementations should translate the
            window by the delta.
        on_resize: Callback invoked with cumulative ``(dx, dy)`` deltas
            during resize-handle drag. Implementations should grow or
            shrink the window's geometry.

    Returns:
        ``OverlayChromeWidgets`` bundle exposing the constructed
        widgets so callers can theme or further configure them.

    Side effects:
        Mutates ``layout``; connects ``dragDelta`` / ``resizeDelta``
        signals to the supplied handlers.
    """

    title_bar = OverlayTitleBar(title, parent, use_runtime_drag_motion=use_runtime_drag_motion)
    title_bar.dragDelta.connect(on_move)
    if on_drag_started is not None:
        title_bar.dragStarted.connect(on_drag_started)
    if on_drag_ended is not None:
        title_bar.dragEnded.connect(on_drag_ended)
    layout.insertWidget(0, title_bar)

    resize_handle = OverlayResizeHandle(title_bar)
    resize_handle.resizeDelta.connect(on_resize)
    title_bar.add_control(resize_handle)

    return OverlayChromeWidgets(
        title_bar=title_bar,
        resize_handle=resize_handle,
    )


LayerShellTitleBar = OverlayTitleBar
LayerShellResizeHandle = OverlayResizeHandle
