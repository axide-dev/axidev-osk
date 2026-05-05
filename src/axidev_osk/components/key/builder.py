"""Builders for keyboard key and spacer components."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...config.models import ComponentConfig, KeyConfig, SpacerConfig
from ...runtime.context import Context
from ...runtime.registries import ComponentRegistry
from ..keyboard_metrics import DEFAULT_KEYBOARD_METRICS
from ..keyboard_widget import KeyboardWidget


def register(registry: ComponentRegistry) -> None:
    """Register key-related component builders.

    Args:
        registry: Component registry owned by the runtime context.

    Returns:
        None.

    Side effects:
        Mutates the registry.
    """

    registry.register("key", build_key_component)
    registry.register("spacer", build_spacer_component)


def build_key_component(config: ComponentConfig, context: Context) -> QWidget:
    """Build a key button component.

    Args:
        config: Key component config.
        context: Runtime context.

    Returns:
        Constructed key button widget.

    Side effects:
        Registers the key with the active keyboard widget builder scope.
    """

    if not isinstance(config, KeyConfig):
        raise TypeError(f"Expected KeyConfig, got {type(config).__name__}")
    owner = KeyboardWidget.current_builder()
    if owner is None:
        raise RuntimeError("Key components must be built inside a KeyboardWidget")
    return owner.build_key_from_config(config, context)


def build_spacer_component(config: ComponentConfig, context: Context) -> QWidget:
    """Build a spacer component.

    Args:
        config: Spacer component config.
        context: Runtime context.

    Returns:
        Transparent spacer widget.

    Side effects:
        None beyond widget construction.
    """

    del context
    if not isinstance(config, SpacerConfig):
        raise TypeError(f"Expected SpacerConfig, got {type(config).__name__}")
    metrics = DEFAULT_KEYBOARD_METRICS
    spacer = QWidget()
    spacer.setProperty("componentType", "spacer")
    spacer.setProperty("componentId", config.id)
    spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    spacer.setMinimumWidth(metrics.span_width(config.spec.width))
    spacer.setMinimumHeight(metrics.span_height(config.spec.height))
    spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return spacer
