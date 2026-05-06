"""Synchronous event and command dispatcher with queue-ready DTO boundaries."""

from __future__ import annotations

from collections.abc import Callable

from typing import TYPE_CHECKING, Any

from .commands import (
    KeyboardKeyDown,
    KeyboardKeyUp,
    KeyboardSyncLatchedKey,
    RuntimeCommand,
    StateSet,
)
from .events import RuntimeEvent

if TYPE_CHECKING:
    from .context import Context


EventHandler = Callable[[RuntimeEvent], object | None]
CommandHandler = Callable[[RuntimeCommand], object | None]


class Dispatcher:
    """Routes runtime events and commands synchronously for now.

    The public shape accepts DTOs and returns command results, which keeps UI code
    independent from direct service calls and allows a later async queue swap.
    """

    def __init__(self) -> None:
        """Create an unbound dispatcher.

        Args:
            None.

        Returns:
            None.

        Side effects:
            None.
        """

        self._context: Context | None = None
        self._event_handlers: list[EventHandler] = []
        self._command_handlers: dict[type[object], CommandHandler] = {}

    def bind_context(self, context: "Context") -> None:
        """Bind the main context after all runtime objects are created.

        Args:
            context: Runtime context.

        Returns:
            None.

        Side effects:
            Installs default command handlers.
        """

        self._context = context
        self._command_handlers.update(
            {
                KeyboardKeyDown: lambda command: context.keyboard.key_down(command.key_spec, command.latched_keys),  # type: ignore[union-attr]
                KeyboardKeyUp: lambda command: context.keyboard.key_up(command.active_press),  # type: ignore[union-attr]
                KeyboardSyncLatchedKey: lambda command: context.keyboard.sync_latched_key(  # type: ignore[union-attr]
                    command.key_spec,
                    command.latched,
                    command.active_press,
                ),
                StateSet: lambda command: context.state.set(command.namespace, command.key, command.value),
            }
        )

    def add_event_handler(self, handler: EventHandler) -> None:
        """Register an event observer.

        Args:
            handler: Callable invoked for every dispatched event.

        Returns:
            None.

        Side effects:
            Mutates dispatcher handler list.
        """

        self._event_handlers.append(handler)

    def add_command_handler(self, command_type: type[object], handler: CommandHandler) -> None:
        """Register or replace a command handler.

        Args:
            command_type: DTO class handled by ``handler``.
            handler: Callable that applies the command.

        Returns:
            None.

        Side effects:
            Mutates dispatcher handler map.
        """

        self._command_handlers[command_type] = handler

    def dispatch_event(self, event: RuntimeEvent) -> None:
        """Dispatch an event to registered observers.

        Args:
            event: Runtime event DTO.

        Returns:
            None.

        Side effects:
            Invokes registered handlers synchronously.
        """

        for handler in tuple(self._event_handlers):
            handler(event)

    def dispatch_command(self, command: RuntimeCommand) -> Any:
        """Apply a command and return its handler result.

        Args:
            command: Runtime command DTO.

        Returns:
            Handler-specific result.

        Side effects:
            Invokes the command handler synchronously.
        """

        handler = self._command_handlers.get(type(command))
        if handler is None:
            raise ValueError(f"No command handler registered for {type(command).__name__}")
        return handler(command)
