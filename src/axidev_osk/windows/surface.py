"""Root surface hosting a window's content and background attachments."""

from __future__ import annotations

from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QWidget


class RootSurface(QWidget):
    """Generic root surface with a background-component layer."""

    def __init__(self) -> None:
        super().__init__()
        self._background_components: list[QWidget] = []

    def install_background_component(self, widget: QWidget) -> None:
        """Parent and stack one component immediately above the styled background."""

        widget.setParent(self)
        widget.setGeometry(self.rect())
        self._background_components.append(widget)
        for component in reversed(self._background_components):
            component.lower()

    def resizeEvent(self, event: QResizeEvent) -> None:  # type: ignore[override]
        """Keep all background components fitted to the surface."""

        super().resizeEvent(event)
        for component in self._background_components:
            component.setGeometry(self.rect())
