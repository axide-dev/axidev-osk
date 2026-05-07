"""Queue-ready event DTOs emitted by UI components and runtime controllers."""

from __future__ import annotations

from dataclasses import dataclass

from typing import Literal

from ..models import KeySpec


@dataclass(frozen=True, slots=True)
class ComponentPressed:
    """A component was pressed by the user.

    Attributes:
        component_id: Deterministic component ID.
        key_spec: Optional key semantics for keyboard components.
    """

    component_id: str
    key_spec: KeySpec | None = None


@dataclass(frozen=True, slots=True)
class ComponentReleased:
    """A component was released by the user.

    Attributes:
        component_id: Deterministic component ID.
        active_press: Backend-specific press handle returned by the press command.
    """

    component_id: str
    active_press: object | None = None


@dataclass(frozen=True, slots=True)
class ComponentStateChanged:
    """A component state changed and should be reflected in runtime state.

    Attributes:
        component_id: Deterministic component ID.
        key_id: Logical key group for latchable keys.
        latched: New latched state.
    """

    component_id: str
    key_id: str
    latched: bool


@dataclass(frozen=True, slots=True)
class BackendKeyStateChanged:
    layout: str
    key_id: str
    pressed: bool
    latched: bool


@dataclass(frozen=True, slots=True)
class WindowCloseRequested:
    """A managed window requested application shutdown confirmation.

    Attributes:
        window_id: Deterministic window ID.
    """

    window_id: str


@dataclass(frozen=True, slots=True)
class PromptResolved:
    """A prompt window resolved to an accepted or rejected outcome.

    Attributes:
        prompt_id: Deterministic prompt ID.
        result: Prompt result value.
    """

    prompt_id: str
    result: Literal["accepted", "rejected"]


RuntimeEvent = (
    ComponentPressed
    | ComponentReleased
    | ComponentStateChanged
    | BackendKeyStateChanged
    | WindowCloseRequested
    | PromptResolved
)
