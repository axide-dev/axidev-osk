"""Registered generic messages routed through one synchronous FIFO queue."""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar, cast

from ..messages import DataMap, MessageResult, RuntimeAction, RuntimeEvent, RuntimeMessage, copy_data_map


DecodedT = TypeVar("DecodedT")
Decoder = Callable[[DataMap], DecodedT]
MessageHandler = Callable[[DecodedT], MessageResult]
Unsubscribe = Callable[[], None]
Wake = Callable[[], None]

_logger = logging.getLogger(__name__)
_DRAIN_WARNING_INTERVAL = 10_000


@dataclass(slots=True)
class _ActionDefinition(Generic[DecodedT]):
    decoder: Decoder[DecodedT]
    handler: MessageHandler[DecodedT]


@dataclass(slots=True)
class _EventDefinition(Generic[DecodedT]):
    decoder: Decoder[DecodedT]
    handlers: list[tuple[Callable[[object], MessageResult], bool]] = field(default_factory=list)


class Dispatcher:
    """Own registered message definitions and drain them in FIFO order.

    Handlers run only on the thread that created the dispatcher. Messages
    sent from any other thread wait in a locked inbox, and the optional
    ``wake`` callback asks the owner thread to call ``process_pending``.
    """

    def __init__(self, *, wake: Wake | None = None) -> None:
        self._actions: dict[str, _ActionDefinition[object]] = {}
        self._events: dict[str, _EventDefinition[object]] = {}
        self._queue: deque[RuntimeMessage] = deque()
        self._draining = False
        self._owner_thread = threading.get_ident()
        self._inbox: deque[RuntimeMessage] = deque()
        self._inbox_lock = threading.Lock()
        self._wake = wake

    def set_wake(self, wake: Wake | None) -> None:
        """Set the callback that schedules ``process_pending`` on the owner thread."""

        self._wake = wake

    def process_pending(self) -> None:
        """Drain messages sent from other threads; call on the owner thread."""

        if threading.get_ident() != self._owner_thread:
            raise RuntimeError("Runtime messages must be processed on the dispatcher owner thread")
        if not self._draining:
            self._drain()

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

        return self._subscribe(name, cast(Callable[[object], MessageResult], handler), raw=False)

    def add_raw_event_handler(
        self,
        name: str,
        handler: Callable[[DataMap], MessageResult],
    ) -> Unsubscribe:
        """Subscribe a handler that receives a copy of the plain event arguments.

        Profile callbacks use this so they see the same plain data a Lua
        callback would. The event is still validated by its decoder first.
        """

        return self._subscribe(name, cast(Callable[[object], MessageResult], handler), raw=True)

    def has_event(self, name: str) -> bool:
        return name in self._events

    def _subscribe(self, name: str, handler: Callable[[object], MessageResult], *, raw: bool) -> Unsubscribe:
        definition = self._events.get(name)
        if definition is None:
            raise ValueError(f"Event {name!r} is not registered")
        entry = (handler, raw)
        definition.handlers.append(entry)

        def unsubscribe() -> None:
            if entry in definition.handlers:
                definition.handlers.remove(entry)

        return unsubscribe

    def dispatch_action(self, action: RuntimeAction) -> None:
        """Append an action and drain the queue unless a drain is active."""

        self._enqueue(action)

    def dispatch_event(self, event: RuntimeEvent) -> None:
        """Append an event and drain the queue unless a drain is active."""

        self._enqueue(event)

    def _enqueue(self, message: RuntimeMessage) -> None:
        if threading.get_ident() != self._owner_thread:
            with self._inbox_lock:
                self._inbox.append(message)
            wake = self._wake
            if wake is not None:
                wake()
            return
        self._queue.append(message)
        if self._draining:
            return
        self._drain()

    def _take_inbox(self) -> None:
        with self._inbox_lock:
            self._queue.extend(self._inbox)
            self._inbox.clear()

    def _drain(self) -> None:
        self._draining = True
        processed = 0
        try:
            while True:
                if not self._queue:
                    self._take_inbox()
                    if not self._queue:
                        break
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
        for handler, raw in tuple(definition.handlers):
            try:
                self._append_results(handler(copy_data_map(event.arguments) if raw else decoded))
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
