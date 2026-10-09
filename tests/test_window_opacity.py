from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from axidev_osk.windows.opacity import WindowOpacityController


class WindowOpacityControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_wayland_applies_every_opacity_value_to_content(self) -> None:
        window = QMainWindow()
        content = QWidget()
        window.setCentralWidget(content)
        controller = WindowOpacityController(window)

        with patch(
            "axidev_osk.windows.opacity.QGuiApplication.platformName",
            return_value="wayland",
        ):
            controller.set_opacity(0.85)
            effect = content.graphicsEffect()
            self.assertIsNotNone(effect)
            self.assertAlmostEqual(effect.opacity(), 0.85, delta=0.005)

            controller.set_opacity(0.01)
            self.assertIs(content.graphicsEffect(), effect)
            self.assertAlmostEqual(effect.opacity(), 0.01, delta=0.005)

    def test_non_wayland_applies_opacity_to_native_window(self) -> None:
        window = QMainWindow()
        window.setCentralWidget(QWidget())
        controller = WindowOpacityController(window)

        with patch(
            "axidev_osk.windows.opacity.QGuiApplication.platformName",
            return_value="windows",
        ):
            controller.set_opacity(0.42)

        self.assertAlmostEqual(window.windowOpacity(), 0.42, delta=0.005)
        self.assertIsNone(window.centralWidget().graphicsEffect())


if __name__ == "__main__":
    unittest.main()
