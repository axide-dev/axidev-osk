"""Builders for grid-related components."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

from ...config.models import ComponentConfig, KeyboardGridConfig, KeyboardStatusConfig
from ...runtime.context import Context
from ...runtime.registries import ComponentRegistry
from .keyboard import KeyboardWidget


def register(registry: ComponentRegistry) -> None:
    """Register grid-related component builders."""

    registry.register("keyboard-grid", build_keyboard_grid_component)
    registry.register("keyboard-status", build_keyboard_status_component)


def build_keyboard_grid_component(config: ComponentConfig, context: Context) -> QWidget:
    """Build a keyboard grid component from layout config."""

    if not isinstance(config, KeyboardGridConfig):
        raise TypeError(f"Expected KeyboardGridConfig, got {type(config).__name__}")
    widget = KeyboardWidget(layout_config=config.layout, context=context)
    widget.setProperty("componentId", config.id)
    return widget


def build_keyboard_status_component(config: ComponentConfig, context: Context) -> QWidget:
    """Build a keyboard backend status label when output is unavailable."""

    if not isinstance(config, KeyboardStatusConfig):
        raise TypeError(f"Expected KeyboardStatusConfig, got {type(config).__name__}")
    label = QLabel(context.keyboard.status_text)
    label.setObjectName("statusLabel")
    label.setProperty("componentType", "keyboard-status")
    label.setProperty("componentId", config.id)
    label.setWordWrap(True)
    label.setVisible(not context.keyboard.ready)
    return label
