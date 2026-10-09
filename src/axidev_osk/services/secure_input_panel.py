"""Private control channel for the supervised Plasma lock-screen worker."""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QSocketNotifier
from PySide6.QtWidgets import QApplication

from collections.abc import Callable

from ..messages import MessageResult
from ..runtime.actions import (
    SECURE_INPUT_PANEL_PREPARE,
    SECURE_INPUT_PANEL_RELEASE,
    secure_input_panel_prepare,
    secure_input_panel_release,
)
from ..runtime.events import (
    ACTION_FAILED,
    SECURE_INPUT_PANEL_PREPARED,
    SECURE_INPUT_PANEL_RELEASED,
    ActionFailedArguments,
    NoEventArguments,
)

if TYPE_CHECKING:
    from ..runtime.context import Context

_logger = logging.getLogger(__name__)


class SecureInputPanelWorkerService(QObject):
    """Translate supervisor commands into runtime actions and answer from runtime events."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._context: Context | None = None
        self._notifier: QSocketNotifier | None = None
        self._buffer = bytearray()
        self._pending_action: str | None = None
        self._unsubscribes: list[Callable[[], None]] = []

    def start(self, context: Context) -> None:
        """Start reading line-delimited commands from the Rust supervisor."""

        self._context = context
        dispatcher = context.dispatcher
        self._unsubscribes = [
            dispatcher.add_event_handler(SECURE_INPUT_PANEL_PREPARED, self._handle_prepared),
            dispatcher.add_event_handler(SECURE_INPUT_PANEL_RELEASED, self._handle_released),
            dispatcher.add_event_handler(ACTION_FAILED, self._handle_action_failed),
        ]
        self._notifier = QSocketNotifier(sys.stdin.fileno(), QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._read_commands)
        self._respond("READY")

    def stop(self) -> None:
        """Stop reading supervisor commands."""

        self._context = None
        self._pending_action = None
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes.clear()
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier.deleteLater()
            self._notifier = None

    def _read_commands(self) -> None:
        try:
            chunk = os.read(sys.stdin.fileno(), 4096)
        except OSError:
            _logger.exception("Cannot read from the lock-screen supervisor")
            self._exit(1)
            return
        if not chunk:
            if self._notifier is not None:
                self._notifier.setEnabled(False)
            self._exit(0)
            return
        self._buffer.extend(chunk)
        while b"\n" in self._buffer:
            raw, _, remainder = self._buffer.partition(b"\n")
            self._buffer = bytearray(remainder)
            self._handle_command(raw.decode("ascii", "replace"))

    def _handle_command(self, command: str) -> None:
        context = self._context
        if context is None:
            self._respond("ERROR")
            return
        try:
            if command == "PREPARE":
                self._pending_action = SECURE_INPUT_PANEL_PREPARE
                context.dispatcher.dispatch_action(secure_input_panel_prepare())
            elif command == "RELEASE":
                self._pending_action = SECURE_INPUT_PANEL_RELEASE
                context.dispatcher.dispatch_action(secure_input_panel_release())
            elif command == "PING":
                self._respond("PONG")
            else:
                _logger.error("Unknown lock-screen supervisor command: %r", command)
                self._respond("ERROR")
        except Exception:
            _logger.exception("Lock-screen worker command failed: %s", command)
            self._pending_action = None
            self._respond("ERROR")

    def _handle_prepared(self, event: NoEventArguments) -> MessageResult:
        del event
        self._answer_pending(SECURE_INPUT_PANEL_PREPARE, "PREPARED")
        return []

    def _handle_released(self, event: NoEventArguments) -> MessageResult:
        del event
        self._answer_pending(SECURE_INPUT_PANEL_RELEASE, "RELEASED")
        return []

    def _handle_action_failed(self, event: ActionFailedArguments) -> MessageResult:
        self._answer_pending(event.action, "ERROR")
        return []

    def _answer_pending(self, action: str, response: str) -> None:
        if self._pending_action != action:
            return
        self._pending_action = None
        self._respond(response)

    def _respond(self, response: str) -> None:
        os.write(sys.stdout.fileno(), f"AXIDEV_OSK {response}\n".encode("ascii"))

    @staticmethod
    def _exit(status: int) -> None:
        app = QApplication.instance()
        if app is not None:
            app.exit(status)
