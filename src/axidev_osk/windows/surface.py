"""Generic window surface builder."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..config.models import SurfaceConfig
from ..runtime.context import Context
from ..runtime.registries import SurfaceRegistry


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

    central = QWidget()
    central.setObjectName("rootSurface")
    central.setProperty("componentType", "surface")
    central.setProperty("componentId", config.id)
    central.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    layout = QVBoxLayout(central)
    layout.setContentsMargins(*config.margins)
    layout.setSpacing(config.spacing)
    for component in config.components:
        if getattr(component, "omit_when_ready", False) and context.keyboard.ready:
            continue
        widget = context.components.build(component, context)
        layout.addWidget(widget)
    return central
