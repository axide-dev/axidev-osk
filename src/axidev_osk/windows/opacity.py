"""Platform-aware visual opacity for runtime windows."""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QGraphicsOpacityEffect, QMainWindow


class WindowOpacityController:
    """Apply one opacity API through the primitive supported by the platform."""

    def __init__(self, window: QMainWindow) -> None:
        self._window = window
        self._content_effect: QGraphicsOpacityEffect | None = None

    def set_opacity(self, opacity: float) -> None:
        """Set visual opacity for the complete runtime-window content."""

        content = self._window.centralWidget()
        if QGuiApplication.platformName().lower() == "wayland" and content is not None:
            if self._content_effect is None:
                self._content_effect = QGraphicsOpacityEffect(content)
                content.setGraphicsEffect(self._content_effect)
            self._content_effect.setOpacity(opacity)
            return
        self._window.setWindowOpacity(opacity)
