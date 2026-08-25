from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from PySide6.QtDBus import QDBusMessage

from axidev_osk.services.kwin_lock import KWinLockService


class KWinLockServiceTests(unittest.TestCase):
    def test_lock_signals_are_bound_to_screen_locker_services(self) -> None:
        connection = Mock()
        connection.isConnected.return_value = True
        connection.connect.return_value = True
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


if __name__ == "__main__":
    unittest.main()
