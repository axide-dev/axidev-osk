from __future__ import annotations

import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from axidev_osk.components.button import Button
from axidev_osk.components.grid.keyboard import KeyboardWidget
from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.config.models import KeyboardGridConfig
from axidev_osk.messages import MessageResult
from axidev_osk.runtime.behavior_models import KeyboardOutput
from axidev_osk.runtime.config_paths import surface_source_path
from axidev_osk.runtime.events import (
    COMPONENT_PRESSED,
    COMPONENT_RELEASED,
    PROMPT_RESOLVED,
    ComponentPressedArguments,
    ComponentReleasedArguments,
    PromptResolvedArguments,
)
from axidev_osk.runtime.testing import make_test_context
from axidev_osk.windows.chrome import OverlayTitleBar


class FakeKeyboardBackend:
    ready = True
    status_text = ""
    needs_permission_setup = False
    permission_setup_text = ""

    def add_modifier_state_listener(self, listener):
        del listener
        return lambda: None

    def add_observation_listener(self, listener):
        del listener
        return lambda: None

    def add_key_state_listener(self, listener):
        del listener
        return lambda: None

    def is_key_down(self, key_name: str) -> bool:
        del key_name
        return False

    def key_name_for_output(self, output: KeyboardOutput) -> str:
        return output.output_key

    def state_tags_for_key(self, output_key: str) -> frozenset[str]:
        del output_key
        return frozenset()

    def key_down(self, output: KeyboardOutput, active_state_tags: frozenset[str]) -> object:
        del active_state_tags
        return output

    def key_up(self, press_handle: object) -> None:
        del press_handle


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _keyboard_widget(test: unittest.TestCase, context) -> KeyboardWidget:
    window = context.config.windows[0]
    grid = window.surface.components[0]
    assert isinstance(grid, KeyboardGridConfig)
    keyboard = KeyboardWidget(
        layout_config=grid.layout,
        context=context,
        source_path=surface_source_path(context.config, window.id, window.surface.id).child(
            "component",
            grid.id,
        ),
    )
    test.addCleanup(keyboard.close)
    keyboard.show()
    return keyboard


def _button_with_text(parent: QWidget, text: str) -> Button:
    return next(child for child in parent.findChildren(Button) if child.text() == text)


class ButtonTests(unittest.TestCase):
    def test_right_click_has_the_same_signal_cycle_as_left_click(self) -> None:
        _app()
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

    def test_right_click_latches_a_latchable_control_through_runtime_state(self) -> None:
        _app()
        context = make_test_context(FakeKeyboardBackend())
        context.dispatcher.register_action(
            "window.set_dwell_enabled",
            lambda arguments: arguments,
            lambda arguments: [],
        )
        dwell = _button_with_text(_keyboard_widget(self, context), "Dwell")

        QTest.mouseClick(dwell, Qt.MouseButton.RightButton)
        QApplication.processEvents()

        self.assertTrue(dwell.property("latched"))
        self.assertTrue(dwell.isChecked())

        QTest.mouseClick(dwell, Qt.MouseButton.RightButton)
        QApplication.processEvents()

        self.assertFalse(dwell.property("latched"))
        self.assertFalse(dwell.isChecked())

    def test_right_click_dispatches_a_built_key_press_and_release(self) -> None:
        _app()
        context = make_test_context(FakeKeyboardBackend())
        events: list[str] = []

        def record_pressed(event: ComponentPressedArguments) -> MessageResult:
            del event
            events.append(COMPONENT_PRESSED)
            return []

        def record_released(event: ComponentReleasedArguments) -> MessageResult:
            del event
            events.append(COMPONENT_RELEASED)
            return []

        context.dispatcher.add_event_handler(COMPONENT_PRESSED, record_pressed)
        context.dispatcher.add_event_handler(COMPONENT_RELEASED, record_released)
        button = _button_with_text(_keyboard_widget(self, context), "a")

        QTest.mouseClick(button, Qt.MouseButton.RightButton)

        self.assertEqual(events, [COMPONENT_PRESSED, COMPONENT_RELEASED])

    def test_right_click_resolves_a_prompt(self) -> None:
        _app()
        config = build_default_app_config()
        context = make_test_context(FakeKeyboardBackend(), config=config)
        resolved: list[PromptResolvedArguments] = []
        context.dispatcher.add_event_handler(
            PROMPT_RESOLVED,
            lambda event: resolved.append(event) or [],
        )
        prompt_config = config.quit_prompt
        window = QWidget()
        self.addCleanup(window.close)
        prompt = context.components.build(
            prompt_config,
            context,
            source_path=surface_source_path(
                config,
                prompt_config.window_id,
                prompt_config.surface_id,
            ).child("component", prompt_config.id),
            host=window,
        )
        prompt.setParent(window)
        window.show()
        button = prompt.findChild(Button, "confirmAcceptButton")
        assert button is not None

        QTest.mouseClick(button, Qt.MouseButton.RightButton)

        self.assertEqual(
            resolved,
            [PromptResolvedArguments(prompt_id=prompt_config.id, result="accepted")],
        )

    def test_title_bar_close_control_uses_the_shared_button(self) -> None:
        _app()
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
