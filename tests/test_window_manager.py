from __future__ import annotations

import unittest
from unittest.mock import Mock

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from axidev_osk.runtime.window_manager import WindowManager
from axidev_osk.windows.builder import _WindowInputBlocker


class WindowManagerVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = Mock()
        self.manager = WindowManager({"window:keyboard": lambda: self.window})
        self.manager.get_or_create("window:keyboard")

    def test_hide_hides_window(self) -> None:
        self.manager.hide("window:keyboard")

        self.window.hide.assert_called_once_with()
        self.window.showMinimized.assert_not_called()

    def test_show_restores_a_minimized_window_on_every_platform(self) -> None:
        self.window.isMinimized.return_value = True

        self.manager.show("window:keyboard")

        self.window.showNormal.assert_called_once_with()
        self.window.show.assert_not_called()

    def test_show_uses_normal_show_when_not_minimized(self) -> None:
        self.window.isMinimized.return_value = False

        self.manager.show("window:keyboard")

        self.window.show.assert_called_once_with()
        self.window.showNormal.assert_not_called()

    def test_input_blocker_lets_through_only_nodes_that_pass_the_block(self) -> None:
        window = QWidget()
        ghost = QPushButton(window)
        ghost.setProperty("passesInputBlock", True)
        normal_key = QPushButton(window)
        blocker = _WindowInputBlocker(window)
        event = QEvent(QEvent.Type.MouseButtonPress)

        self.assertFalse(blocker.eventFilter(ghost, event))
        self.assertTrue(blocker.eventFilter(normal_key, event))
        self.assertTrue(blocker.eventFilter(window, event))

    def test_windows_are_built_lazily(self) -> None:
        built: list[object] = []
        manager = WindowManager({"pad": lambda: built.append(None) or self.window})

        self.assertIsNone(manager.get("pad"))
        self.assertIs(manager.get_or_create("pad"), self.window)
        self.assertIs(manager.get_or_create("pad"), self.window)
        self.assertEqual(built, [None])
        with self.assertRaisesRegex(ValueError, "No window named 'nope'"):
            manager.get_or_create("nope")

    def test_close_releases_and_forgets_every_window(self) -> None:
        other = Mock()
        manager = WindowManager({"a": lambda: self.window, "b": lambda: other})
        manager.get_or_create("a")
        manager.get_or_create("b")

        manager.close("a")

        self.assertIsNone(manager.get("a"))
        self.window.release_platform_resources.assert_called_once_with()
        self.window.deleteLater.assert_called_once_with()
        self.window.close.assert_not_called()

        manager.close_all()
        self.assertEqual(manager.all_windows(), [])
        other.deleteLater.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
