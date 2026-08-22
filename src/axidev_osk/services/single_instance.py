"""Windows single-instance coordination through a local Qt server."""

from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from ..runtime.commands import WindowShow
from ..runtime.context import Context


class ExistingInstanceActivated(RuntimeError):
    """Signal that a running Windows instance accepted this launch request."""


def _server_name() -> str:
    profile = os.environ.get("USERPROFILE", str(Path.home())).casefold()
    user_id = hashlib.sha256(profile.encode("utf-8")).hexdigest()[:16]
    return f"axidev-osk-{user_id}"


def _lock_path() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Axidev OSK Development" / "single-instance.lock"


class WindowsSingleInstanceService(QObject):
    """Keep one Windows process and route later launches through the command queue."""

    def __init__(self, *, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._context: Context | None = None
        self._lock: QLockFile | None = None
        self._server: QLocalServer | None = None
        self._name: str | None = None

    def start(self, context: Context) -> None:
        if sys.platform != "win32":
            return

        name = _server_name()
        lock_path = _lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(lock_path))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            self._notify_running_instance(name)
            raise ExistingInstanceActivated

        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(name)
        if not server.listen(name):
            lock.unlock()
            raise RuntimeError(f"Unable to create the Axidev OSK single-instance server: {server.errorString()}")
        self._context = context
        self._lock = lock
        self._server = server
        self._name = name
        server.newConnection.connect(self._activate_running_window)

    def stop(self) -> None:
        if self._server is not None:
            self._server.close()
        if self._name is not None:
            QLocalServer.removeServer(self._name)
        if self._lock is not None:
            self._lock.unlock()
        self._context = None
        self._lock = None
        self._server = None
        self._name = None

    @staticmethod
    def _notify_running_instance(name: str) -> None:
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            client = QLocalSocket()
            client.connectToServer(name)
            if client.waitForConnected(100):
                client.disconnectFromServer()
                return
            client.abort()
            time.sleep(0.05)
        raise RuntimeError("The running Axidev OSK instance did not accept the activation request.")

    def _activate_running_window(self) -> None:
        server = self._server
        context = self._context
        if server is None or context is None:
            return

        received_request = False
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()
            connection.disconnectFromServer()
            connection.deleteLater()
            received_request = True
        if received_request:
            context.dispatcher.dispatch_command(WindowShow(context.config.keyboard_window_id))
