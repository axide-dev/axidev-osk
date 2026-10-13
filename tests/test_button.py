from __future__ import annotations

import unittest

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QContextMenuEvent, QFontInfo, QFontMetrics, QPainterPath, QPolygonF, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from axidev_osk.components.button import Button
from axidev_osk.messages import DataMap, MessageResult
from axidev_osk.nodes import BUTTON_PRESSED, BUTTON_RELEASED
from axidev_osk.runtime.profile_runtime import state_set
from axidev_osk.windows.chrome import OverlayTitleBar
from support import RecordingBackend, build_window, find_node, make_test_engine, qt_app, start_test_profile


class ButtonTests(unittest.TestCase):
    def test_labels_shrink_to_fit_but_never_grow_past_the_style_size(self) -> None:
        qt_app()
        button = Button()
        self.addCleanup(button.close)
        button.setStyleSheet("QPushButton { font-size: 18px; padding: 0px; border: none; }")
        button.resize(60, 40)
        button.show()
        area = button.rect()

        self.assertEqual(QFontInfo(button.fitted_font("a", area)).pixelSize(), 18)
        long = button.fitted_font("Backspace Backspace", area)
        self.assertLess(QFontInfo(long).pixelSize(), 18)
        self.assertLessEqual(QFontMetrics(long).horizontalAdvance("Backspace Backspace"), area.width())

        # A clipped button fits its label inside the clipped shape, not its rectangle.
        button.setMask(QRegion(QRect(20, 10, 20, 20)))
        clipped = button.fitted_font("Back", area)
        self.assertLessEqual(QFontMetrics(clipped).horizontalAdvance("Back"), 20)

    def test_state_text_colors_apply_even_to_a_label_that_shrinks(self) -> None:
        qt_app()
        button = Button("Backspace")
        self.addCleanup(button.close)
        button.setStyleSheet(
            "QPushButton { font-size: 40px; color: #ffffff; background: #000000; border: none; padding: 0px; }"
            "QPushButton:pressed { color: #0000ff; }"
        )
        button.resize(60, 30)
        button.show()

        def text_pixels() -> list[QColor]:
            image = button.grab().toImage()
            return [
                image.pixelColor(x, y)
                for x in range(image.width())
                for y in range(image.height())
                if image.pixelColor(x, y).lightness() > 60
            ]

        idle = text_pixels()
        button.setDown(True)
        pressed = text_pixels()

        self.assertTrue(idle and all(color.blue() >= color.red() for color in idle))
        self.assertTrue(pressed)
        self.assertTrue(all(color.red() < 80 and color.blue() > 120 for color in pressed))

    def test_a_shaped_button_draws_its_border_along_its_shape(self) -> None:
        qt_app()
        button = Button()
        self.addCleanup(button.close)
        button.setStyleSheet("QPushButton { background: #000000; border: 1px solid #ff0000; border-radius: 0px; }")
        button.resize(100, 100)
        triangle = QPainterPath()
        triangle.addPolygon(QPolygonF([QPointF(0, 0), QPointF(100, 0), QPointF(0, 100)]))
        triangle.closeSubpath()
        button.set_shape(triangle)
        button.show()

        image = button.grab().toImage()

        # Just inside the long side, the border shows; well inside, only the background does.
        edge = image.pixelColor(49, 49)
        inside = image.pixelColor(20, 20)
        self.assertGreater(edge.red(), 120)
        self.assertLess(inside.red(), 40)

    def test_parts_are_spread_inside_the_shape_in_order(self) -> None:
        qt_app()
        button = Button()
        self.addCleanup(button.close)
        button.setStyleSheet("QPushButton { font-size: 14px; padding: 0px; border: none; }")
        button.resize(120, 120)
        button.setMask(QRegion(QPolygonF([QPointF(0, 0), QPointF(120, 0), QPointF(60, 120)]).toPolygon()))
        button.show()
        parts = ("q", "w", "e", "r", "t", "y", "u", "i", "o", "p")

        _font, placed = button.spread(parts, button.rect())

        self.assertEqual([part for _box, part in placed], list(parts))
        mask = button.mask()
        for box, part in placed:
            with self.subTest(part):
                self.assertEqual(mask.intersected(box), QRegion(box))
        rows = [box.top() for box, _part in placed]
        self.assertEqual(rows, sorted(rows))

    def test_parts_never_land_in_a_gap_of_a_dented_shape(self) -> None:
        qt_app()
        button = Button()
        self.addCleanup(button.close)
        button.setStyleSheet("QPushButton { font-size: 14px; padding: 0px; border: none; }")
        button.resize(200, 200)
        # A U: two arms joined at the bottom, with a gap between them.
        u_shape = QRegion(QRect(0, 0, 60, 200)) + QRegion(QRect(140, 0, 60, 200)) + QRegion(QRect(0, 140, 200, 60))
        button.setMask(u_shape)
        button.show()

        for parts in (("Hello", "World"), ("a", "b", "c", "d")):
            _font, placed = button.spread(parts, button.rect())
            with self.subTest(parts):
                self.assertEqual([part for _box, part in placed], list(parts))
                for box, _part in placed:
                    self.assertEqual(u_shape.intersected(box), QRegion(box))

    def test_state_text_colors_apply_to_label_parts(self) -> None:
        qt_app()
        button = Button()
        self.addCleanup(button.close)
        button.setStyleSheet(
            "QPushButton { font-size: 20px; color: #ffffff; background: #000000; border: none; padding: 0px; }"
            "QPushButton:pressed { color: #0000ff; }"
        )
        button.resize(120, 60)
        button.set_parts(("Ab", "Cd"))
        button.show()
        button.setDown(True)

        image = button.grab().toImage()
        text = [
            image.pixelColor(x, y)
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).lightness() > 60
        ]

        self.assertTrue(text)
        self.assertTrue(all(color.red() < 80 and color.blue() > 120 for color in text))

    def test_a_list_label_that_empties_shows_nothing(self) -> None:
        qt_app()
        engine = make_test_engine(RecordingBackend())
        content = {"kind": "button", "id": "menu", "label": lambda state: list(state.parts)}
        profile = start_test_profile(
            engine,
            {
                "active_profile": "p",
                "profiles": {
                    "p": {
                        "state": {"parts": {"var": {"list": "string"}, "default": ["a", "b"]}},
                        "windows": [{"id": "pad", "title": "Pad", "content": content}],
                    }
                },
            },
        )
        button = find_node(build_window(self, profile.window("pad"), engine), "menu")
        self.assertEqual(button.text(), "a b")  # type: ignore[attr-defined]

        engine.dispatcher.dispatch(state_set("parts", []))

        self.assertEqual(button.text(), "")  # type: ignore[attr-defined]

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
