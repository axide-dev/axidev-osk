"""Keyboard service boundary used by runtime commands and components."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Mapping

from ..keyboard_io import AxidevIoKeyboardBackend, PermissionSetupOutcome
from ..models import KeySpec

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

        return self._backend.initialize()

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

    def is_key_down(self, key_name: str) -> bool:
        """Return whether a canonical key is currently down."""

        return self._backend.is_key_down(key_name)

    def key_name_for_spec(self, spec: KeySpec) -> str | None:
        """Resolve the backend key name for a key spec."""

        return self._backend.key_name_for_spec(spec)

    def key_down(self, spec: KeySpec, latched_keys: Mapping[str, bool]) -> object | None:
        """Emit a key-down action through the backend."""

        return self._backend.key_down(spec, latched_keys)

    def key_up(self, active_press: object | None) -> None:
        """Emit a key-up action through the backend."""

        self._backend.key_up(active_press)

    def sync_latched_key(self, spec: KeySpec, latched: bool, active_press: object | None = None) -> object | None:
        """Synchronize a latched modifier with backend held-key state."""

        return self._backend.sync_latched_key(spec, latched, active_press)
