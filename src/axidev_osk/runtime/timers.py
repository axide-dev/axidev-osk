"""Timers a profile starts and cancels by ID, and the ``timer.fired`` event they report.

A profile sends ``timer.start`` with an ID and a delay; after the delay the
engine posts ``timer.fired`` with that ID, and again every delay while the
timer repeats. Starting an ID that is already running restarts it with the new
delay. ``timer.cancel`` stops a timer, and cancelling one that is not running
does nothing. Timers belong to the running profile: stopping the profile
cancels every one of them.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QTimer

from ..messages import DataMap, MessageResult, RuntimeEvent
from .decoding import bool_value, int_value, non_empty_string_value, require_keys, validated_event
from .dispatcher import Dispatcher
from .event_fields import samples

TIMER_START = "timer.start"
TIMER_CANCEL = "timer.cancel"
TIMER_FIRED = "timer.fired"


@dataclass(frozen=True, slots=True)
class TimerStartArguments:
    id: str
    delay_ms: int
    repeat: bool


@dataclass(frozen=True, slots=True)
class TimerArguments:
    id: str = samples("example")


def decode_timer_start(arguments: DataMap) -> TimerStartArguments:
    require_keys(arguments, ("id", "delay_ms"), optional=("repeat",))
    delay_ms = int_value(arguments, "delay_ms")
    if delay_ms < 0:
        raise ValueError("Argument 'delay_ms' must be at least 0")
    return TimerStartArguments(
        id=non_empty_string_value(arguments, "id"),
        delay_ms=delay_ms,
        repeat=bool_value(arguments, "repeat") if "repeat" in arguments else False,
    )


def decode_timer(arguments: DataMap) -> TimerArguments:
    require_keys(arguments, ("id",))
    return TimerArguments(id=non_empty_string_value(arguments, "id"))


def timer_fired(timer_id: str) -> RuntimeEvent:
    return validated_event(TIMER_FIRED, {"id": timer_id}, decode_timer)


class Timers:
    """The running profile's timers, one Qt timer per ID, each posting ``timer.fired`` from the Qt thread."""

    def __init__(self, dispatcher: Dispatcher) -> None:
        self._dispatcher = dispatcher
        self._running: dict[str, QTimer] = {}

    def register(self) -> None:
        """Register the timer actions and the ``timer.fired`` event."""

        self._dispatcher.register_event(TIMER_FIRED, decode_timer)
        self._dispatcher.register_action(TIMER_START, decode_timer_start, self._start)
        self._dispatcher.register_action(TIMER_CANCEL, decode_timer, self._cancel)

    def cancel_all(self) -> None:
        """Stop every running timer."""

        for timer_id in list(self._running):
            self._stop(timer_id)

    def _start(self, arguments: TimerStartArguments) -> MessageResult:
        self._stop(arguments.id)
        timer = QTimer()
        timer.setSingleShot(not arguments.repeat)
        timer.timeout.connect(lambda timer_id=arguments.id, repeat=arguments.repeat: self._fire(timer_id, repeat))
        self._running[arguments.id] = timer
        timer.start(arguments.delay_ms)
        return []

    def _cancel(self, arguments: TimerArguments) -> MessageResult:
        self._stop(arguments.id)
        return []

    def _fire(self, timer_id: str, repeat: bool) -> None:
        if not repeat:
            done = self._running.pop(timer_id, None)
            if done is not None:
                done.deleteLater()
        # Posted, so the drain never runs inside Qt's timer event.
        self._dispatcher.post(timer_fired(timer_id))

    def _stop(self, timer_id: str) -> None:
        timer = self._running.pop(timer_id, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
