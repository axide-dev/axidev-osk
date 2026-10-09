"""Application-wide graceful quit coordination.

Owns OS signal handlers, stdin EOF detection, and an ordered list of
shutdown callbacks. Components register windows and callbacks; the
controller serializes one shutdown sequence regardless of how the quit
was triggered (signal, EOF, window close, programmatic).
"""

from __future__ import annotations

import os
import logging
import signal
import sys
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QSocketNotifier, QTimer
from PySide6.QtWidgets import QApplication, QWidget


QuitCallback = Callable[[], None]
AskToQuit = Callable[[], None]

_logger = logging.getLogger(__name__)


class ApplicationQuitController(QObject):
    """Coordinates app-wide quit requests before process shutdown.

    The controller owns no confirmation UI. When a quit needs confirmation it
    calls ``ask_to_quit`` and returns; the profile decides what to show and
    finishes the quit by sending ``app.quit``, which calls ``shutdown``.

    Side effects:
        Installs OS signal handlers, owns a heartbeat ``QTimer`` so
        Python signal handlers run promptly under Qt's event loop, and
        optionally registers a stdin EOF notifier when stdin is a TTY.
    """

    def __init__(
        self,
        app: QApplication,
        *,
        ask_to_quit: AskToQuit | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Construct an unstarted quit controller.

        Args:
            app: Application instance whose ``exit`` is called at end of
                shutdown.
            ask_to_quit: Called instead of shutting down when a quit needs
                confirmation. ``None`` means every quit proceeds immediately.
            parent: Standard ``QObject`` parent.

        Returns:
            None.

        Side effects:
            Constructs the heartbeat timer; does not start it.
        """

        super().__init__(parent)
        self._app = app
        self._ask_to_quit = ask_to_quit
        self._callbacks: list[QuitCallback] = []
        self._windows: list[QWidget] = []
        self._quitting = False
        self._signal_timer = QTimer(self)
        self._signal_timer.setInterval(250)
        self._signal_timer.timeout.connect(lambda: None)
        self._stdin_notifier: QSocketNotifier | None = None

    def register_window(self, window: QWidget) -> None:
        """Register a top-level window that participates in shutdown.

        The runtime is responsible for routing ``WindowCloseRequested``
        events on the dispatcher to ``request_quit``; this method only
        records the window so it can be closed at the end of the
        shutdown sequence and informs it that the controller now owns
        close behavior.

        Args:
            window: Window participating in graceful shutdown. If the
                window defines ``set_quit_controller_managed`` it is
                informed so it can suppress its own confirmation UI.

        Returns:
            None.

        Side effects:
            Appends the window to the controller's tracked list and
            flags it as managed.
        """

        self._windows.append(window)
        if hasattr(window, "set_quit_controller_managed"):
            window.set_quit_controller_managed(True)  # type: ignore[attr-defined]

    def register_quit_callback(self, callback: QuitCallback) -> None:
        """Register a callback fired in registration order during shutdown.

        Args:
            callback: Zero-arg callable invoked synchronously after the
                user confirms the quit prompt and before windows close.

        Returns:
            None.

        Side effects:
            None until shutdown begins.
        """

        self._callbacks.append(callback)

    def install_signal_handlers(self) -> None:
        """Install OS signal handlers and stdin EOF detection.

        Returns:
            None.

        Side effects:
            Replaces handlers for ``SIGINT``, ``SIGTERM``, and ``SIGHUP``
            (when available); starts the heartbeat timer; installs a
            ``QSocketNotifier`` on stdin when stdin is a TTY.
        """

        for signal_name in ("SIGINT", "SIGTERM", "SIGHUP"):
            signal_value = getattr(signal, signal_name, None)
            if signal_value is None:
                continue
            signal.signal(signal_value, self._handle_signal)
        self._signal_timer.start()
        self._install_stdin_eof_handler()

    def request_quit(self, *, confirm: bool = True) -> None:
        """Ask to quit, or shut down right away when no confirmation is needed.

        Args:
            confirm: Whether the user should confirm before shutdown.

        Side effects:
            Calls ``ask_to_quit`` when confirming, otherwise runs ``shutdown``.
        """

        if self._quitting:
            _logger.info("Graceful shutdown already in progress")
            return
        if confirm and self._ask_to_quit is not None:
            self._ask_to_quit()
            return
        self.shutdown()

    def shutdown(self, exit_code: int = 0) -> None:
        """Run the graceful shutdown sequence once.

        Side effects:
            Invokes registered quit callbacks in order, hides and closes all
            registered windows, and calls ``QApplication.exit(exit_code)``.
            Later calls while shutdown is in progress are ignored.
        """

        if self._quitting:
            _logger.info("Graceful shutdown already in progress")
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
        self._app.exit(exit_code)

    def _handle_signal(self, signum: int, _frame: object) -> None:
        confirm = signum != signal.SIGTERM
        QTimer.singleShot(0, lambda: self.request_quit(confirm=confirm))

    def _callback_name(self, callback: QuitCallback) -> str:
        self_obj = getattr(callback, "__self__", None)
        func = getattr(callback, "__func__", callback)
        name = getattr(func, "__qualname__", repr(callback))
        if self_obj is None:
            return name
        return f"{type(self_obj).__name__}.{getattr(func, '__name__', name)}"

    def _install_stdin_eof_handler(self) -> None:
        stdin = sys.stdin
        if stdin is None or not stdin.isatty():
            return
        self._stdin_notifier = QSocketNotifier(stdin.fileno(), QSocketNotifier.Type.Read, self)
        self._stdin_notifier.activated.connect(self._handle_stdin_ready)

    def _handle_stdin_ready(self) -> None:
        try:
            data = os.read(sys.stdin.fileno(), 1)
        except OSError:
            return
        if data == b"":
            self.request_quit()
