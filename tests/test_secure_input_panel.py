from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from axidev_osk.runtime.commands import SecureInputPanelPrepare, SecureInputPanelRelease
from axidev_osk.services.secure_input_panel import OBJECT_PATH, SERVICE_NAME, SecureInputPanelService


class SecureInputPanelServiceTests(unittest.TestCase):
    def test_dbus_methods_dispatch_runtime_commands(self) -> None:
        connection = Mock()
        connection.isConnected.return_value = True
        connection.registerService.return_value = True
        connection.registerObject.return_value = True
        context = Mock()

        with patch(
            "axidev_osk.services.secure_input_panel.QDBusConnection.sessionBus",
            return_value=connection,
        ):
            service = SecureInputPanelService()
            service.start(context)
            service.prepare()
            service.release()
            service.stop()

        connection.registerService.assert_called_once_with(SERVICE_NAME)
        self.assertEqual(connection.registerObject.call_args.args[:2], (OBJECT_PATH, service))
        dispatched = [call.args[0] for call in context.dispatcher.dispatch_command.call_args_list]
        self.assertEqual(dispatched, [SecureInputPanelPrepare(), SecureInputPanelRelease()])
        connection.unregisterObject.assert_called_once_with(OBJECT_PATH)
        connection.unregisterService.assert_called_once_with(SERVICE_NAME)

    def test_failed_object_registration_releases_service_name(self) -> None:
        connection = Mock()
        connection.isConnected.return_value = True
        connection.registerService.return_value = True
        connection.registerObject.return_value = False

        with patch(
            "axidev_osk.services.secure_input_panel.QDBusConnection.sessionBus",
            return_value=connection,
        ):
            service = SecureInputPanelService()
            with self.assertRaisesRegex(RuntimeError, OBJECT_PATH):
                service.start(Mock())

        connection.unregisterService.assert_called_once_with(SERVICE_NAME)


if __name__ == "__main__":
    unittest.main()
