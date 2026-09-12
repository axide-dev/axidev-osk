"""Private control channel for the supervised Plasma lock-screen worker."""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QSocketNotifier
from PySide6.QtWidgets import QApplication

from ..runtime.commands import SecureInputPanelPrepare, SecureInputPanelRelease

if TYPE_CHECKING:
    from ..runtime.context import Context

_logger = logging.getLogger(__name__)


class SecureInputPanelWorkerService(QObject):
    """Translate supervisor commands into runtime queue commands."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._context: Context | None = None
        self._notifier: QSocketNotifier | None = None
        self._buffer = bytearray()

    def start(self, context: Context) -> None:
        """Start reading line-delimited commands from the Rust supervisor."""

        self._context = context
        self._notifier = QSocketNotifier(sys.stdin.fileno(), QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._read_commands)
        self._respond("READY")

    def stop(self) -> None:
        """Stop reading supervisor commands."""

        self._context = None
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
                context.dispatcher.dispatch_command(SecureInputPanelPrepare())
                self._respond("PREPARED")
            elif command == "RELEASE":
                context.dispatcher.dispatch_command(SecureInputPanelRelease())
                self._respond("RELEASED")
            elif command == "PING":
                self._respond("PONG")
            else:
                _logger.error("Unknown lock-screen supervisor command: %r", command)
                self._respond("ERROR")
        except Exception:
            _logger.exception("Lock-screen worker command failed: %s", command)
            self._respond("ERROR")

    def _respond(self, response: str) -> None:
        os.write(sys.stdout.fileno(), f"AXIDEV_OSK {response}\n".encode("ascii"))

    @staticmethod
    def _exit(status: int) -> None:
        app = QApplication.instance()
        if app is not None:
            app.exit(status)
