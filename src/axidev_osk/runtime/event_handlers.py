"""Default runtime event and command handler registration."""

from __future__ import annotations

from .commands import AppQuit, WindowClose, WindowHide, WindowShow
from .registries import EventHandlerRegistry


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
        AppQuit,
        lambda runtime: lambda command: runtime._app.exit(command.exit_code),
    )
    registry.register_event_handler(lambda runtime: runtime._handle_window_close_requested)
    registry.register_event_handler(lambda runtime: runtime._handle_hot_corner_triggered)
