"""Keyboard service boundary used by runtime commands and components."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from ..keyboard_io import AxidevIoKeyboardBackend, PermissionSetupOutcome
from ..models import KeySpec
from ..runtime.events import BackendKeyStateChanged, KeyLatchChanged

if TYPE_CHECKING:
    from ..runtime.context import Context

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
        self._press_handles: dict[tuple[str, str], object | None] = {}
        self._latched_keys: dict[tuple[str, str], bool] = {}
        self._specs_by_key_name: dict[str, list[tuple[str, KeySpec]]] = {}
        self._layouts: set[str] = set()
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

    def register_key_spec(self, layout: str, spec: KeySpec) -> str | None:
        """Register a key spec for backend state updates and return its backend key name."""

        key_name = self._backend.key_name_for_spec(spec)
        state_key = self._state_key_for_spec(spec)
        self._layouts.add(layout)
        if state_key is None:
            return key_name
        latched = self._is_spec_latched(layout, spec)
        if spec.key_id is not None:
            self._write_latch_state(layout, spec.key_id, latched)
        if self._context is not None and self._context.state.get(f"keyboard.key_states:{layout}", state_key) is None:
            self._write_key_state(layout, state_key, pressed=False, latched=latched)
        if key_name is not None:
            registrations = self._specs_by_key_name.setdefault(key_name, [])
            registration = (layout, spec)
            if registration not in registrations:
                registrations.append(registration)
            if self._backend.is_key_down(key_name):
                self._emit_key_state(layout, state_key, pressed=True, latched=latched)
        return key_name

    def is_latched(self, layout: str, key_id: str) -> bool:
        """Return the current latch state for a layout/key pair."""

        if (layout, key_id) in self._latched_keys:
            return self._latched_keys[(layout, key_id)]
        if self._context is None:
            return False
        return bool(self._context.state.get(f"keyboard.latches:{layout}", key_id, False))

    def reset_state(self) -> None:
        """Reset keyboard-owned transient and durable state for profile/config reloads."""

        layouts = set(self._layouts)
        layouts.update(layout for layout, _key_id in self._press_handles)
        layouts.update(layout for layout, _key_id in self._latched_keys)
        self._press_handles.clear()
        self._latched_keys.clear()
        if self._context is None:
            return
        for layout in layouts:
            self._context.state.clear_namespace(f"keyboard.key_states:{layout}")
            self._context.state.clear_namespace(f"keyboard.latches:{layout}")

    def key_down(self, layout: str, spec: KeySpec) -> None:
        """Emit a key-down action through the backend."""

        latched_keys = self._latched_snapshot(layout)
        press_handle = self._backend.key_down(spec, latched_keys)
        state_key = self._state_key_for_spec(spec)
        if state_key is not None and press_handle is not None:
            self._press_handles[(layout, state_key)] = press_handle
            self._emit_key_state(layout, state_key, pressed=True, latched=self._is_spec_latched(layout, spec))

    def key_up(self, layout: str, spec: KeySpec) -> None:
        """Emit a key-up action through the backend."""

        state_key = self._state_key_for_spec(spec)
        latched = self._is_spec_latched(layout, spec)
        press_handle = self._press_handles.pop((layout, state_key), None) if state_key is not None else None
        if not (spec.holds_when_latched and latched):
            self._backend.key_up(press_handle)
        if state_key is not None:
            self._emit_key_state(
                layout,
                state_key,
                pressed=self._pressed_snapshot(spec, latched=latched),
                latched=latched,
            )

    def sync_latched_key(self, layout: str, spec: KeySpec, latched: bool) -> None:
        """Synchronize a latched modifier with backend held-key state."""

        state_key = self._state_key_for_spec(spec)
        if spec.key_id is not None:
            self._set_latch_state(layout, spec.key_id, latched)
        press_handle = self._press_handles.get((layout, state_key)) if state_key is not None else None
        synced_press = self._backend.sync_latched_key(spec, latched, press_handle)
        if state_key is not None:
            if synced_press is None:
                self._press_handles.pop((layout, state_key), None)
            else:
                self._press_handles[(layout, state_key)] = synced_press
            if spec.holds_when_latched:
                self._emit_key_state(layout, state_key, pressed=latched, latched=latched)

    def _handle_backend_key_state_change(self, key_name: str, pressed: bool) -> None:
        for layout, spec in self._specs_by_key_name.get(key_name, []):
            key_id = self._state_key_for_spec(spec)
            if key_id is None:
                continue
            self._emit_key_state(layout, key_id, pressed=pressed, latched=self._is_spec_latched(layout, spec))

    def _set_latch_state(self, layout: str, key_id: str, latched: bool) -> None:
        self._layouts.add(layout)
        self._latched_keys[(layout, key_id)] = latched
        self._write_latch_state(layout, key_id, latched)
        if self._context is not None:
            self._context.dispatcher.dispatch_event(KeyLatchChanged(layout=layout, key_id=key_id, latched=latched))

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

    def _write_latch_state(self, layout: str, key_id: str, latched: bool) -> None:
        if self._context is not None:
            self._context.state.set(f"keyboard.latches:{layout}", key_id, latched)

    def _latched_snapshot(self, layout: str) -> dict[str, bool]:
        snapshot: dict[str, bool] = {}
        if self._context is not None:
            for _registered_layout, spec in self._registered_specs_for_layout(layout):
                key_id = spec.key_id
                if key_id is not None:
                    snapshot[key_id] = self.is_latched(layout, key_id)
        for (latched_layout, key_id), latched in self._latched_keys.items():
            if latched_layout == layout:
                snapshot[key_id] = latched
        return snapshot

    def _registered_specs_for_layout(self, layout: str) -> list[tuple[str, KeySpec]]:
        return [registration for registrations in self._specs_by_key_name.values() for registration in registrations if registration[0] == layout]

    def _state_key_for_spec(self, spec: KeySpec) -> str | None:
        return spec.io_key or spec.label or spec.key_id

    def _is_spec_latched(self, layout: str, spec: KeySpec) -> bool:
        return bool(spec.key_id is not None and self.is_latched(layout, spec.key_id))

    def _pressed_snapshot(self, spec: KeySpec, *, latched: bool) -> bool:
        if spec.holds_when_latched and latched:
            return True
        key_name = self._backend.key_name_for_spec(spec)
        return self._backend.is_key_down(key_name) if key_name is not None else False

    def _ensure_backend_listener(self) -> None:
        if self._backend_listener_unsubscribe is None:
            self._backend_listener_unsubscribe = self._backend.add_key_state_listener(self._handle_backend_key_state_change)
