from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import call, patch

from axidev_osk.messages import MessageResult
from axidev_osk.runtime.app_messages import (
    SECURE_INPUT_PANEL_PREPARE,
    SECURE_INPUT_PANEL_RELEASE,
    register_app_events,
    secure_input_panel_prepared,
    secure_input_panel_released,
)
from axidev_osk.runtime.decoding import EmptyArguments, decode_empty
from axidev_osk.runtime.dispatcher import Dispatcher
from axidev_osk.services.secure_input_panel import SecureInputPanelWorkerService


class SecureInputPanelWorkerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dispatcher = Dispatcher()
        register_app_events(self.dispatcher)
        self.actions: list[str] = []
        self.prepare_error: Exception | None = None

        def prepare(arguments: EmptyArguments) -> MessageResult:
            del arguments
            self.actions.append(SECURE_INPUT_PANEL_PREPARE)
            if self.prepare_error is not None:
                raise self.prepare_error
            return [secure_input_panel_prepared()]

        def release(arguments: EmptyArguments) -> MessageResult:
            del arguments
            self.actions.append(SECURE_INPUT_PANEL_RELEASE)
            return [secure_input_panel_released()]

        self.dispatcher.register_action(SECURE_INPUT_PANEL_PREPARE, decode_empty, prepare)
        self.dispatcher.register_action(SECURE_INPUT_PANEL_RELEASE, decode_empty, release)
        self.service = SecureInputPanelWorkerService()
        context = SimpleNamespace(dispatcher=self.dispatcher)
        with (
            patch("axidev_osk.services.secure_input_panel.QSocketNotifier"),
            patch.object(self.service, "_respond") as respond,
        ):
            self.service.start(context)  # type: ignore[arg-type]
        respond.assert_called_once_with("READY")

    def test_worker_commands_dispatch_runtime_actions_and_answer_from_events(self) -> None:
        with patch.object(self.service, "_respond") as respond:
            self.service._handle_command("PREPARE")
            self.service._handle_command("PING")
            self.service._handle_command("RELEASE")

        self.assertEqual(self.actions, [SECURE_INPUT_PANEL_PREPARE, SECURE_INPUT_PANEL_RELEASE])
        self.assertEqual(
            respond.call_args_list,
            [call("PREPARED"), call("PONG"), call("RELEASED")],
        )

    def test_failed_runtime_action_returns_error(self) -> None:
        self.prepare_error = RuntimeError("failed")

        with patch.object(self.service, "_respond") as respond:
            self.service._handle_command("PREPARE")

        respond.assert_called_once_with("ERROR")

    def test_unknown_worker_command_returns_error(self) -> None:
        with patch.object(self.service, "_respond") as respond:
            self.service._handle_command("UNKNOWN")

        self.assertEqual(self.actions, [])
        respond.assert_called_once_with("ERROR")

    def test_stopped_worker_ignores_late_runtime_events(self) -> None:
        with patch.object(self.service, "_respond") as respond:
            self.service.stop()
            self.dispatcher.dispatch(secure_input_panel_prepared())

        respond.assert_not_called()


if __name__ == "__main__":
    unittest.main()
