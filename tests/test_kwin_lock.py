from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from PySide6.QtDBus import QDBusMessage

from axidev_osk.runtime.events import ScreenLockStateChanged
from axidev_osk.services.kwin_lock import KWinLockService


class KWinLockServiceTests(unittest.TestCase):
    def test_lock_signals_are_bound_to_screen_locker_services(self) -> None:
        connection = Mock()
        connection.isConnected.return_value = True
        connection.connect.return_value = True
        system_connection = Mock()
        system_connection.isConnected.return_value = True
        system_connection.connect.return_value = True
        reply = Mock()
        reply.type.return_value = QDBusMessage.MessageType.ReplyMessage
        reply.arguments.return_value = [False]
        screen_saver = Mock()
        screen_saver.call.return_value = reply

        with (
            patch(
                "axidev_osk.services.kwin_lock.QDBusConnection.sessionBus",
                return_value=connection,
            ),
            patch(
                "axidev_osk.services.kwin_lock.QDBusConnection.systemBus",
                return_value=system_connection,
            ),
            patch(
                "axidev_osk.services.kwin_lock.QDBusInterface",
                side_effect=(Mock(), screen_saver),
            ),
        ):
            service = KWinLockService()
            service.start(Mock())
            service.stop()

        self.assertEqual(
            [call.args[0] for call in connection.connect.call_args_list],
            ["org.kde.screensaver", "org.freedesktop.ScreenSaver"],
        )
        self.assertEqual(
            [call.args[0] for call in connection.disconnect.call_args_list],
            ["org.kde.screensaver", "org.freedesktop.ScreenSaver"],
        )
        system_connection.connect.assert_called_once()
        system_connection.disconnect.assert_called_once()

    def test_resume_republishes_current_lock_state(self) -> None:
        connection = Mock()
        connection.isConnected.return_value = True
        connection.connect.return_value = True
        system_connection = Mock()
        system_connection.isConnected.return_value = True
        system_connection.connect.return_value = True
        unlocked_reply = Mock()
        unlocked_reply.type.return_value = QDBusMessage.MessageType.ReplyMessage
        unlocked_reply.arguments.return_value = [False]
        locked_reply = Mock()
        locked_reply.type.return_value = QDBusMessage.MessageType.ReplyMessage
        locked_reply.arguments.return_value = [True]
        screen_saver = Mock()
        screen_saver.call.side_effect = (unlocked_reply, locked_reply)
        context = Mock()

        with (
            patch(
                "axidev_osk.services.kwin_lock.QDBusConnection.sessionBus",
                return_value=connection,
            ),
            patch(
                "axidev_osk.services.kwin_lock.QDBusConnection.systemBus",
                return_value=system_connection,
            ),
            patch(
                "axidev_osk.services.kwin_lock.QDBusInterface",
                side_effect=(Mock(), screen_saver),
            ),
        ):
            service = KWinLockService()
            service.start(context)
            service.prepareForSleep(True)
            service.prepareForSleep(False)

        self.assertEqual(screen_saver.call.call_count, 2)
        event = context.dispatcher.dispatch_event.call_args_list[-1].args[0]
        self.assertEqual(event, ScreenLockStateChanged(locked=True))

    def test_activation_retries_only_while_locked(self) -> None:
        with (
            patch("axidev_osk.services.kwin_lock.QDBusConnection.sessionBus"),
            patch("axidev_osk.services.kwin_lock.QDBusConnection.systemBus"),
            patch("axidev_osk.services.kwin_lock.QTimer.singleShot") as single_shot,
        ):
            service = KWinLockService()
            service._virtual_keyboard = Mock()
            service._locked = True
            service.activate()

            self.assertEqual(service._virtual_keyboard.call.call_count, 1)
            callbacks = [call.args[1] for call in single_shot.call_args_list]
            callbacks[0]()
            service._locked = False
            callbacks[1]()

        self.assertEqual(service._virtual_keyboard.call.call_count, 2)


if __name__ == "__main__":
    unittest.main()
