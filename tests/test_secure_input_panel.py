from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from axidev_osk.runtime.commands import SecureInputPanelPrepare, SecureInputPanelRelease
from axidev_osk.services.secure_input_panel import SecureInputPanelWorkerService


class SecureInputPanelWorkerServiceTests(unittest.TestCase):
    def test_worker_commands_dispatch_runtime_commands_and_acknowledge(self) -> None:
        service = SecureInputPanelWorkerService()
        service._context = Mock()

        with patch.object(service, "_respond") as respond:
            service._handle_command("PREPARE")
            service._handle_command("PING")
            service._handle_command("RELEASE")

        dispatched = [
            call.args[0]
            for call in service._context.dispatcher.dispatch_command.call_args_list
        ]
        self.assertEqual(
            dispatched,
            [SecureInputPanelPrepare(), SecureInputPanelRelease()],
        )
        self.assertEqual(
            respond.call_args_list,
            [
                unittest.mock.call("PREPARED"),
                unittest.mock.call("PONG"),
                unittest.mock.call("RELEASED"),
            ],
        )

    def test_failed_runtime_command_returns_error(self) -> None:
        service = SecureInputPanelWorkerService()
        service._context = Mock()
        service._context.dispatcher.dispatch_command.side_effect = RuntimeError("failed")

        with patch.object(service, "_respond") as respond:
            service._handle_command("PREPARE")

        respond.assert_called_once_with("ERROR")

    def test_unknown_worker_command_returns_error(self) -> None:
        service = SecureInputPanelWorkerService()
        service._context = Mock()

        with patch.object(service, "_respond") as respond:
            service._handle_command("UNKNOWN")

        service._context.dispatcher.dispatch_command.assert_not_called()
        respond.assert_called_once_with("ERROR")


if __name__ == "__main__":
    unittest.main()
