from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from axidev_osk.runtime.window_manager import WindowManager, _WindowInputBlocker


class WindowManagerVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = Mock(configured_opacity=0.85)
        self.manager = WindowManager({"window:keyboard": lambda parent: self.window})
        self.manager.get_or_create("window:keyboard")

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
        blocker = _WindowInputBlocker(window, frozenset({"key:ghost"}))
        event = QEvent(QEvent.Type.MouseButtonPress)

        self.assertFalse(blocker.eventFilter(ghost, event))
        self.assertTrue(blocker.eventFilter(normal_key, event))
        self.assertTrue(blocker.eventFilter(window, event))

    def test_windows_are_built_lazily_from_factories(self) -> None:
        built: list[object] = []
        manager = WindowManager({"pad": lambda parent: built.append(parent) or self.window})

        self.assertIsNone(manager.get("pad"))
        self.assertIs(manager.get_or_create("pad"), self.window)
        self.assertIs(manager.get_or_create("pad"), self.window)
        self.assertEqual(built, [None])
        with self.assertRaisesRegex(ValueError, "No window named 'nope'"):
            manager.get_or_create("nope")

    def test_opacity_and_input_blocking_are_separate_effects(self) -> None:
        self.manager.set_opacity("window:keyboard", 0.01)
        self.manager.block_input("window:keyboard", frozenset({"ghost"}))
        self.manager.show("window:keyboard")

        self.window.set_visual_opacity.assert_called_once_with(0.01)
        self.assertIn("window:keyboard", self.manager._input_blockers)

        self.manager.unblock_input("window:keyboard")
        self.manager.unblock_input("window:keyboard")
        self.assertNotIn("window:keyboard", self.manager._input_blockers)

    def test_close_and_destroy_remove_input_blocks(self) -> None:
        self.manager.get_or_create("window:keyboard")
        self.manager.block_input("window:keyboard", frozenset())
        self.manager.close("window:keyboard")
        self.assertEqual(self.manager._input_blockers, {})

        self.manager.get_or_create("window:keyboard")
        self.manager.block_input("window:keyboard", frozenset())
        self.manager.destroy("window:keyboard")
        self.assertEqual(self.manager._input_blockers, {})
        self.window.release_platform_resources.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
