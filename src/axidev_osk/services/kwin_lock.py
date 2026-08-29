"""KWin screen-lock state integration for the secure input panel."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, SLOT, QTimer, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

from ..runtime.events import ScreenLockStateChanged

if TYPE_CHECKING:
    from ..runtime.context import Context

_logger = logging.getLogger(__name__)


class KWinLockService(QObject):
    """Observe KDE's lock state and expose KWin input-method activation."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._context: Context | None = None
        self._connection = QDBusConnection.sessionBus()
        self._system_connection = QDBusConnection.systemBus()
        self._virtual_keyboard: QDBusInterface | None = None
        self._screen_saver: QDBusInterface | None = None
        self._locked = False

    def start(self, context: Context) -> None:
        """Connect lock-state signals and publish the current state."""

        self._context = context
        if not self._connection.isConnected():
            raise RuntimeError("KDE session bus is unavailable")
        self._virtual_keyboard = QDBusInterface(
            "org.kde.KWin",
            "/VirtualKeyboard",
            "org.kde.kwin.VirtualKeyboard",
            self._connection,
        )
        connected_about = self._connection.connect(
            "org.kde.screensaver",
            "/ScreenSaver",
            "org.kde.screensaver",
            "AboutToLock",
            self,
            SLOT("aboutToLock()"),
        )
        connected_active = self._connection.connect(
            "org.freedesktop.ScreenSaver",
            "/ScreenSaver",
            "org.freedesktop.ScreenSaver",
            "ActiveChanged",
            self,
            SLOT("activeChanged(bool)"),
        )
        if not connected_about or not connected_active:
            raise RuntimeError("Cannot monitor KDE screen-lock state")
        if not self._system_connection.isConnected() or not self._system_connection.connect(
            "org.freedesktop.login1",
            "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager",
            "PrepareForSleep",
            self,
            SLOT("prepareForSleep(bool)"),
        ):
            _logger.warning("System sleep state is unavailable; lock panel resume may be delayed")

        self._screen_saver = QDBusInterface(
            "org.freedesktop.ScreenSaver",
            "/ScreenSaver",
            "org.freedesktop.ScreenSaver",
            self._connection,
        )
        reply = self._screen_saver.call("GetActive")
        if reply.type() == QDBusMessage.MessageType.ReplyMessage and reply.arguments():
            self._emit_state(bool(reply.arguments()[0]))
        else:
            _logger.warning("KDE screen-lock state is unavailable; keeping the secure panel hidden")
            self._emit_state(False)

    def stop(self) -> None:
        """Disconnect lock-state signals."""

        self._connection.disconnect(
            "org.kde.screensaver",
            "/ScreenSaver",
            "org.kde.screensaver",
            "AboutToLock",
            self,
            SLOT("aboutToLock()"),
        )
        self._connection.disconnect(
            "org.freedesktop.ScreenSaver",
            "/ScreenSaver",
            "org.freedesktop.ScreenSaver",
            "ActiveChanged",
            self,
            SLOT("activeChanged(bool)"),
        )
        self._system_connection.disconnect(
            "org.freedesktop.login1",
            "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager",
            "PrepareForSleep",
            self,
            SLOT("prepareForSleep(bool)"),
        )
        self._context = None
        self._virtual_keyboard = None
        self._screen_saver = None
        self._locked = False

    def activate(self) -> None:
        """Ask KWin to activate its configured virtual keyboard."""

        self._force_activate()
        QTimer.singleShot(250, self._force_activate)
        QTimer.singleShot(1000, self._force_activate)

    @Slot()
    def aboutToLock(self) -> None:
        self._emit_state(True)

    @Slot(bool)
    def activeChanged(self, active: bool) -> None:
        self._emit_state(active)

    @Slot(bool)
    def prepareForSleep(self, sleeping: bool) -> None:
        """Republish lock state after resume so KWin reactivates a hidden panel."""

        if sleeping or self._screen_saver is None:
            return
        reply = self._screen_saver.call("GetActive")
        if reply.type() == QDBusMessage.MessageType.ReplyMessage and reply.arguments():
            self._emit_state(bool(reply.arguments()[0]))
        else:
            _logger.warning("KDE screen-lock state is unavailable after resume")

    def _emit_state(self, locked: bool) -> None:
        self._locked = locked
        if self._context is not None:
            self._context.dispatcher.dispatch_event(ScreenLockStateChanged(locked=locked))

    def _force_activate(self) -> None:
        if self._locked and self._virtual_keyboard is not None:
            self._virtual_keyboard.call("forceActivate")
