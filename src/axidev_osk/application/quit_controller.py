from __future__ import annotations

import os
import logging
import signal
import sys
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QSocketNotifier, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget


QuitCallback = Callable[[], None]
QuitPrompt = Callable[[QWidget | None], bool]

_logger = logging.getLogger(__name__)


class ApplicationQuitController(QObject):
    """Coordinates app-wide quit requests before process shutdown."""

    def __init__(
        self,
        app: QApplication,
        *,
        prompt: QuitPrompt | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._app = app
        self._prompt = prompt or self._show_quit_prompt
        self._callbacks: list[QuitCallback] = []
        self._windows: list[QWidget] = []
        self._quitting = False
        self._signal_timer = QTimer(self)
        self._signal_timer.setInterval(250)
        self._signal_timer.timeout.connect(lambda: None)
        self._stdin_notifier: QSocketNotifier | None = None

    def register_window(self, window: QWidget) -> None:
        self._windows.append(window)
        if hasattr(window, "set_quit_controller_managed"):
            window.set_quit_controller_managed(True)  # type: ignore[attr-defined]
        window.close_requested.connect(self.request_quit)  # type: ignore[attr-defined]

    def register_quit_callback(self, callback: QuitCallback) -> None:
        self._callbacks.append(callback)

    def install_signal_handlers(self) -> None:
        for signal_name in ("SIGINT", "SIGTERM", "SIGHUP"):
            signal_value = getattr(signal, signal_name, None)
            if signal_value is None:
                continue
            signal.signal(signal_value, self._handle_signal)
        self._signal_timer.start()
        self._install_stdin_eof_handler()

    def request_quit(self) -> None:
        if self._quitting:
            _logger.info("Graceful shutdown already in progress")
            return

        active_window = self._app.activeWindow()
        if not self._prompt(active_window):
            _logger.info("Graceful shutdown cancelled")
            return

        shutdown_started_at = time.perf_counter()
        _logger.info("Graceful shutdown requested")
        self._quitting = True
        self._signal_timer.stop()
        if self._stdin_notifier is not None:
            self._stdin_notifier.setEnabled(False)
        for callback in list(self._callbacks):
            callback_name = self._callback_name(callback)
            callback_started_at = time.perf_counter()
            _logger.info("Shutting down %s", callback_name)
            callback()
            _logger.info(
                "Finished shutting down %s in %.3fs",
                callback_name,
                time.perf_counter() - callback_started_at,
            )
        for window in list(self._windows):
            if hasattr(window, "set_quit_controller_managed"):
                window.set_quit_controller_managed(False)  # type: ignore[attr-defined]
            window.hide()
            window.close()
        _logger.info("Graceful shutdown completed in %.3fs", time.perf_counter() - shutdown_started_at)
        self._app.exit(0)

    def _handle_signal(self, _signum: int, _frame: object) -> None:
        QTimer.singleShot(0, self.request_quit)

    def _callback_name(self, callback: QuitCallback) -> str:
        self_obj = getattr(callback, "__self__", None)
        func = getattr(callback, "__func__", callback)
        name = getattr(func, "__qualname__", repr(callback))
        if self_obj is None:
            return name
        return f"{type(self_obj).__name__}.{getattr(func, '__name__', name)}"

    def _install_stdin_eof_handler(self) -> None:
        if not sys.stdin.isatty():
            return
        self._stdin_notifier = QSocketNotifier(sys.stdin.fileno(), QSocketNotifier.Type.Read, self)
        self._stdin_notifier.activated.connect(self._handle_stdin_ready)

    def _handle_stdin_ready(self) -> None:
        try:
            data = os.read(sys.stdin.fileno(), 1)
        except OSError:
            return
        if data == b"":
            self.request_quit()

    def _show_quit_prompt(self, parent: QWidget | None) -> bool:
        answer = QMessageBox.question(
            parent,
            "Close axidev-osk?",
            "Do you want to close axidev-osk?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes
