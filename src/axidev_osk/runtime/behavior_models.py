"""Typed records used by built-in component behavior kinds."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..messages import RuntimeAction, RuntimeEvent


class KeyboardBehaviorMode(str, Enum):
    """How a keyboard behavior reacts to press and release interactions."""

    MOMENTARY = "momentary"
    LOGICAL_TOGGLE = "logical-toggle"
    HELD_TOGGLE = "held-toggle"


@dataclass(frozen=True, slots=True)
class KeyboardOutput:
    """Backend-ready output metadata with no visual component data."""

    output_key: str
    repeats: bool = True
    uses_active_state_tags: bool = True


@dataclass(frozen=True, slots=True)
class KeyboardBehavior:
    """Runtime interaction policy for one keyboard control."""

    mode: KeyboardBehaviorMode
    output: KeyboardOutput


@dataclass(frozen=True, slots=True)
class ActionBehavior:
    """Ordered configured actions for component press and release."""

    pressed_actions: tuple[RuntimeAction, ...] = ()
    released_actions: tuple[RuntimeAction, ...] = ()


class HookDecision(str, Enum):
    """Control decision returned by a blocking before-hook."""

    CONTINUE = "continue"
    CANCEL = "cancel"
    REPLACE = "replace"


@dataclass(frozen=True, slots=True)
class HookOutcome:
    """Side messages and optional default-control decision from one hook."""

    decision: HookDecision = HookDecision.CONTINUE
    messages: tuple[RuntimeEvent | RuntimeAction, ...] = ()
    replacement: tuple[RuntimeEvent | RuntimeAction, ...] = ()
