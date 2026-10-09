from __future__ import annotations

import signal
import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QWidget

from axidev_osk.application.quit_controller import ApplicationQuitController


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FakeWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.managed = False

    def set_quit_controller_managed(self, managed: bool) -> None:
        self.managed = managed


class ApplicationQuitControllerTests(unittest.TestCase):
    def test_stdin_eof_handler_allows_windowed_executable_without_stdin(self) -> None:
        controller = ApplicationQuitController(_app())

        with patch("axidev_osk.application.quit_controller.sys.stdin", None):
            controller._install_stdin_eof_handler()

        self.assertIsNone(controller._stdin_notifier)

    def test_request_without_confirmation_runs_callbacks_and_exits(self) -> None:
        app = _app()
        callback = Mock()
        controller = ApplicationQuitController(app)
        controller.register_quit_callback(callback)

        with patch.object(app, "exit") as exit_app:
            controller.request_quit()

        callback.assert_called_once_with()
        exit_app.assert_called_once_with(0)

    def test_confirmed_request_asks_and_waits_for_shutdown(self) -> None:
        app = _app()
        ask = Mock()
        callback = Mock()
        controller = ApplicationQuitController(app, ask_to_quit=ask)
        controller.register_quit_callback(callback)

        with patch.object(app, "exit") as exit_app:
            controller.request_quit()
            ask.assert_called_once_with()
            callback.assert_not_called()
            exit_app.assert_not_called()

            controller.shutdown(3)
            controller.shutdown(4)

        callback.assert_called_once_with()
        exit_app.assert_called_once_with(3)

    def test_sigterm_skips_confirmation_and_runs_callbacks(self) -> None:
        app = _app()
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
        app = _app()
        ask = Mock()
        controller = ApplicationQuitController(app, ask_to_quit=ask)

        with patch("axidev_osk.application.quit_controller.QTimer.singleShot") as single_shot:
            controller._handle_signal(signal.SIGINT, None)
        scheduled_quit = single_shot.call_args.args[1]

        with patch.object(app, "exit") as exit_app:
            scheduled_quit()

        ask.assert_called_once_with()
        exit_app.assert_not_called()

    def test_register_window_marks_window_managed_and_unmanages_on_quit(self) -> None:
        app = _app()
        window = FakeWindow()
        callback = Mock()
        controller = ApplicationQuitController(app)
        controller.register_window(window)
        controller.register_quit_callback(callback)

        self.assertTrue(window.managed)

        with patch.object(app, "exit"):
            controller.request_quit()

        self.assertFalse(window.managed)
        callback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
