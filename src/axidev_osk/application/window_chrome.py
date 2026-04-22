from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget


MoveResizeHandler = Callable[[int, int], None]


@dataclass(slots=True)
class OverlayChromeWidgets:
    title_bar: "OverlayTitleBar"
    resize_handle: "OverlayResizeHandle"


class OverlayTitleBar(QFrame):
    dragDelta = Signal(int, int)

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_last_global: QPoint | None = None

        self.setObjectName("layerShellTitleBar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(8)

        title_label = QLabel(title, self)
        title_label.setObjectName("layerShellTitleLabel")
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(title_label)
        layout.addStretch(1)

        close_button = QPushButton("x", self)
        close_button.setObjectName("layerShellCloseButton")
        close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_button.setFixedSize(28, 24)
        close_button.clicked.connect(self._close_window)
        layout.addWidget(close_button)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last_global = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_last_global is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return

        current = event.globalPosition().toPoint()
        delta = current - self._drag_last_global
        self._drag_last_global = current
        self.dragDelta.emit(delta.x(), delta.y())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last_global = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _close_window(self) -> None:
        window = self.window()
        if window is not None:
            window.close()


class OverlayResizeHandle(QFrame):
    resizeDelta = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_last_global: QPoint | None = None

        self.setObjectName("layerShellResizeHandle")
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setFixedSize(18, 18)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last_global = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_last_global is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return

        current = event.globalPosition().toPoint()
        delta = current - self._drag_last_global
        self._drag_last_global = current
        self.resizeDelta.emit(delta.x(), delta.y())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last_global = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


def install_overlay_chrome(
    layout: QVBoxLayout,
    footer: QHBoxLayout,
    *,
    title: str,
    parent: QWidget,
    on_move: MoveResizeHandler,
    on_resize: MoveResizeHandler,
) -> OverlayChromeWidgets:
    title_bar = OverlayTitleBar(title, parent)
    title_bar.dragDelta.connect(on_move)
    layout.addWidget(title_bar)

    resize_handle = OverlayResizeHandle(parent)
    resize_handle.resizeDelta.connect(on_resize)
    footer.addWidget(resize_handle, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

    return OverlayChromeWidgets(
        title_bar=title_bar,
        resize_handle=resize_handle,
    )


LayerShellTitleBar = OverlayTitleBar
LayerShellResizeHandle = OverlayResizeHandle
