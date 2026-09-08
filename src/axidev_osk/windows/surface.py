"""Generic window surface builder."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..config.models import SurfaceConfig
from ..runtime.context import Context
from ..runtime.registries import SurfaceRegistry


@runtime_checkable
class SurfaceDecorationHost(Protocol):
    """Surface capability for widgets painted between the background and content."""

    def install_background_decoration(self, widget: QWidget) -> None:
        """Install one widget behind the surface's content."""


class RootSurface(QWidget):
    """Generic root surface with a background-decoration layer."""

    def __init__(self) -> None:
        super().__init__()
        self._background_decorations: list[QWidget] = []

    def install_background_decoration(self, widget: QWidget) -> None:
        """Parent and stack one decoration immediately above the styled background."""

        widget.setParent(self)
        widget.setGeometry(self.rect())
        widget.lower()
        self._background_decorations.append(widget)

    def resizeEvent(self, event: QResizeEvent) -> None:  # type: ignore[override]
        """Keep all background decorations fitted to the surface."""

        super().resizeEvent(event)
        for decoration in self._background_decorations:
            decoration.setGeometry(self.rect())


def register_surfaces(registry: SurfaceRegistry) -> None:
    """Register the generic surface builder.

    Args:
        registry: Surface registry owned by the runtime context.

    Returns:
        None.

    Side effects:
        Mutates the registry.
    """

    registry.register("surface", build_surface)


def build_surface(config: SurfaceConfig, context: Context) -> QWidget:
    """Build a generic root surface from child component configs.

    Args:
        config: Surface config containing child components.
        context: Runtime context used to build child components.

    Returns:
        Root surface widget.

    Side effects:
        Constructs child widgets via the component registry.
    """

    central = RootSurface()
    central.setObjectName("rootSurface")
    central.setProperty("componentType", "surface")
    central.setProperty("componentId", config.id)
    central.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    layout = QVBoxLayout(central)
    layout.setContentsMargins(*config.margins)
    layout.setSpacing(config.spacing)
    for component in config.components:
        widget = context.components.build(component, context, host=central)
        layout.addWidget(widget)
    return central
