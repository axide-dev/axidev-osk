"""Synchronous event and command dispatcher with queue-ready DTO boundaries."""

from __future__ import annotations

from collections.abc import Callable

from typing import TYPE_CHECKING

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
Unsubscribe = Callable[[], None]


class Dispatcher:
    """Routes runtime events and commands synchronously for now.

    The public shape accepts DTOs and applies commands without returning service
    results, which keeps UI code independent from direct service calls and allows
    a later async queue swap.
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
                KeyboardKeyDown: lambda command: context.keyboard.key_down(  # type: ignore[union-attr]
                    command.layout,
                    command.key_spec,
                ),
                KeyboardKeyUp: lambda command: context.keyboard.key_up(command.layout, command.key_spec),  # type: ignore[union-attr]
                KeyboardSyncLatchedKey: lambda command: context.keyboard.sync_latched_key(  # type: ignore[union-attr]
                    command.layout,
                    command.key_spec,
                    command.latched,
                ),
                StateSet: lambda command: context.state.set(command.namespace, command.key, command.value),
            }
        )

    def add_event_handler(self, handler: EventHandler) -> Unsubscribe:
        """Register an event observer.

        Args:
            handler: Callable invoked for every dispatched event.

        Returns:
            Callable that removes the handler when invoked.

        Side effects:
            Mutates dispatcher handler list.
        """

        self._event_handlers.append(handler)

        def unsubscribe() -> None:
            if handler in self._event_handlers:
                self._event_handlers.remove(handler)

        return unsubscribe

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

    def dispatch_command(self, command: RuntimeCommand) -> None:
        """Apply a command without returning its handler result.

        This is the queue-ready dispatch path: when the runtime gains a
        proper async queue, ``dispatch_command`` will enqueue the command
        for asynchronous handling and callers will receive results
        through events. New call sites should use this method.

        Args:
            command: Runtime command DTO.

        Returns:
            None.

        Side effects:
            Invokes the command handler synchronously.
        """

        self._dispatch_command_internal(command)

    def _dispatch_command_internal(self, command: RuntimeCommand) -> object | None:
        """Look up and invoke a command handler.

        Args:
            command: Runtime command DTO.

        Returns:
            Handler-specific result, or ``None`` for fire-and-forget
            handlers.

        Side effects:
            Invokes the command handler synchronously.
        """

        handler = self._command_handlers.get(type(command))
        if handler is None:
            raise ValueError(f"No command handler registered for {type(command).__name__}")
        return handler(command)
