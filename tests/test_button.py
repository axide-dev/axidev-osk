from __future__ import annotations

import unittest

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from axidev_osk.components.button import Button
from axidev_osk.messages import DataMap, MessageResult
from axidev_osk.nodes import BUTTON_PRESSED, BUTTON_RELEASED
from axidev_osk.windows.chrome import OverlayTitleBar
from support import RecordingBackend, build_window, find_node, make_test_engine, qt_app, start_test_profile


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
        engine = make_test_engine(RecordingBackend())
        events: list[tuple[str, DataMap]] = []

        def recorder(name: str):
            def record(arguments: DataMap) -> MessageResult:
                events.append((name, arguments))
                return []

            return record

        engine.dispatcher.add_raw_event_handler(BUTTON_PRESSED, recorder(BUTTON_PRESSED))
        engine.dispatcher.add_raw_event_handler(BUTTON_RELEASED, recorder(BUTTON_RELEASED))
        profile = start_test_profile(
            engine,
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
        window = build_window(self, profile.window("pad"), engine)
        window.show()

        QTest.mouseClick(find_node(window, "moo"), Qt.MouseButton.RightButton)
        self.assertEqual(events, [])
        engine.dispatcher.process_pending()

        self.assertEqual(
            events, [(BUTTON_PRESSED, {"node": "moo", "button": "right"}), (BUTTON_RELEASED, {"node": "moo", "button": "right"})]
        )

    def test_title_bar_close_control_uses_the_shared_button(self) -> None:
        qt_app()
        title_bar = OverlayTitleBar("Test")
        self.addCleanup(title_bar.close)
        title_bar.show()

        close_button = title_bar.findChild(Button, "layerShellCloseButton")

        self.assertIsNotNone(close_button)
        assert close_button is not None
        pressed: list[str] = []
        title_bar.closePressed.connect(pressed.append)
        QTest.mouseClick(close_button, Qt.MouseButton.RightButton)
        self.assertEqual(pressed, ["right"])


if __name__ == "__main__":
    unittest.main()
