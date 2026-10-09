"""Spawn external programs for profiles and report their exit through the queue."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QProcess

from ..runtime.engine_messages import process_exited

if TYPE_CHECKING:
    from ..runtime.context import Context

_logger = logging.getLogger(__name__)


class ProcessService(QObject):
    """Run programs from an argument list, never through a shell.

    Attached programs report ``process.exited`` when they end, and Qt stops
    them if the app quits first. Detached programs outlive the app and never
    report an exit; a detached start failure still reports one.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._context: Context | None = None
        self._running: set[QProcess] = set()

    def start(self, context: "Context") -> None:
        self._context = context

    def stop(self) -> None:
        self._context = None

    def spawn(self, argv: tuple[str, ...], tag: str, detached: bool) -> None:
        program, *arguments = argv
        if detached:
            started, _pid = QProcess.startDetached(program, arguments)
            if not started:
                self._report(tag, -1, f"Could not start {program!r}")
            return
        process = QProcess(self)
        process.finished.connect(
            lambda code, _status, process=process, tag=tag: self._finished(process, tag, code)
        )
        process.errorOccurred.connect(
            lambda error, process=process, tag=tag: self._failed(process, tag, error)
        )
        self._running.add(process)
        process.start(program, arguments)

    def _finished(self, process: QProcess, tag: str, code: int) -> None:
        self._release(process)
        self._report(tag, code, None)

    def _failed(self, process: QProcess, tag: str, error: QProcess.ProcessError) -> None:
        if error != QProcess.ProcessError.FailedToStart:
            return
        message = process.errorString()
        self._release(process)
        self._report(tag, -1, message)

    def _release(self, process: QProcess) -> None:
        self._running.discard(process)
        process.deleteLater()

    def _report(self, tag: str, code: int, error: str | None) -> None:
        if error is not None:
            _logger.warning("Process %s failed: %s", tag, error)
        if self._context is not None:
            self._context.dispatcher.dispatch(process_exited(tag, code, error))
