from __future__ import annotations

import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from axidev_osk.components.button import Button, ButtonInteractionState
from axidev_osk.components.grid.keyboard import KeyboardWidget
from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.config.defaults.us_iso import build_us_iso_layout_config
from axidev_osk.models import KeySpec
from axidev_osk.runtime.events import ComponentPressed, ComponentReleased, PromptResolved
from axidev_osk.runtime.testing import make_test_context
from axidev_osk.windows.chrome import OverlayTitleBar


class FakeKeyboardBackend:
    ready = True
    status_text = ""
    needs_permission_setup = False

    def add_key_state_listener(self, listener: object) -> object:
        del listener
        return lambda: None

    def is_key_down(self, key_name: str) -> bool:
        del key_name
        return False

    def key_name_for_spec(self, spec: KeySpec) -> str | None:
        return spec.io_key or (spec.label if len(spec.label) == 1 else None)

    def key_down(self, spec: KeySpec, latched_keys: object) -> object:
        del latched_keys
        return spec

    def key_up(self, press_handle: object) -> None:
        del press_handle

    def sync_latched_key(
        self,
        spec: KeySpec,
        latched: bool,
        press_handle: object = None,
    ) -> object:
        del spec, latched
        return press_handle


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class ButtonTests(unittest.TestCase):
    def test_right_click_has_the_same_signal_and_state_cycle_as_left_click(self) -> None:
        _app()
        button = Button("Test")
        self.addCleanup(button.close)
        button.show()
        events: list[tuple[str, object]] = []
        button.pressed.connect(lambda: events.append(("pressed", button.state)))
        button.released.connect(lambda: events.append(("released", button.state)))
        button.clicked.connect(lambda checked: events.append(("clicked", checked)))

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        left_events = events.copy()
        events.clear()
        QTest.mouseClick(button, Qt.MouseButton.RightButton)

        self.assertEqual(events, left_events)
        self.assertEqual(button.state, ButtonInteractionState.IDLE)

    def test_right_click_toggles_a_latchable_button(self) -> None:
        _app()
        button = Button("Test", latchable=True)
        self.addCleanup(button.close)
        button.show()

        QTest.mouseClick(button, Qt.MouseButton.RightButton)

        self.assertEqual(button.state, ButtonInteractionState.LATCHED)
        self.assertTrue(button.isChecked())

        QTest.mouseClick(button, Qt.MouseButton.RightButton)

        self.assertEqual(button.state, ButtonInteractionState.IDLE)
        self.assertFalse(button.isChecked())

    def test_right_click_dispatches_a_built_key_press_and_release(self) -> None:
        _app()
        context = make_test_context(FakeKeyboardBackend())
        keyboard = KeyboardWidget(
            layout_config=build_us_iso_layout_config(),
            context=context,
        )
        self.addCleanup(keyboard.close)
        keyboard.show()
        events: list[object] = []
        context.dispatcher.add_event_handler(
            lambda event: events.append(event)
            if isinstance(event, (ComponentPressed, ComponentReleased))
            else None,
        )
        button = next(
            child
            for child in keyboard.findChildren(Button)
            if child.property("ioKey") == "A"
        )

        QTest.mouseClick(button, Qt.MouseButton.RightButton)

        self.assertEqual(
            [type(event) for event in events],
            [ComponentPressed, ComponentReleased],
        )

    def test_right_click_resolves_a_prompt(self) -> None:
        _app()
        config = build_default_app_config()
        context = make_test_context(FakeKeyboardBackend(), config=config)
        resolved: list[PromptResolved] = []
        context.dispatcher.add_event_handler(
            lambda event: resolved.append(event) if isinstance(event, PromptResolved) else None,
        )
        window = QWidget()
        self.addCleanup(window.close)
        prompt = context.components.build(config.quit_prompt, context, host=window)
        prompt.setParent(window)
        window.show()
        button = next(
            child
            for child in prompt.findChildren(Button)
            if child.property("role") == "accepted"
        )

        QTest.mouseClick(button, Qt.MouseButton.RightButton)

        self.assertEqual(
            resolved,
            [PromptResolved(prompt_id=config.quit_prompt.id, result="accepted")],
        )

    def test_title_bar_close_control_uses_the_shared_button(self) -> None:
        _app()
        title_bar = OverlayTitleBar("Test")
        self.addCleanup(title_bar.close)
        title_bar.show()

        close_button = title_bar.findChild(Button, "layerShellCloseButton")

        self.assertIsNotNone(close_button)
        QTest.mouseClick(close_button, Qt.MouseButton.RightButton)
        self.assertFalse(title_bar.isVisible())


if __name__ == "__main__":
    unittest.main()
