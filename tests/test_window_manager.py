from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from axidev_osk.runtime.window_manager import WindowManager


class WindowManagerVisibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = Mock()
        self.manager = WindowManager.__new__(WindowManager)
        self.manager._windows = {"window:keyboard": self.window}
        self.manager._configs = {}

    def test_windows_hide_hides_window(self) -> None:
        with patch("axidev_osk.runtime.window_manager.sys.platform", "win32"):
            self.manager.hide("window:keyboard")

        self.window.hide.assert_called_once_with()
        self.window.showMinimized.assert_not_called()

    def test_windows_show_restores_window(self) -> None:
        self.window.isMinimized.return_value = True

        with patch("axidev_osk.runtime.window_manager.sys.platform", "win32"):
            self.manager.show("window:keyboard")

        self.window.showNormal.assert_called_once_with()
        self.window.show.assert_not_called()

    def test_windows_show_uses_normal_show_when_not_minimized(self) -> None:
        self.window.isMinimized.return_value = False

        with patch("axidev_osk.runtime.window_manager.sys.platform", "win32"):
            self.manager.show("window:keyboard")

        self.window.show.assert_called_once_with()
        self.window.showNormal.assert_not_called()

    def test_windows_minimized_window_remains_visible(self) -> None:
        self.window.isVisible.return_value = True
        self.window.isMinimized.return_value = True

        with patch("axidev_osk.runtime.window_manager.sys.platform", "win32"):
            self.assertTrue(self.manager.is_visible("window:keyboard"))
            self.assertTrue(self.manager.is_minimized("window:keyboard"))

    def test_linux_hide_still_hides_window(self) -> None:
        with patch("axidev_osk.runtime.window_manager.sys.platform", "linux"):
            self.manager.hide("window:keyboard")

        self.window.hide.assert_called_once_with()
        self.window.showMinimized.assert_not_called()


if __name__ == "__main__":
    unittest.main()
