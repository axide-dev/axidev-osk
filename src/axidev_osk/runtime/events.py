"""Queue-ready event DTOs emitted by UI components and runtime controllers."""

from __future__ import annotations

from dataclasses import dataclass

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
    """

    component_id: str


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
class KeyLatchChanged:
    layout: str
    key_id: str
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
    """A prompt window resolved to the selected button role.

    Attributes:
        prompt_id: Deterministic prompt ID.
        result: Selected prompt button role.
    """

    prompt_id: str
    result: str


RuntimeEvent = (
    ComponentPressed
    | ComponentReleased
    | ComponentStateChanged
    | BackendKeyStateChanged
    | KeyLatchChanged
    | WindowCloseRequested
    | PromptResolved
)
