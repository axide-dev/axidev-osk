"""Builder for generic prompt/action buttons."""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QWidget


from ...config.models import ButtonConfig, ComponentConfig
from ...runtime.context import Context
from ...runtime.registries import ComponentRegistry


def register(registry: ComponentRegistry) -> None:
    """Register the generic button component builder.

    Args:
        registry: Component registry owned by the runtime context.

    Returns:
        None.

    Side effects:
        Mutates the registry.
    """

    registry.register("button", build_button_component)


def build_button_component(
    config: ComponentConfig,
    context: Context,
    *,
    host: QWidget | None = None,
) -> QPushButton:
    """Build a QPushButton from declarative config.

    Args:
        config: Button component config.
        context: Runtime context.
        host: Unused; accepted for registry signature parity.

    Returns:
        Constructed QPushButton.

    Side effects:
        None beyond widget construction.
    """

    del context, host
    if not isinstance(config, ButtonConfig):
        raise TypeError(f"Expected ButtonConfig, got {type(config).__name__}")
    button = QPushButton(config.label)
    button.setProperty("componentType", "button")
    button.setProperty("componentId", config.id)
    button.setProperty("role", config.role)
    if config.object_name is not None:
        button.setObjectName(config.object_name)
    if config.style_sheet is not None:
        button.setStyleSheet(config.style_sheet)
    return button
