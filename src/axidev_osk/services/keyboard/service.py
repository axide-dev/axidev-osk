"""Keyboard input/output service used by registered runtime actions."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...runtime.behavior_models import KeyboardOutput
from ...runtime.engine_messages import (
    input_key,
    keyboard_permission_required,
    keyboard_reset,
    keyboard_status_changed,
)
from ...runtime.events import keyboard_key_state_changed, keyboard_lock_state_changed
from ...runtime.source import SourcePath
from .io import AxidevIoKeyboardBackend, KeyObservation

if TYPE_CHECKING:
    from ...runtime.context import Context

Unsubscribe = Callable[[], None]

_logger = logging.getLogger(__name__)


class KeyboardService:
    """Own backend lifecycle, output registration, and active press handles."""

    def __init__(self, backend: AxidevIoKeyboardBackend | None = None) -> None:
        self._backend = backend or AxidevIoKeyboardBackend()
        self._shutdown = False
        self._context: Context | None = None
        self._press_handles: dict[SourcePath, object | None] = {}
        self._outputs_by_source: dict[SourcePath, KeyboardOutput] = {}
        self._sources_by_key_name: dict[str, list[SourcePath]] = {}
        self._backend_listener_unsubscribe: Unsubscribe | None = None
        self._modifier_listener_unsubscribe: Unsubscribe | None = None
        self._locked_by_key_name: dict[str, bool] = {}
        self._held: dict[str, object | None] = {}
        self._observation_unsubscribe: Unsubscribe | None = None

    def bind_context(self, context: "Context") -> None:
        self._context = context
        self._ensure_backend_listener()

    def start(self, context: "Context") -> None:
        self.bind_context(context)
        self.initialize()
        self.publish_status()

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
        self._ensure_backend_listener()
        return initialized

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

    def register_output(
        self,
        source: SourcePath,
        output: KeyboardOutput,
    ) -> tuple[str, frozenset[str]]:
        """Register backend output metadata and return canonical key metadata."""

        key_name = self._backend.key_name_for_output(output)
        state_tags = self._backend.state_tags_for_key(key_name)
        self._outputs_by_source[source] = output
        sources = self._sources_by_key_name.setdefault(key_name, [])
        if source not in sources:
            sources.append(source)
        if self._backend.is_key_down(key_name):
            self._emit_key_state(source, True, state_tags)
        locked = self._locked_by_key_name.get(key_name)
        if locked is not None:
            self._emit_lock_state(source, locked)
        return key_name, state_tags

    def key_down(
        self,
        source: SourcePath,
        active_state_tags: frozenset[str],
    ) -> None:
        """Emit registered output for one exact component source."""

        output = self._registered_output(source)
        press_handle = self._backend.key_down(output, active_state_tags)
        if press_handle is None:
            return
        self._press_handles[source] = press_handle

    def key_up(self, source: SourcePath) -> None:
        """Release the backend press associated with one exact source."""

        self._registered_output(source)
        press_handle = self._press_handles.pop(source, None)
        self._backend.key_up(press_handle)

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
        """Release active output and discard service-owned registration state."""

        self._release_press_handles()
        self._outputs_by_source.clear()
        self._sources_by_key_name.clear()
        if self._context is not None:
            self._context.dispatcher.dispatch_event(keyboard_reset())

    def _registered_output(self, source: SourcePath) -> KeyboardOutput:
        output = self._outputs_by_source.get(source)
        if output is None:
            raise ValueError(f"No keyboard output registered for source {source!r}")
        return output

    def _release_press_handles(self) -> None:
        for press_handle in (*self._press_handles.values(), *self._held.values()):
            self._backend.key_up(press_handle)
        self._press_handles.clear()
        self._held.clear()

    def _handle_backend_key_state_change(self, key_name: str, pressed: bool) -> None:
        state_tags = self._backend.state_tags_for_key(key_name)
        for source in self._sources_by_key_name.get(key_name, []):
            self._emit_key_state(source, pressed, state_tags)

    def _handle_backend_modifier_state_change(self, modifiers: frozenset[str]) -> None:
        for key_name, sources in tuple(self._sources_by_key_name.items()):
            lock_name = self._backend.lock_name_for_key(key_name)
            if lock_name is None:
                continue
            locked = lock_name in modifiers
            if self._locked_by_key_name.get(key_name) == locked:
                continue
            self._locked_by_key_name[key_name] = locked
            for source in tuple(sources):
                self._emit_lock_state(source, locked)

    def _emit_lock_state(self, source: SourcePath, locked: bool) -> None:
        if self._context is not None:
            self._context.dispatcher.dispatch_event(keyboard_lock_state_changed(source, locked))

    def _emit_key_state(
        self,
        source: SourcePath,
        pressed: bool,
        state_tags: frozenset[str],
    ) -> None:
        if self._context is not None:
            self._context.dispatcher.dispatch_event(
                keyboard_key_state_changed(source, pressed, state_tags)
            )

    def _ensure_backend_listener(self) -> None:
        if self._backend_listener_unsubscribe is None:
            self._backend_listener_unsubscribe = self._backend.add_key_state_listener(
                self._handle_backend_key_state_change
            )
        if self._modifier_listener_unsubscribe is None:
            self._modifier_listener_unsubscribe = self._backend.add_modifier_state_listener(
                self._handle_backend_modifier_state_change
            )
        if self._observation_unsubscribe is None:
            self._observation_unsubscribe = self._backend.add_observation_listener(
                self._handle_observation
            )

    def _handle_observation(self, observation: KeyObservation) -> None:
        # Called on the listener thread; the dispatcher hands it to its owner thread.
        if self._context is not None:
            self._context.dispatcher.dispatch_event(
                input_key(observation.key, observation.text, observation.modifiers, observation.pressed)
            )
