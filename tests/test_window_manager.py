from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from axidev_osk.runtime.window_manager import WindowManager, _WindowInputBlocker


class WindowManagerVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = Mock()
        self.manager = WindowManager.__new__(WindowManager)
        self.manager._windows = {"window:keyboard": self.window}
        self.manager._configs = {"window:keyboard": SimpleNamespace(opacity=0.85)}
        self.manager._input_blockers = {}

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

    def test_input_blocker_allows_only_the_recovery_component(self) -> None:
        window = QWidget()
        ghost = QPushButton(window)
        ghost.setProperty("componentId", "key:ghost")
        normal_key = QPushButton(window)
        normal_key.setProperty("componentId", "key:a")
        blocker = _WindowInputBlocker(window, "key:ghost")
        event = QEvent(QEvent.Type.MouseButtonPress)

        self.assertFalse(blocker.eventFilter(ghost, event))
        self.assertTrue(blocker.eventFilter(normal_key, event))
        self.assertTrue(blocker.eventFilter(window, event))

    def test_toggle_opacity_restores_configured_opacity_on_second_call(self) -> None:
        window = QWidget()
        self.manager._windows = {"window:keyboard": window}

        self.manager.toggle_opacity(
            "window:keyboard",
            component_id="key:ghost",
            opacity=0.01,
        )

        self.assertAlmostEqual(window.windowOpacity(), 0.01, delta=0.005)
        self.assertIn("window:keyboard", self.manager._input_blockers)

        self.manager.toggle_opacity(
            "window:keyboard",
            component_id="key:ghost",
            opacity=0.01,
        )

        self.assertAlmostEqual(window.windowOpacity(), 0.85, delta=0.005)
        self.assertNotIn("window:keyboard", self.manager._input_blockers)

    def test_show_restores_configured_opacity_and_removes_input_blocker(self) -> None:
        window = QWidget()
        window.setWindowOpacity(0.01)
        blocker = _WindowInputBlocker(window, "key:ghost")
        self.app.installEventFilter(blocker)
        self.manager._windows = {"window:keyboard": window}
        self.manager._input_blockers = {"window:keyboard": blocker}

        self.manager.show("window:keyboard")

        self.assertAlmostEqual(window.windowOpacity(), 0.85, delta=0.005)
        self.assertNotIn("window:keyboard", self.manager._input_blockers)


if __name__ == "__main__":
    unittest.main()
