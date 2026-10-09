from __future__ import annotations

import signal
import unittest
from unittest.mock import Mock, patch

from axidev_osk.application.quit_controller import ApplicationQuitController
from support import qt_app


class ApplicationQuitControllerTests(unittest.TestCase):
    def test_stdin_eof_handler_allows_windowed_executable_without_stdin(self) -> None:
        controller = ApplicationQuitController(qt_app())

        with patch("axidev_osk.application.quit_controller.sys.stdin", None):
            controller._install_stdin_eof_handler()

        self.assertIsNone(controller._stdin_notifier)

    def test_request_without_confirmation_runs_callbacks_and_exits(self) -> None:
        app = qt_app()
        callback = Mock()
        controller = ApplicationQuitController(app)
        controller.register_quit_callback(callback)

        with patch.object(app, "exit") as exit_app:
            controller.request_quit("signal")

        callback.assert_called_once_with()
        exit_app.assert_called_once_with(0)

    def test_a_failing_shutdown_step_is_logged_and_the_app_still_exits(self) -> None:
        app = qt_app()
        after = Mock()
        controller = ApplicationQuitController(app)
        controller.register_quit_callback(Mock(side_effect=RuntimeError("stop failed")))
        controller.register_quit_callback(after)

        with patch.object(app, "exit") as exit_app, self.assertLogs("axidev_osk.application.quit_controller", "ERROR"):
            controller.shutdown(2)

        after.assert_called_once_with()
        exit_app.assert_called_once_with(2)

    def test_confirmed_request_asks_and_waits_for_shutdown(self) -> None:
        app = qt_app()
        ask = Mock()
        callback = Mock()
        controller = ApplicationQuitController(app, ask_to_quit=ask)
        controller.register_quit_callback(callback)

        with patch.object(app, "exit") as exit_app:
            controller.request_quit("signal")
            ask.assert_called_once_with("signal")
            callback.assert_not_called()
            exit_app.assert_not_called()

            controller.shutdown(3)
            controller.shutdown(4)

        callback.assert_called_once_with()
        exit_app.assert_called_once_with(3)

    def test_sigterm_skips_confirmation_and_runs_callbacks(self) -> None:
        app = qt_app()
        ask = Mock()
        callback = Mock()
        controller = ApplicationQuitController(app, ask_to_quit=ask)
        controller.register_quit_callback(callback)

        with patch("axidev_osk.application.quit_controller.QTimer.singleShot") as single_shot:
            controller._handle_signal(signal.SIGTERM, None)
        scheduled_quit = single_shot.call_args.args[1]

        with patch.object(app, "exit") as exit_app:
            scheduled_quit()

        ask.assert_not_called()
        callback.assert_called_once_with()
        exit_app.assert_called_once_with(0)

    def test_sigint_keeps_confirmation(self) -> None:
        app = qt_app()
        ask = Mock()
        controller = ApplicationQuitController(app, ask_to_quit=ask)

        with patch("axidev_osk.application.quit_controller.QTimer.singleShot") as single_shot:
            controller._handle_signal(signal.SIGINT, None)
        scheduled_quit = single_shot.call_args.args[1]

        with patch.object(app, "exit") as exit_app:
            scheduled_quit()

        ask.assert_called_once_with("signal")
        exit_app.assert_not_called()


if __name__ == "__main__":
    unittest.main()
