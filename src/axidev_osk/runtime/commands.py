"""Queue-ready command DTOs applied by services and runtime controllers."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import KeySpec


@dataclass(frozen=True, slots=True)
class KeyboardRegisterKeySpec:
    """Command registering a key for backend state observation.

    Attributes:
        layout_id: Deterministic keyboard layout instance ID.
        component_id: Deterministic key component ID.
        key_spec: Key semantics to observe.
    """

    layout_id: str
    component_id: str
    key_spec: KeySpec


@dataclass(frozen=True, slots=True)
class KeyboardKeyDown:
    """Command requesting keyboard output for a key press.

    Attributes:
        layout_id: Deterministic keyboard layout instance ID.
        key_spec: Key semantics to emit.
    """

    layout_id: str
    key_spec: KeySpec
    component_id: str | None = None


@dataclass(frozen=True, slots=True)
class KeyboardKeyUp:
    """Command requesting release of a key press owned by the keyboard service.

    Attributes:
        layout_id: Deterministic keyboard layout instance ID.
        key_spec: Key semantics to release.
    """

    layout_id: str
    key_spec: KeySpec
    component_id: str | None = None


@dataclass(frozen=True, slots=True)
class KeyboardSyncLatchedKey:
    """Command requesting backend synchronization for a latched modifier.

    Attributes:
        layout_id: Deterministic keyboard layout instance ID.
        key_spec: Latchable key semantics.
        latched: Desired latched state.
    """

    layout_id: str
    key_spec: KeySpec
    latched: bool
    component_id: str | None = None


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
class WindowToggleOpacity:
    """Command toggling a managed window's low-opacity input-blocking mode."""

    window_id: str
    component_id: str
    opacity: float


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


RuntimeCommand = KeyboardRegisterKeySpec | KeyboardKeyDown | KeyboardKeyUp | KeyboardSyncLatchedKey | StateSet | WindowShow | WindowHide | WindowToggleOpacity | WindowClose | AppQuit
