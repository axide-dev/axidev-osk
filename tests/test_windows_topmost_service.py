from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

from axidev_osk.runtime.window_manager import WindowManager
from axidev_osk.services.windows_topmost import WindowsTopmostService


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class WindowsTopmostServiceTests(unittest.TestCase):
    def test_window_manager_reapplies_only_always_on_top_windows(self) -> None:
        manager = WindowManager.__new__(WindowManager)
        topmost_window = Mock(always_on_top=True)
        plain_window = Mock(always_on_top=False)
        manager._windows = {"topmost": topmost_window, "plain": plain_window}

        manager.reapply_always_on_top_windows()

        topmost_window.reapply_always_on_top.assert_called_once_with()
        plain_window.reapply_always_on_top.assert_not_called()

    def test_start_is_noop_off_windows(self) -> None:
        service = WindowsTopmostService()

        with patch("axidev_osk.services.windows_topmost.sys.platform", "linux"):
            service.start(Mock())

        self.assertIsNone(service._hook)

    def test_window_event_debounces_topmost_refresh(self) -> None:
        _app()
        reapply = Mock()
        service = WindowsTopmostService(reapply)

        with patch("axidev_osk.services.windows_topmost.QTimer.singleShot") as single_shot:
            service._handle_window_event(1, 2, 3, 4, 5, 6, 7)
            service._handle_window_event(1, 2, 3, 4, 5, 6, 7)

        single_shot.assert_called_once_with(50, service._refresh_topmost_windows)

        service._refresh_topmost_windows()

        reapply.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
