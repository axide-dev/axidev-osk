"""Interaction state machine for key buttons.

Tracks the orthogonal pressed/latched dimensions of a button and exposes
a single composed ``KeyInteractionState`` value plus a listener stream
of ``KeyStateChange`` records. Pure data; no Qt dependencies.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class KeyInteractionState(str, Enum):
    """Composed pressed/latched state of a key button."""

    IDLE = "idle"
    PRESSED = "pressed"
    LATCHED = "latched"
    LATCHED_PRESSED = "latched_pressed"


@dataclass(frozen=True, slots=True)
class KeyStateChange:
    """Listener payload describing a single state transition.

    Attributes:
        previous: State immediately before the transition.
        current: State after the transition.
        reason: Free-form tag identifying which call drove the change
            (``"press"``, ``"release"``, ``"toggle_latched"``, ...).
    """

    previous: KeyInteractionState
    current: KeyInteractionState
    reason: str


StateListener = Callable[[KeyStateChange], None]


class KeyStateMachine:
    """Pressed/latched state machine with listener fan-out.

    Side effects:
        Listeners registered via ``add_listener`` are invoked synchronously
        on every distinct transition. Listener order is registration order;
        a snapshot of the listener list is taken before dispatch so a
        listener may freely register or remove other listeners during
        notification without affecting the current dispatch.
    """

    def __init__(self, *, latchable: bool = False, initial_latched: bool = False) -> None:
        self._latchable = latchable
        self._state = self._compose_state(pressed=False, latched=initial_latched)
        self._listeners: list[StateListener] = []

    @property
    def latchable(self) -> bool:
        """Whether latch transitions are enabled for this key."""

        return self._latchable

    @property
    def state(self) -> KeyInteractionState:
        """Current composed interaction state."""

        return self._state

    @property
    def is_pressed(self) -> bool:
        """Whether the key is currently pressed."""

        return self._state in {
            KeyInteractionState.PRESSED,
            KeyInteractionState.LATCHED_PRESSED,
        }

    @property
    def is_latched(self) -> bool:
        """Whether the key is currently latched."""

        return self._state in {
            KeyInteractionState.LATCHED,
            KeyInteractionState.LATCHED_PRESSED,
        }

    def add_listener(self, listener: StateListener) -> None:
        """Register a synchronous state-change listener."""

        self._listeners.append(listener)

    def press(self) -> None:
        """Transition to the pressed state when needed."""

        self.set_pressed(True, reason="press")

    def release(self) -> None:
        """Transition out of the pressed state when needed."""

        self.set_pressed(False, reason="release")

    def set_pressed(self, pressed: bool, *, reason: str = "set_pressed") -> None:
        """Set the pressed dimension while preserving latch state."""

        self._transition_to(self._compose_state(pressed=pressed, latched=self.is_latched), reason)

    def toggle_latched(self) -> None:
        """Toggle latch state when this machine is latchable."""

        if not self._latchable:
            return
        self.set_latched(not self.is_latched, reason="toggle_latched")

    def set_latched(self, latched: bool, *, reason: str = "set_latched") -> None:
        """Set the latch dimension when this machine is latchable."""

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
