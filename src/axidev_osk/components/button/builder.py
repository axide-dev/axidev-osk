"""Builder for generic prompt/action buttons."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtWidgets import QPushButton, QWidget


from ...config.models import ButtonConfig, ComponentConfig
from ...messages import MessageResult
from ...runtime.context import Context
from ...runtime.events import STATE_CHANGED, StateChangedArguments, component_pressed, component_released
from ...runtime.registries import ComponentRegistry
from ...runtime.source import SourcePath


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
    source_path: SourcePath,
    host: QWidget | None = None,
) -> QPushButton:
    """Build a QPushButton from declarative config.

    Args:
        config: Button component config.
        context: Runtime context.
        source_path: Exact runtime identity used for events and state.
        host: Unused; accepted for registry signature parity.

    Returns:
        Constructed QPushButton.

    Side effects:
        Subscribes to runtime state and emits raw component interactions.
    """

    del host
    if not isinstance(config, ButtonConfig):
        raise TypeError(f"Expected ButtonConfig, got {type(config).__name__}")
    button = QPushButton(config.label)
    button.setProperty("componentType", "button")
    button.setProperty("componentId", config.id)
    if config.object_name is not None:
        button.setObjectName(config.object_name)
    if config.style_sheet is not None:
        button.setStyleSheet(config.style_sheet)

    def render_state(state: Mapping[str, object]) -> None:
        button.setProperty("pressed", bool(state.get("pressed", False)))
        button.setProperty("latched", bool(state.get("latched", False)))
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def receive_state(event: StateChangedArguments) -> MessageResult:
        if event.source == source_path:
            render_state(event.state)
        return []

    render_state(context.behaviors.state_snapshot(source_path))
    unsubscribe = context.dispatcher.add_event_handler(STATE_CHANGED, receive_state)
    button.destroyed.connect(lambda _object=None: unsubscribe())
    button.pressed.connect(
        lambda: context.dispatcher.dispatch_event(component_pressed(source_path))
    )
    button.released.connect(
        lambda: context.dispatcher.dispatch_event(component_released(source_path))
    )
    return button
