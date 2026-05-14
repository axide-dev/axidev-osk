"""Helpers for transient prompt event resolution."""

from __future__ import annotations

from PySide6.QtCore import QEventLoop

from .dispatcher import Dispatcher, Unsubscribe
from .events import PromptResolved


class PromptResolutionWaiter:
    """Waits for a specific prompt resolution event on a nested Qt loop."""

    def __init__(self, dispatcher: Dispatcher, prompt_id: str, event_loop: QEventLoop, *, default: str) -> None:
        """Create a waiter for one prompt ID."""

        self._dispatcher = dispatcher
        self._prompt_id = prompt_id
        self._event_loop = event_loop
        self._result = default
        self._unsubscribe: Unsubscribe | None = None

    @property
    def result(self) -> str:
        """Return the selected prompt role or the configured default."""

        return self._result

    def start(self) -> None:
        """Subscribe to prompt resolution events."""

        self._unsubscribe = self._dispatcher.add_event_handler(self._handle_prompt)

    def stop(self) -> None:
        """Unsubscribe from prompt resolution events."""

        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def _handle_prompt(self, event: object) -> None:
        if not isinstance(event, PromptResolved):
            return
        if event.prompt_id != self._prompt_id:
            return
        self._result = event.result
        if self._event_loop.isRunning():
            self._event_loop.quit()
