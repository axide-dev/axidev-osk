"""Session D-Bus control surface for the Plasma lock-screen button."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Slot
from PySide6.QtDBus import QDBusConnection

from ..runtime.commands import SecureInputPanelPrepare, SecureInputPanelRelease

if TYPE_CHECKING:
    from ..runtime.context import Context

SERVICE_NAME = "org.axidev.OSK.LockScreen"
OBJECT_PATH = "/org/axidev/OSK/LockScreen"


class SecureInputPanelService(QObject):
    """Translate lock-screen D-Bus requests into runtime commands."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._connection = QDBusConnection.sessionBus()
        self._context: Context | None = None

    def start(self, context: Context) -> None:
        """Publish the lock-screen control object on the session bus."""

        if not self._connection.isConnected():
            raise RuntimeError("KDE session bus is unavailable")
        if not self._connection.registerService(SERVICE_NAME):
            raise RuntimeError(f"Cannot register D-Bus service {SERVICE_NAME}")
        if not self._connection.registerObject(
            OBJECT_PATH,
            self,
            QDBusConnection.RegisterOption.ExportAllSlots,
        ):
            self._connection.unregisterService(SERVICE_NAME)
            raise RuntimeError(f"Cannot register D-Bus object {OBJECT_PATH}")
        self._context = context

    def stop(self) -> None:
        """Remove the lock-screen control object from the session bus."""

        self._context = None
        self._connection.unregisterObject(OBJECT_PATH)
        self._connection.unregisterService(SERVICE_NAME)

    @Slot()
    def prepare(self) -> None:
        """Request secure input-panel creation through the runtime queue."""

        if self._context is not None:
            self._context.dispatcher.dispatch_command(SecureInputPanelPrepare())

    @Slot()
    def release(self) -> None:
        """Request secure input-panel cleanup through the runtime queue."""

        if self._context is not None:
            self._context.dispatcher.dispatch_command(SecureInputPanelRelease())
