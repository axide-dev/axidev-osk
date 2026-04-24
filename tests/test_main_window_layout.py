from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from axidev_osk.application import OverlayResizeHandle, OverlayTitleBar
from axidev_osk.application.main_window import MainWindow


class FakeKeyboardBackend:
    def __init__(self, *, ready: bool) -> None:
        self.ready = ready
        self.status_text = "Keyboard output is unavailable."
        self.needs_permission_setup = False

    def initialize(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def add_key_state_listener(self, listener):
        return lambda: None

    def is_key_down(self, key_name: str) -> bool:
        return False

    def key_name_for_spec(self, spec):
        return spec.io_key or (spec.label if len(spec.label) == 1 else None)


class FakeOverlayController:
    def __init__(self, *, uses_custom_chrome: bool = True) -> None:
        self.uses_custom_chrome = uses_custom_chrome

    def move_by(self, dx: int, dy: int) -> None:
        return None

    def resize_by(self, dx: int, dy: int) -> None:
        return None

    def handle_show(self) -> bool:
        return True


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class MainWindowLayoutTests(unittest.TestCase):
    def test_custom_chrome_puts_resize_handle_in_title_bar(self) -> None:
        _app()
        overlay = FakeOverlayController()

        with (
            patch(
                "axidev_osk.application.main_window.AxidevIoKeyboardBackend",
                return_value=FakeKeyboardBackend(ready=True),
            ),
            patch(
                "axidev_osk.application.main_window.configure_always_on_top_window",
                return_value=overlay,
            ),
        ):
            window = MainWindow()

        self.addCleanup(window.close)

        central_layout = window.centralWidget().layout()
        self.assertEqual(central_layout.count(), 2)

        title_bar = central_layout.itemAt(0).widget()
        self.assertIsInstance(title_bar, OverlayTitleBar)

        resize_handle = title_bar.findChild(OverlayResizeHandle, "layerShellResizeHandle")
        self.assertIsNotNone(resize_handle)

        close_button = title_bar.findChild(QPushButton, "layerShellCloseButton")
        self.assertIsNotNone(close_button)
        title_bar_layout = title_bar.layout()
        self.assertLess(title_bar_layout.indexOf(resize_handle), title_bar_layout.indexOf(close_button))
        self.assertIsNone(window.findChild(QLabel, "statusLabel"))

    def test_status_footer_is_only_added_when_backend_is_unavailable(self) -> None:
        _app()
        overlay = FakeOverlayController()

        with (
            patch(
                "axidev_osk.application.main_window.AxidevIoKeyboardBackend",
                return_value=FakeKeyboardBackend(ready=False),
            ),
            patch(
                "axidev_osk.application.main_window.configure_always_on_top_window",
                return_value=overlay,
            ),
        ):
            window = MainWindow()

        self.addCleanup(window.close)

        central_layout = window.centralWidget().layout()
        self.assertEqual(central_layout.count(), 3)
        self.assertIsNotNone(window.findChild(QPushButton, "layerShellCloseButton"))
        self.assertIsNotNone(window.findChild(QLabel, "statusLabel"))

    def test_root_surface_uses_styled_background(self) -> None:
        _app()
        overlay = FakeOverlayController()

        with (
            patch(
                "axidev_osk.application.main_window.AxidevIoKeyboardBackend",
                return_value=FakeKeyboardBackend(ready=True),
            ),
            patch(
                "axidev_osk.application.main_window.configure_always_on_top_window",
                return_value=overlay,
            ),
        ):
            window = MainWindow()

        self.addCleanup(window.close)

        central = window.centralWidget()
        self.assertTrue(central.testAttribute(Qt.WidgetAttribute.WA_StyledBackground))


if __name__ == "__main__":
    unittest.main()
