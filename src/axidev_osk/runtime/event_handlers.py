"""Default runtime event and command handler registration."""

from __future__ import annotations

from typing import Protocol

from .commands import (
    AppQuit,
    KeyboardKeyDown,
    KeyboardRegisterKeySpec,
    KeyboardKeyUp,
    KeyboardSyncLatchedKey,
    StateSet,
    WindowClose,
    WindowHide,
    WindowShow,
    WindowToggleOpacity,
)
from .events import ComponentPressed, HotCornerTriggered
from .registries import EventHandlerRegistry


class _WindowVisibilityManager(Protocol):
    """Minimal window-manager surface needed by hot-corner routing."""

    def is_visible(self, window_id: str) -> bool:
        """Return whether the managed window is currently visible."""

    def is_minimized(self, window_id: str) -> bool:
        """Return whether the managed window is currently minimized."""

    def is_opacity_reduced(self, window_id: str) -> bool:
        """Return whether the managed window is in low-opacity mode."""


def register_context_command_handlers(registry: EventHandlerRegistry) -> None:
    """Register context-level command handlers in deterministic order."""

    registry.register_command_handler(
        KeyboardRegisterKeySpec,
        lambda context: lambda command: context.keyboard.register_key_spec(
            command.layout_id,
            command.key_spec,
            component_id=command.component_id,
        ),
    )
    registry.register_command_handler(
        KeyboardKeyDown,
        lambda context: lambda command: context.keyboard.key_down(command.layout_id, command.key_spec),
    )
    registry.register_command_handler(
        KeyboardKeyUp,
        lambda context: lambda command: context.keyboard.key_up(command.layout_id, command.key_spec),
    )
    registry.register_command_handler(
        KeyboardSyncLatchedKey,
        lambda context: lambda command: context.keyboard.sync_latched_key(
            command.layout_id,
            command.key_spec,
            command.latched,
        ),
    )
    registry.register_command_handler(
        StateSet,
        lambda context: lambda command: context.state.set(command.namespace, command.key, command.value),
    )


def register_event_handlers(registry: EventHandlerRegistry) -> None:
    """Register application-level runtime handlers in deterministic order."""

    registry.register_command_handler(
        WindowShow,
        lambda runtime: lambda command: runtime._window_manager.show(command.window_id),
    )
    registry.register_command_handler(
        WindowHide,
        lambda runtime: lambda command: runtime._window_manager.hide(command.window_id),
    )
    registry.register_command_handler(
        WindowClose,
        lambda runtime: lambda command: runtime._window_manager.close(command.window_id),
    )
    registry.register_command_handler(
        WindowToggleOpacity,
        lambda runtime: lambda command: runtime._window_manager.toggle_opacity(
            command.window_id,
            component_id=command.component_id,
            opacity=command.opacity,
        ),
    )
    registry.register_command_handler(
        AppQuit,
        lambda runtime: lambda command: runtime._app.exit(command.exit_code),
    )
    registry.register_event_handler(lambda runtime: runtime._handle_window_close_requested)
    registry.register_event_handler(lambda runtime: runtime._handle_hot_corner_triggered)
    registry.register_event_handler(lambda runtime: runtime._handle_component_pressed)


def route_hot_corner_triggered(event: object, runtime: object) -> None:
    """Map hot-corner events to managed window visibility commands."""

    if not isinstance(event, HotCornerTriggered):
        return
    config = runtime._config  # noqa: SLF001
    dispatcher = runtime._dispatcher  # noqa: SLF001
    window_manager: _WindowVisibilityManager = runtime._window_manager  # noqa: SLF001
    for window_id in config.hot_corner.bindings.get(event.corner, []):
        if window_manager.is_minimized(window_id):
            dispatcher.dispatch_command(WindowShow(window_id))
        elif window_manager.is_opacity_reduced(window_id):
            dispatcher.dispatch_command(WindowShow(window_id))
        elif window_manager.is_visible(window_id):
            dispatcher.dispatch_command(WindowHide(window_id))
        else:
            dispatcher.dispatch_command(WindowShow(window_id))


def route_component_pressed(event: object, runtime: object) -> None:
    """Map configured key actions to managed-window commands."""

    if not isinstance(event, ComponentPressed) or event.key_spec is None:
        return
    action = event.key_spec.action
    if action is None:
        return
    if action.kind == "toggle-opacity":
        runtime._dispatcher.dispatch_command(  # noqa: SLF001
            WindowToggleOpacity(
                window_id=action.target_window_id,
                component_id=event.component_id,
                opacity=action.opacity,
            )
        )
