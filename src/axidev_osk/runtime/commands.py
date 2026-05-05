"""Queue-ready command DTOs applied by services and runtime controllers."""

from __future__ import annotations

from dataclasses import dataclass

from typing import Mapping

from ..models import KeySpec


@dataclass(frozen=True, slots=True)
class KeyboardKeyDown:
    """Command requesting keyboard output for a key press.

    Attributes:
        key_spec: Key semantics to emit.
        latched_keys: Snapshot of active latch groups.
    """

    key_spec: KeySpec
    latched_keys: Mapping[str, bool]


@dataclass(frozen=True, slots=True)
class KeyboardKeyUp:
    """Command requesting release of a backend press handle.

    Attributes:
        active_press: Backend-specific handle returned by ``KeyboardKeyDown``.
    """

    active_press: object | None


@dataclass(frozen=True, slots=True)
class KeyboardSyncLatchedKey:
    """Command requesting backend synchronization for a latched modifier.

    Attributes:
        key_spec: Latchable key semantics.
        latched: Desired latched state.
        active_press: Optional active press handle to reuse.
    """

    key_spec: KeySpec
    latched: bool
    active_press: object | None = None


@dataclass(frozen=True, slots=True)
class StateSet:
    """Command storing durable runtime state in the central state store.

    Attributes:
        namespace: State namespace, usually profile/window/layout/component identity.
        key: State key inside the namespace.
        value: Serializable state value.
    """

    namespace: str
    key: str
    value: object


@dataclass(frozen=True, slots=True)
class WindowShow:
    """Command requesting a managed window to be shown.

    Attributes:
        window_id: Deterministic window ID.
    """

    window_id: str


@dataclass(frozen=True, slots=True)
class WindowHide:
    """Command requesting a managed window to be hidden.

    Attributes:
        window_id: Deterministic window ID.
    """

    window_id: str


@dataclass(frozen=True, slots=True)
class WindowClose:
    """Command requesting a managed window to be closed.

    Attributes:
        window_id: Deterministic window ID.
    """

    window_id: str


@dataclass(frozen=True, slots=True)
class AppQuit:
    """Command requesting application shutdown.

    Attributes:
        exit_code: Process exit code supplied to QApplication.
    """

    exit_code: int = 0


RuntimeCommand = KeyboardKeyDown | KeyboardKeyUp | KeyboardSyncLatchedKey | StateSet | WindowShow | WindowHide | WindowClose | AppQuit
