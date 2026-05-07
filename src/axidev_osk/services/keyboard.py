"""Keyboard service boundary used by runtime commands and components."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from ..keyboard_io import AxidevIoKeyboardBackend, PermissionSetupOutcome
from ..models import KeySpec
from ..runtime.events import BackendKeyStateChanged

if TYPE_CHECKING:
    from ..runtime.context import Context

KeyStateListener = Callable[[str, bool], None]
Unsubscribe = Callable[[], None]

_logger = logging.getLogger(__name__)


class KeyboardService:
    """Owns keyboard backend lifecycle and exposes command-friendly methods."""

    def __init__(self, backend: AxidevIoKeyboardBackend | None = None) -> None:
        """Create a keyboard service.

        Args:
            backend: Optional backend, primarily for tests.

        Returns:
            None.

        Side effects:
            None until ``initialize`` is called.
        """

        self._backend = backend or AxidevIoKeyboardBackend()
        self._shutdown = False
        self._context: Context | None = None
        self._active_presses: dict[tuple[str, str], object | None] = {}
        self._specs_by_key_name: dict[str, list[tuple[str, KeySpec]]] = {}
        self._backend_listener_unsubscribe: Unsubscribe | None = None

    def bind_context(self, context: "Context") -> None:
        """Bind the runtime context used for events and state updates."""

        self._context = context
        self._ensure_backend_listener()

    @property
    def ready(self) -> bool:
        """Return whether keyboard output is available."""

        return self._backend.ready

    @property
    def status_text(self) -> str:
        """Return the user-facing backend status text."""

        return self._backend.status_text

    @property
    def needs_permission_setup(self) -> bool:
        """Return whether Linux input permissions need setup."""

        return self._backend.needs_permission_setup

    @property
    def permission_setup_text(self) -> str:
        """Return user-facing Linux permission setup guidance."""

        return self._backend.permission_setup_text

    @property
    def permission_setup_script_path(self) -> Path | None:
        """Return the bundled permission helper path when available."""

        return self._backend.permission_setup_script_path

    def initialize(self) -> bool:
        """Initialize keyboard output.

        Args:
            None.

        Returns:
            ``True`` when keyboard output is ready.

        Side effects:
            Initializes the backend and may start backend listeners.
        """

        initialized = self._backend.initialize()
        self._ensure_backend_listener()
        return initialized

    def shutdown(self) -> None:
        """Shut down keyboard output exactly once.

        Args:
            None.

        Returns:
            None.

        Side effects:
            Releases latched keys and shuts down backend resources.
        """

        if self._shutdown:
            _logger.info("Keyboard backend shutdown already completed")
            return
        self._shutdown = True
        started_at = time.perf_counter()
        _logger.info("Shutting down keyboard backend")
        self._backend.shutdown()
        _logger.info("Keyboard backend shutdown completed in %.3fs", time.perf_counter() - started_at)

    def setup_permissions(self) -> PermissionSetupOutcome:
        """Run backend permission setup.

        Args:
            None.

        Returns:
            Permission setup outcome from the backend.

        Side effects:
            May run helper scripts and update backend readiness/status.
        """

        return self._backend.setup_permissions()

    def add_key_state_listener(self, listener: KeyStateListener) -> Unsubscribe:
        """Subscribe to backend key state changes.

        Args:
            listener: Callable receiving canonical key name and pressed state.

        Returns:
            Callable that unsubscribes the listener.

        Side effects:
            Mutates backend listener registration.
        """

        return self._backend.add_key_state_listener(listener)

    def register_key_spec(self, layout: str, spec: KeySpec) -> str | None:
        """Register a key spec for backend state updates and return its backend key name."""

        key_name = self.key_name_for_spec(spec)
        key_id = self._state_key_for_spec(spec)
        if key_id is None:
            return key_name
        if self._context is not None and self._context.state.get(f"keyboard.key_states:{layout}", key_id) is None:
            self._write_key_state(layout, key_id, pressed=False, latched=False)
        if key_name is not None:
            registrations = self._specs_by_key_name.setdefault(key_name, [])
            registration = (layout, spec)
            if registration not in registrations:
                registrations.append(registration)
            if self._backend.is_key_down(key_name):
                self._emit_key_state(layout, key_id, pressed=True, latched=False)
        return key_name

    def is_key_down(self, key_name: str) -> bool:
        """Return whether a canonical key is currently down."""

        return self._backend.is_key_down(key_name)

    def key_name_for_spec(self, spec: KeySpec) -> str | None:
        """Resolve the backend key name for a key spec."""

        return self._backend.key_name_for_spec(spec)

    def key_down(self, layout: str, spec: KeySpec, latched_keys: Mapping[str, bool]) -> None:
        """Emit a key-down action through the backend."""

        active_press = self._backend.key_down(spec, latched_keys)
        key_id = self._state_key_for_spec(spec)
        if key_id is not None:
            self._active_presses[(layout, key_id)] = active_press
            self._emit_key_state(layout, key_id, pressed=True, latched=bool(latched_keys.get(key_id, False)))

    def key_up(self, layout: str, spec: KeySpec) -> None:
        """Emit a key-up action through the backend."""

        key_id = self._state_key_for_spec(spec)
        active_press = self._active_presses.pop((layout, key_id), None) if key_id is not None else None
        self._backend.key_up(active_press)
        if key_id is not None:
            latched = self._read_latched(layout, key_id)
            self._emit_key_state(layout, key_id, pressed=False, latched=latched)

    def sync_latched_key(self, layout: str, spec: KeySpec, latched: bool) -> None:
        """Synchronize a latched modifier with backend held-key state."""

        key_id = self._state_key_for_spec(spec)
        active_press = self._active_presses.get((layout, key_id)) if key_id is not None else None
        synced_press = self._backend.sync_latched_key(spec, latched, active_press)
        if key_id is not None:
            if synced_press is None:
                self._active_presses.pop((layout, key_id), None)
            else:
                self._active_presses[(layout, key_id)] = synced_press
            self._emit_key_state(layout, key_id, pressed=latched, latched=latched)

    def _handle_backend_key_state_change(self, key_name: str, pressed: bool) -> None:
        for layout, spec in self._specs_by_key_name.get(key_name, []):
            key_id = self._state_key_for_spec(spec)
            if key_id is None:
                continue
            self._emit_key_state(layout, key_id, pressed=pressed, latched=self._read_latched(layout, key_id))

    def _emit_key_state(self, layout: str, key_id: str, *, pressed: bool, latched: bool) -> None:
        self._write_key_state(layout, key_id, pressed=pressed, latched=latched)
        if self._context is not None:
            self._context.dispatcher.dispatch_event(
                BackendKeyStateChanged(layout=layout, key_id=key_id, pressed=pressed, latched=latched)
            )

    def _write_key_state(self, layout: str, key_id: str, *, pressed: bool, latched: bool) -> None:
        if self._context is None:
            return
        self._context.state.set(
            f"keyboard.key_states:{layout}",
            key_id,
            {"pressed": pressed, "latched": latched},
        )

    def _read_latched(self, layout: str, key_id: str) -> bool:
        if self._context is None:
            return False
        value = self._context.state.get(f"keyboard.key_states:{layout}", key_id, {})
        return bool(value.get("latched", False)) if isinstance(value, dict) else False

    def _state_key_for_spec(self, spec: KeySpec) -> str | None:
        return spec.key_id or spec.io_key or spec.label

    def _ensure_backend_listener(self) -> None:
        if self._backend_listener_unsubscribe is None:
            self._backend_listener_unsubscribe = self._backend.add_key_state_listener(self._handle_backend_key_state_change)
