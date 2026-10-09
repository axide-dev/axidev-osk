from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from axidev_osk.components.button import Button
from axidev_osk.messages import DataMap, MessageResult
from axidev_osk.nodes import BUTTON_PRESSED, BUTTON_RELEASED
from axidev_osk.runtime.testing import make_test_context, start_test_profile
from axidev_osk.windows.builder import build_profile_window
from axidev_osk.windows.chrome import OverlayTitleBar
from support import FakeOverlay, RecordingBackend, qt_app


def _find_button(parent: QWidget, node_id: str) -> Button:
    return next(child for child in parent.findChildren(Button) if child.property("componentId") == node_id)


class ButtonTests(unittest.TestCase):
    def test_right_click_has_the_same_signal_cycle_as_left_click(self) -> None:
        qt_app()
        button = Button("Test")
        self.addCleanup(button.close)
        button.show()
        events: list[object] = []
        button.pressed.connect(lambda: events.append("pressed"))
        button.released.connect(lambda: events.append("released"))
        button.clicked.connect(lambda checked: events.append(("clicked", checked)))

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        left_events = events.copy()
        events.clear()
        QTest.mouseClick(button, Qt.MouseButton.RightButton)

        self.assertEqual(left_events, ["pressed", "released", ("clicked", False)])
        self.assertEqual(events, left_events)

    def test_context_menu_event_is_suppressed(self) -> None:
        qt_app()
        button = Button("Test")
        self.addCleanup(button.close)
        event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(1, 1), QPoint(1, 1))
        event.ignore()

        QApplication.sendEvent(button, event)

        self.assertTrue(event.isAccepted())

    def test_right_click_on_a_profile_button_dispatches_press_and_release(self) -> None:
        qt_app()
        context = make_test_context(RecordingBackend())
        events: list[tuple[str, DataMap]] = []

        def recorder(name: str):
            def record(arguments: DataMap) -> MessageResult:
                events.append((name, arguments))
                return []

            return record

        context.dispatcher.add_raw_event_handler(BUTTON_PRESSED, recorder(BUTTON_PRESSED))
        context.dispatcher.add_raw_event_handler(BUTTON_RELEASED, recorder(BUTTON_RELEASED))
        profile = start_test_profile(
            context,
            {
                "active_profile": "p",
                "profiles": {
                    "p": {
                        "windows": [
                            {
                                "id": "pad",
                                "title": "Pad",
                                "content": {"kind": "button", "id": "moo", "label": "Moo"},
                            }
                        ]
                    }
                },
            },
        )
        with patch("axidev_osk.windows.builder.configure_always_on_top_window", return_value=FakeOverlay()):
            window = build_profile_window(profile.window("pad"), context)
        self.addCleanup(window.deleteLater)
        window.show()

        QTest.mouseClick(_find_button(window, "moo"), Qt.MouseButton.RightButton)

        self.assertEqual(events, [(BUTTON_PRESSED, {"node": "moo"}), (BUTTON_RELEASED, {"node": "moo"})])

    def test_title_bar_close_control_uses_the_shared_button(self) -> None:
        qt_app()
        title_bar = OverlayTitleBar("Test")
        self.addCleanup(title_bar.close)
        title_bar.show()

        close_button = title_bar.findChild(Button, "layerShellCloseButton")

        self.assertIsNotNone(close_button)
        assert close_button is not None
        QTest.mouseClick(close_button, Qt.MouseButton.RightButton)
        self.assertFalse(title_bar.isVisible())


if __name__ == "__main__":
    unittest.main()
