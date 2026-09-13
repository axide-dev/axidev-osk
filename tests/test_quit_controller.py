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
        controller = ApplicationQuitController(_app(), prompt=lambda _parent: True)

        with patch("axidev_osk.application.quit_controller.sys.stdin", None):
            controller._install_stdin_eof_handler()

        self.assertIsNone(controller._stdin_notifier)

    def test_request_quit_runs_callbacks_after_confirmation(self) -> None:
        app = _app()
        callback = Mock()
        controller = ApplicationQuitController(app, prompt=lambda _parent: True)
        controller.register_quit_callback(callback)

        with patch.object(app, "exit") as exit_app:
            controller.request_quit()

        callback.assert_called_once_with()
        exit_app.assert_called_once_with(0)

    def test_request_quit_does_not_run_callbacks_when_cancelled(self) -> None:
        app = _app()
        callback = Mock()
        controller = ApplicationQuitController(app, prompt=lambda _parent: False)
        controller.register_quit_callback(callback)

        with patch.object(app, "exit") as exit_app:
            controller.request_quit()

        callback.assert_not_called()
        exit_app.assert_not_called()

    def test_sigterm_skips_confirmation_and_runs_callbacks(self) -> None:
        app = _app()
        prompt = Mock(return_value=False)
        callback = Mock()
        controller = ApplicationQuitController(app, prompt=prompt)
        controller.register_quit_callback(callback)

        with patch("axidev_osk.application.quit_controller.QTimer.singleShot") as single_shot:
            controller._handle_signal(signal.SIGTERM, None)
        scheduled_quit = single_shot.call_args.args[1]

        with patch.object(app, "exit") as exit_app:
            scheduled_quit()

        prompt.assert_not_called()
        callback.assert_called_once_with()
        exit_app.assert_called_once_with(0)

    def test_sigint_keeps_confirmation(self) -> None:
        app = _app()
        prompt = Mock(return_value=False)
        controller = ApplicationQuitController(app, prompt=prompt)

        with patch("axidev_osk.application.quit_controller.QTimer.singleShot") as single_shot:
            controller._handle_signal(signal.SIGINT, None)
        scheduled_quit = single_shot.call_args.args[1]

        with patch.object(app, "exit") as exit_app:
            scheduled_quit()

        prompt.assert_called_once_with(app.activeWindow())
        exit_app.assert_not_called()

    def test_register_window_marks_window_managed_and_unmanages_on_quit(self) -> None:
        app = _app()
        window = FakeWindow()
        callback = Mock()
        controller = ApplicationQuitController(app, prompt=lambda _parent: True)
        controller.register_window(window)
        controller.register_quit_callback(callback)

        self.assertTrue(window.managed)

        with patch.object(app, "exit"):
            controller.request_quit()

        self.assertFalse(window.managed)
        callback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
