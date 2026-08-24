"""Registered generic messages routed through one synchronous FIFO queue."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar, cast

from ..messages import DataMap, MessageResult, RuntimeAction, RuntimeEvent, RuntimeMessage


DecodedT = TypeVar("DecodedT")
Decoder = Callable[[DataMap], DecodedT]
MessageHandler = Callable[[DecodedT], MessageResult]
Unsubscribe = Callable[[], None]

_logger = logging.getLogger(__name__)
_DRAIN_WARNING_INTERVAL = 10_000


@dataclass(slots=True)
class _ActionDefinition(Generic[DecodedT]):
    decoder: Decoder[DecodedT]
    handler: MessageHandler[DecodedT]


@dataclass(slots=True)
class _EventDefinition(Generic[DecodedT]):
    decoder: Decoder[DecodedT]
    handlers: list[MessageHandler[DecodedT]] = field(default_factory=list)


class Dispatcher:
    """Own registered message definitions and drain them in FIFO order."""

    def __init__(self) -> None:
        self._actions: dict[str, _ActionDefinition[object]] = {}
        self._events: dict[str, _EventDefinition[object]] = {}
        self._queue: deque[RuntimeMessage] = deque()
        self._draining = False

    def register_action(
        self,
        name: str,
        decoder: Decoder[DecodedT],
        handler: MessageHandler[DecodedT],
        *,
        override: bool = False,
    ) -> None:
        """Register one action definition, optionally replacing it in full."""

        if name in self._actions and not override:
            raise ValueError(f"Action {name!r} is already registered")
        if name in self._actions:
            _logger.warning("Overriding registered action %s", name)
        definition = _ActionDefinition(decoder=decoder, handler=handler)
        self._actions[name] = cast(_ActionDefinition[object], definition)

    def register_event(
        self,
        name: str,
        decoder: Decoder[DecodedT],
        *,
        override: bool = False,
    ) -> None:
        """Register one event definition, optionally replacing it in full."""

        if name in self._events and not override:
            raise ValueError(f"Event {name!r} is already registered")
        if name in self._events:
            _logger.warning("Overriding registered event %s", name)
        definition: _EventDefinition[DecodedT] = _EventDefinition(decoder=decoder)
        self._events[name] = cast(_EventDefinition[object], definition)

    def add_event_handler(
        self,
        name: str,
        handler: MessageHandler[DecodedT],
    ) -> Unsubscribe:
        """Subscribe a typed handler to one registered event name."""

        definition = self._events.get(name)
        if definition is None:
            raise ValueError(f"Event {name!r} is not registered")
        erased_handler = cast(MessageHandler[object], handler)
        definition.handlers.append(erased_handler)

        def unsubscribe() -> None:
            if erased_handler in definition.handlers:
                definition.handlers.remove(erased_handler)

        return unsubscribe

    def dispatch_action(self, action: RuntimeAction) -> None:
        """Append an action and drain the queue unless a drain is active."""

        self._enqueue(action)

    def dispatch_event(self, event: RuntimeEvent) -> None:
        """Append an event and drain the queue unless a drain is active."""

        self._enqueue(event)

    def _enqueue(self, message: RuntimeMessage) -> None:
        self._queue.append(message)
        if self._draining:
            return
        self._draining = True
        processed = 0
        try:
            while self._queue:
                current = self._queue.popleft()
                processed += 1
                if processed % _DRAIN_WARNING_INTERVAL == 0:
                    _logger.warning("Runtime queue drain has processed %d messages without returning", processed)
                if isinstance(current, RuntimeAction):
                    self._process_action(current)
                else:
                    self._process_event(current)
        finally:
            self._draining = False

    def _process_action(self, action: RuntimeAction) -> None:
        definition = self._actions.get(action.action)
        if definition is None:
            self._fail_action(action, stage="lookup", error=ValueError(f"Action {action.action!r} is not registered"))
            return
        try:
            decoded = definition.decoder(action.arguments)
        except Exception as exc:
            self._fail_action(action, stage="decode", error=exc)
            return
        try:
            self._append_results(definition.handler(decoded))
        except Exception as exc:
            self._fail_action(action, stage="execute", error=exc)

    def _process_event(self, event: RuntimeEvent) -> None:
        definition = self._events.get(event.event)
        if definition is None:
            _logger.error("Discarding unregistered event %s with arguments %r", event.event, event.arguments)
            return
        try:
            decoded = definition.decoder(event.arguments)
        except Exception:
            _logger.exception("Discarding event %s with invalid arguments %r", event.event, event.arguments)
            return
        for handler in tuple(definition.handlers):
            try:
                self._append_results(handler(decoded))
            except Exception:
                _logger.exception("Event handler failed for %s with arguments %r", event.event, event.arguments)
                return

    def _append_results(self, messages: MessageResult) -> None:
        for message in messages:
            if not isinstance(message, (RuntimeAction, RuntimeEvent)):
                raise TypeError(f"Message handlers must return runtime messages, got {type(message).__name__}")
        self._queue.extend(messages)

    def _fail_action(self, action: RuntimeAction, *, stage: str, error: Exception) -> None:
        _logger.error(
            "Action %s failed during %s with arguments %r: %s: %s",
            action.action,
            stage,
            action.arguments,
            type(error).__name__,
            error,
        )
        self._queue.append(
            RuntimeEvent(
                event="action.failed",
                arguments={
                    "action": action.action,
                    "arguments": action.arguments,
                    "stage": stage,
                    "exception_type": type(error).__name__,
                    "message": str(error),
                },
            )
        )
