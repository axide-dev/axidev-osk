"""Reusable overlay chrome widgets (title bar + resize handle).

These widgets are shared by frameless overlay surfaces. They emit
``dragDelta`` / ``resizeDelta`` signals and stay decoupled from any
specific window class so multiple surface implementations can install
the same chrome via ``install_overlay_chrome``. Any mouse button drags, and
each delta names it. The window posts those deltas as ``window.dragged`` and
``window.resize_dragged``, the start and end of each drag as
``window.drag_started``/``window.drag_ended`` and
``window.resize_drag_started``/``window.resize_drag_ended``, and its close
button's press as
``window.close_requested`` with that button too, and moves, resizes, or closes
only when a profile asks.

The engine owns this chrome instead of letting profiles build their own.
On the Linux overlay backends (layer shell, input panel, X11 utility
windows) the window is frameless and the app draws its title bar, so a
standard-library title bar made of nodes could work there. On Windows the
window keeps the operating system's own frame and title bar, which no
profile can replace. The engine promises profiles only what it can keep on
every platform, so a profile can turn this chrome off with
``chrome.enabled`` but not replace it. A profile's stylesheet styles and
sizes each part by its object name (``layerShellTitleBar``,
``layerShellTitleLabel``, ``layerShellCloseButton``,
``layerShellResizeHandle``) and spaces the title bar with its ``padding`` and
``qproperty-spacing``, which both default to none, and the window's
``close_label`` value sets the close button's text.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Property, QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..components.button import Button
from ..components.mouse_buttons import BUTTONS_BY_NAME, mouse_button_name


MoveResizeHandler = Callable[[int, int, str], None]
"""Receives a drag's ``(dx, dy)`` and the name of the mouse button dragging."""


class _ButtonDrag:
    """One drag by whichever mouse button pressed first, reporting deltas from the last position."""

    def __init__(self) -> None:
        self.button: str | None = None
        self._qt_button = Qt.MouseButton.NoButton
        self._last_global: QPoint | None = None

    @property
    def active(self) -> bool:
        return self._last_global is not None

    def press(self, event: QMouseEvent) -> bool:
        """Start a drag unless one is running; return whether this press started it."""

        if self.active:
            return False
        self.button = mouse_button_name(event.button())
        self._qt_button = BUTTONS_BY_NAME.get(self.button, event.button())
        self._last_global = event.globalPosition().toPoint()
        return True

    def holds(self, event: QMouseEvent) -> bool:
        return self.active and bool(event.buttons() & self._qt_button)

    def releases(self, event: QMouseEvent) -> bool:
        return self.active and event.button() == self._qt_button

    def step(self, event: QMouseEvent) -> QPoint:
        current = event.globalPosition().toPoint()
        assert self._last_global is not None
        delta = current - self._last_global
        self._last_global = current
        return delta

    def end(self) -> None:
        self._last_global = None


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

    dragDelta = Signal(int, int, str)
    dragStarted = Signal(str)
    dragEnded = Signal()
    closePressed = Signal(str)
    """The close button was pressed, with the name of the mouse button."""

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        *,
        use_runtime_drag_motion: bool = False,
    ) -> None:
        super().__init__(parent)
        self._drag = _ButtonDrag()
        self._use_runtime_drag_motion = use_runtime_drag_motion

        self.setObjectName("layerShellTitleBar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        layout = QHBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_label = QLabel(title, self)
        self._title_label = title_label
        title_label.setObjectName("layerShellTitleLabel")
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(title_label)
        layout.addStretch(1)

        close_button = Button("x", self)
        self._close_button = close_button
        close_button.setObjectName("layerShellCloseButton")
        close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_button.setFixedSize(28, 24)
        close_button.clicked.connect(lambda: self.closePressed.emit(close_button.pressed_with))
        layout.addWidget(close_button)

    def _spacing(self) -> int:
        return self._layout.spacing()

    def _set_spacing(self, spacing: int) -> None:
        self._layout.setSpacing(spacing)

    spacing = Property(int, _spacing, _set_spacing)
    """The gap between the title, the controls, and the close button; a stylesheet sets it with ``qproperty-spacing``."""

    def add_control(self, widget: QWidget) -> None:
        """Insert a control before the close button."""

        self._layout.insertWidget(self._layout.indexOf(self._close_button), widget)

    def set_title(self, title: str) -> None:
        """Show a new window title."""

        self._title_label.setText(title)

    def set_close_label(self, label: str) -> None:
        """Show ``label`` on the close button."""

        # Qt reads a single "&" as a shortcut marker; doubling it shows the label as written.
        self._close_button.setText(label.replace("&", "&&"))

    def set_close_enabled(self, enabled: bool) -> None:
        """Set whether the title bar exposes its close control."""

        self._close_button.setVisible(enabled)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Begin a title-bar drag with whichever mouse button pressed."""

        if self._drag.press(event):
            self.dragStarted.emit(self._drag.button)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Emit movement deltas while the dragging button is held."""

        if not self._drag.holds(event):
            if self._drag.active:
                self.cancel_drag()
            super().mouseMoveEvent(event)
            return

        if self._use_runtime_drag_motion:
            event.accept()
            return

        delta = self._drag.step(event)
        assert self._drag.button is not None
        self.dragDelta.emit(delta.x(), delta.y(), self._drag.button)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """End the drag when its own button is released."""

        if self._drag.releases(event):
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

        if not self._drag.active:
            return
        self._drag.end()
        self.dragEnded.emit()


class OverlayResizeHandle(QFrame):
    """Frameless resize grip that emits resize deltas."""

    resizeDelta = Signal(int, int, str)
    resizeStarted = Signal(str)
    resizeEnded = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag = _ButtonDrag()

        self.setObjectName("layerShellResizeHandle")
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setFixedSize(18, 18)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Begin a resize drag with whichever mouse button pressed."""

        if self._drag.press(event):
            self.resizeStarted.emit(self._drag.button)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Emit resize deltas while the dragging button is held."""

        if not self._drag.holds(event):
            if self._drag.active:
                self.cancel_drag()
            super().mouseMoveEvent(event)
            return

        delta = self._drag.step(event)
        assert self._drag.button is not None
        self.resizeDelta.emit(delta.x(), delta.y(), self._drag.button)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """End the drag when its own button is released."""

        if self._drag.releases(event):
            self.cancel_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def event(self, event: QEvent) -> bool:
        """Cancel an active resize when Qt withdraws the mouse grab or hides the grip."""

        if event.type() in {QEvent.Type.UngrabMouse, QEvent.Type.Hide}:
            self.cancel_drag()
        return super().event(event)

    def cancel_drag(self) -> None:
        """End the resize once if its normal release event was interrupted."""

        if not self._drag.active:
            return
        self._drag.end()
        self.resizeEnded.emit()


def install_overlay_chrome(
    layout: QVBoxLayout,
    *,
    title: str,
    parent: QWidget,
    on_move: MoveResizeHandler,
    on_resize: MoveResizeHandler,
    on_close: Callable[[str], None],
    on_drag_started: Callable[[str], None],
    on_drag_ended: Callable[[], None],
    on_resize_started: Callable[[str], None],
    on_resize_ended: Callable[[], None],
    use_runtime_drag_motion: bool = False,
) -> OverlayChromeWidgets:
    """Install title bar + resize handle into a vertical layout.

    Args:
        layout: Top-level vertical layout of the overlay surface. The
            title bar is inserted at index 0; the resize handle is
            attached to the title bar as a trailing control.
        title: Initial title bar text.
        parent: Parent widget that hosts the chrome and receives focus
            ownership. Typically the surface widget itself.
        on_move: Receives each ``(dx, dy, button)`` of a title-bar drag.
        on_resize: Receives each ``(dx, dy, button)`` of a resize-grip drag.
        on_close: Receives the mouse button that pressed the close button.
        on_drag_started: Receives the mouse button that starts a title-bar drag.
        on_drag_ended: Called once when a title-bar drag ends.
        on_resize_started: Receives the mouse button that starts a grip drag.
        on_resize_ended: Called once when a grip drag ends.
        use_runtime_drag_motion: The title bar leaves movement to raw pointer
            motion the runtime collects, and emits no ``dragDelta``.

    Returns:
        ``OverlayChromeWidgets`` bundle exposing the constructed
        widgets so callers can theme or further configure them.

    Side effects:
        Mutates ``layout``; connects ``dragDelta`` / ``resizeDelta``
        signals to the supplied handlers.
    """

    title_bar = OverlayTitleBar(title, parent, use_runtime_drag_motion=use_runtime_drag_motion)
    title_bar.dragDelta.connect(on_move)
    title_bar.closePressed.connect(on_close)
    title_bar.dragStarted.connect(on_drag_started)
    title_bar.dragEnded.connect(on_drag_ended)
    layout.insertWidget(0, title_bar)

    resize_handle = OverlayResizeHandle(title_bar)
    resize_handle.resizeDelta.connect(on_resize)
    resize_handle.resizeStarted.connect(on_resize_started)
    resize_handle.resizeEnded.connect(on_resize_ended)
    title_bar.add_control(resize_handle)

    return OverlayChromeWidgets(
        title_bar=title_bar,
        resize_handle=resize_handle,
    )
