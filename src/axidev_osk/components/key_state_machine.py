from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class KeyInteractionState(str, Enum):
    IDLE = "idle"
    PRESSED = "pressed"
    LATCHED = "latched"
    LATCHED_PRESSED = "latched_pressed"


@dataclass(frozen=True, slots=True)
class KeyStateChange:
    previous: KeyInteractionState
    current: KeyInteractionState
    reason: str


StateListener = Callable[[KeyStateChange], None]


class KeyStateMachine:
    def __init__(self, *, latchable: bool = False, initial_latched: bool = False) -> None:
        self._latchable = latchable
        self._state = self._compose_state(pressed=False, latched=initial_latched)
        self._listeners: list[StateListener] = []

    @property
    def latchable(self) -> bool:
        return self._latchable

    @property
    def state(self) -> KeyInteractionState:
        return self._state

    @property
    def is_pressed(self) -> bool:
        return self._state in {
            KeyInteractionState.PRESSED,
            KeyInteractionState.LATCHED_PRESSED,
        }

    @property
    def is_latched(self) -> bool:
        return self._state in {
            KeyInteractionState.LATCHED,
            KeyInteractionState.LATCHED_PRESSED,
        }

    def add_listener(self, listener: StateListener) -> None:
        self._listeners.append(listener)

    def press(self) -> None:
        self._transition_to(self._compose_state(pressed=True, latched=self.is_latched), "press")

    def release(self) -> None:
        self._transition_to(self._compose_state(pressed=False, latched=self.is_latched), "release")

    def toggle_latched(self) -> None:
        if not self._latchable:
            return
        self.set_latched(not self.is_latched, reason="toggle_latched")

    def set_latched(self, latched: bool, *, reason: str = "set_latched") -> None:
        if not self._latchable:
            return
        self._transition_to(self._compose_state(pressed=self.is_pressed, latched=latched), reason)

    def _compose_state(self, *, pressed: bool, latched: bool) -> KeyInteractionState:
        if pressed and latched:
            return KeyInteractionState.LATCHED_PRESSED
        if pressed:
            return KeyInteractionState.PRESSED
        if latched:
            return KeyInteractionState.LATCHED
        return KeyInteractionState.IDLE

    def _transition_to(self, next_state: KeyInteractionState, reason: str) -> None:
        if next_state == self._state:
            return

        previous = self._state
        self._state = next_state
        change = KeyStateChange(previous=previous, current=next_state, reason=reason)
        for listener in tuple(self._listeners):
            listener(change)
