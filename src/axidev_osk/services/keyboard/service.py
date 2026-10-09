"""Keyboard service: backend lifecycle, explicit key effects, and observations."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...runtime.engine_messages import (
    input_key,
    keyboard_permission_required,
    keyboard_reset,
    keyboard_status_changed,
)
from .io import AxidevIoKeyboardBackend, KeyObservation

if TYPE_CHECKING:
    from ...runtime.context import Context

Unsubscribe = Callable[[], None]

_logger = logging.getLogger(__name__)


class KeyboardService:
    """Own the keyboard backend, the keys it holds down, and its observations.

    The service never decides what a key means. Profiles send
    ``keyboard.down``, ``keyboard.up``, ``keyboard.tap``, and
    ``keyboard.type_text``; the service reports ``input.key`` observations and
    its status back through the queue.
    """

    def __init__(self, backend: AxidevIoKeyboardBackend | None = None) -> None:
        self._backend = backend or AxidevIoKeyboardBackend()
        self._shutdown = False
        self._context: Context | None = None
        self._held: dict[str, object | None] = {}
        self._observation_unsubscribe: Unsubscribe | None = None

    def bind_context(self, context: "Context") -> None:
        self._context = context
        if self._observation_unsubscribe is None:
            self._observation_unsubscribe = self._backend.add_observation_listener(self._handle_observation)

    def start(self, context: "Context") -> None:
        """Bind the runtime and initialize output; the runtime publishes status when ready."""

        self.bind_context(context)
        self.initialize()

    def stop(self) -> None:
        self.shutdown()

    @property
    def ready(self) -> bool:
        return self._backend.ready

    @property
    def status_text(self) -> str:
        return self._backend.status_text

    @property
    def needs_permission_setup(self) -> bool:
        return self._backend.needs_permission_setup

    @property
    def permission_setup_text(self) -> str:
        return self._backend.permission_setup_text

    def initialize(self) -> bool:
        initialized = self._backend.initialize()
        self._shutdown = False
        return initialized

    def publish_status(self) -> None:
        """Report backend readiness as an observation, plus a setup request if needed."""

        if self._context is None:
            return
        dispatcher = self._context.dispatcher
        dispatcher.dispatch_event(
            keyboard_status_changed(
                self.ready,
                self.status_text,
                self.needs_permission_setup,
                self.permission_setup_text if self.needs_permission_setup else "",
            )
        )
        if self.needs_permission_setup:
            dispatcher.dispatch_event(keyboard_permission_required())

    def shutdown(self) -> None:
        if self._shutdown:
            _logger.info("Keyboard backend shutdown already completed")
            return
        self._shutdown = True
        started_at = time.perf_counter()
        _logger.info("Shutting down keyboard backend")
        self.reset_state()
        self._backend.shutdown()
        _logger.info("Keyboard backend shutdown completed in %.3fs", time.perf_counter() - started_at)

    def press(self, key: str, mods: tuple[str, ...], repeat: bool) -> None:
        """Hold a key down until ``release`` names the same key."""

        canonical = self._backend.canonical_key(key)
        handle = self._backend.press(canonical, mods, repeat)
        if handle is not None:
            previous = self._held.pop(canonical, None)
            if previous is not None:
                self._backend.key_up(previous)
            self._held[canonical] = handle

    def release(self, key: str) -> None:
        """Release a key held by ``press``; releasing an unheld key does nothing."""

        handle = self._held.pop(self._backend.canonical_key(key), None)
        if handle is not None:
            self._backend.key_up(handle)

    def tap(self, key: str, mods: tuple[str, ...]) -> None:
        self._backend.tap(key, mods)

    def type_text(self, text: str) -> None:
        self._backend.type_text(text)

    def reset_state(self) -> None:
        """Release every held key and report ``keyboard.reset``."""

        for handle in tuple(self._held.values()):
            self._backend.key_up(handle)
        self._held.clear()
        if self._context is not None:
            self._context.dispatcher.dispatch_event(keyboard_reset())

    def _handle_observation(self, observation: KeyObservation) -> None:
        # Called on the listener thread; the dispatcher hands it to its owner thread.
        if self._context is not None:
            self._context.dispatcher.dispatch_event(
                input_key(observation.key, observation.text, observation.modifiers, observation.pressed)
            )
