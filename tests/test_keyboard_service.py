from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtWidgets import QApplication, QPushButton

from axidev_osk.components.grid.keyboard import KeyboardWidget
from axidev_osk.config.defaults.us_iso import build_us_iso_layout_config
from axidev_osk.messages import MessageResult, RuntimeAction
from axidev_osk.models import KeySpec
from axidev_osk.runtime.actions import (
    keyboard_key_down,
    keyboard_sync_latched_key,
    window_toggle_opacity,
)
from axidev_osk.runtime.events import (
    COMPONENT_PRESSED,
    KEYBOARD_KEY_STATE_CHANGED,
    KEYBOARD_LATCH_CHANGED,
    ComponentPressedArguments,
    KeyboardKeyStateChangedArguments,
    KeyboardLatchChangedArguments,
)
from axidev_osk.runtime.identity import keyboard_key_states_namespace, keyboard_latches_namespace
from axidev_osk.runtime.testing import make_test_context

LAYOUT_ID = "layout:us-iso"


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FakeKeyboardBackend:
    def __init__(self, pressed_key_names: set[str] | None = None) -> None:
        self.ready = True
        self.status_text = "ready"
        self.needs_permission_setup = False
        self.permission_setup_text = ""
        self._pressed_key_names = pressed_key_names or set()
        self._listeners = []
        self.key_down = Mock(return_value=SimpleNamespace(name="press"))
        self.key_up = Mock()
        self.sync_latched_key = Mock(return_value=None)

    def initialize(self) -> bool:
        return True

    def shutdown(self) -> None:
        return None

    def add_key_state_listener(self, listener):
        self._listeners.append(listener)

        def unsubscribe() -> None:
            self._listeners.remove(listener)

        return unsubscribe

    def is_key_down(self, key_name: str) -> bool:
        return key_name in self._pressed_key_names

    def key_name_for_spec(self, spec: KeySpec) -> str | None:
        return spec.io_key or (spec.label if len(spec.label) == 1 else None)

    def emit_key_state(self, key_name: str, pressed: bool) -> None:
        if pressed:
            self._pressed_key_names.add(key_name)
        else:
            self._pressed_key_names.discard(key_name)
        for listener in tuple(self._listeners):
            listener(key_name, pressed)


class KeyboardServiceTests(unittest.TestCase):
    def test_runtime_actions_reject_non_namespaced_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "dot-separated"):
            RuntimeAction(action="unknown", arguments={})

    def test_action_keys_reject_keyboard_behavior(self) -> None:
        action = window_toggle_opacity("window:keyboard", "key:ghost", 0.01)

        with self.assertRaisesRegex(ValueError, "keyboard output or latch behavior"):
            KeySpec(label="Ghost", row=0, column=0, io_key="A", repeats=False, action=action)
        with self.assertRaisesRegex(ValueError, "cannot repeat"):
            KeySpec(label="Ghost", row=0, column=0, action=action)

    def test_ghost_key_emits_action_event_without_keyboard_output(self) -> None:
        _app()
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        events: list[ComponentPressedArguments] = []

        def record(event: ComponentPressedArguments) -> MessageResult:
            events.append(event)
            return []

        context.dispatcher.add_event_handler(COMPONENT_PRESSED, record)
        widget = KeyboardWidget(layout_config=build_us_iso_layout_config(), context=context)
        self.addCleanup(widget.close)
        ghost = next(
            button
            for button in widget.findChildren(QPushButton)
            if button.text() == "Ghost"
        )

        ghost.click()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].component_id, ghost.property("componentId"))
        self.assertIsNotNone(events[0].action)
        backend.key_down.assert_not_called()
        backend.key_up.assert_not_called()

    def test_service_emits_backend_key_state_changed_on_backend_update(self) -> None:
        backend = FakeKeyboardBackend()
        context = make_test_context(backend, services={"keyboard"})
        spec = KeySpec(label="A", row=0, column=0, io_key="A")
        events: list[KeyboardKeyStateChangedArguments] = []

        def record(event: KeyboardKeyStateChangedArguments) -> MessageResult:
            events.append(event)
            return []

        context.dispatcher.add_event_handler(KEYBOARD_KEY_STATE_CHANGED, record)

        context.keyboard.register_key_spec(LAYOUT_ID, spec)
        backend.emit_key_state("A", True)

        self.assertEqual(events, [KeyboardKeyStateChangedArguments(layout_id=LAYOUT_ID, key_id="A", pressed=True, latched=False)])

    def test_service_writes_keyboard_key_state_namespace(self) -> None:
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        spec = KeySpec(label="A", row=0, column=0, io_key="A")

        context.keyboard.register_key_spec(LAYOUT_ID, spec)
        backend.emit_key_state("A", True)

        self.assertEqual(
            context.state.get(keyboard_key_states_namespace(LAYOUT_ID), "A"),
            {"pressed": True, "latched": False},
        )

    def test_widget_renders_from_snapshot_without_backend_press(self) -> None:
        _app()
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        context.state.set(keyboard_key_states_namespace(LAYOUT_ID), "A", {"pressed": True, "latched": False})

        widget = KeyboardWidget(layout_config=build_us_iso_layout_config(), context=context)
        self.addCleanup(widget.close)

        button = self._button_for_io_key(widget, "A")
        self.assertEqual(button.property("interactionState"), "pressed")
        backend.key_down.assert_not_called()
        backend.key_up.assert_not_called()
        backend.sync_latched_key.assert_not_called()

    def test_service_emits_key_latch_changed_on_latch_toggle(self) -> None:
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        spec = KeySpec(label="Shift", row=0, column=0, key_id="shift", io_key="leftshift", latchable=True)
        events: list[KeyboardLatchChangedArguments] = []

        def record(event: KeyboardLatchChangedArguments) -> MessageResult:
            events.append(event)
            return []

        context.dispatcher.add_event_handler(KEYBOARD_LATCH_CHANGED, record)
        context.keyboard.register_key_spec(LAYOUT_ID, spec, component_id="key:shift")
        context.dispatcher.dispatch_action(keyboard_sync_latched_key(LAYOUT_ID, "key:shift", True))

        self.assertEqual(events, [KeyboardLatchChangedArguments(layout_id=LAYOUT_ID, key_id="shift", latched=True)])
        self.assertTrue(context.state.get(keyboard_latches_namespace(LAYOUT_ID), "shift"))

    def test_non_held_latch_does_not_emit_backend_pressed_state(self) -> None:
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        spec = KeySpec(label="Caps", row=0, column=0, key_id="caps", io_key="capslock", latchable=True)
        events: list[KeyboardKeyStateChangedArguments] = []

        def record(event: KeyboardKeyStateChangedArguments) -> MessageResult:
            events.append(event)
            return []

        context.dispatcher.add_event_handler(KEYBOARD_KEY_STATE_CHANGED, record)
        context.keyboard.register_key_spec(LAYOUT_ID, spec, component_id="key:caps")
        context.dispatcher.dispatch_action(keyboard_sync_latched_key(LAYOUT_ID, "key:caps", True))

        self.assertEqual(events, [])
        self.assertTrue(context.state.get(keyboard_latches_namespace(LAYOUT_ID), "caps"))

    def test_held_latch_uses_one_backend_press_until_unlatched(self) -> None:
        _app()
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        widget = KeyboardWidget(layout_config=build_us_iso_layout_config(), context=context)
        self.addCleanup(widget.close)
        button = self._button_for_key_id(widget, "shift")

        button.pressed.emit()
        button.released.emit()

        backend.key_down.assert_called_once()
        backend.key_up.assert_not_called()
        backend.sync_latched_key.assert_not_called()
        self.assertEqual(button.property("interactionState"), "latched")

        button.pressed.emit()
        button.released.emit()

        backend.key_down.assert_called_once()
        backend.key_up.assert_called_once_with(backend.key_down.return_value)
        self.assertEqual(button.property("interactionState"), "idle")

    def test_reset_state_releases_active_press_handles(self) -> None:
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        spec = KeySpec(label="Shift", row=0, column=0, key_id="shift", io_key="leftshift", holds_when_latched=True)

        context.keyboard.register_key_spec(LAYOUT_ID, spec, component_id="key:shift")
        context.dispatcher.dispatch_action(keyboard_key_down(LAYOUT_ID, "key:shift"))
        context.keyboard.reset_state()

        backend.key_up.assert_called_once_with(backend.key_down.return_value)

    def test_shared_latch_sibling_releases_original_backend_press(self) -> None:
        _app()
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        widget = KeyboardWidget(layout_config=build_us_iso_layout_config(), context=context)
        self.addCleanup(widget.close)
        left_shift = self._button_for_io_key(widget, "ShiftLeft")
        right_shift = self._button_for_io_key(widget, "ShiftRight")

        left_shift.pressed.emit()
        left_shift.released.emit()
        right_shift.pressed.emit()
        right_shift.released.emit()

        backend.key_down.assert_called_once()
        backend.key_up.assert_called_once_with(backend.key_down.return_value)
        self.assertEqual(left_shift.property("interactionState"), "idle")
        self.assertEqual(right_shift.property("interactionState"), "idle")

    def test_ctrl_shift_left_right_sequences_release_original_backend_presses(self) -> None:
        _app()

        for ctrl_name in ("CtrlLeft", "CtrlRight"):
            for shift_name in ("ShiftLeft", "ShiftRight"):
                with self.subTest(ctrl=ctrl_name, shift=shift_name):
                    backend = FakeKeyboardBackend()
                    handles: list[SimpleNamespace] = []
                    presses: list[tuple[str | None, dict[str, bool]]] = []

                    def key_down(spec: KeySpec, latched_keys: dict[str, bool]) -> SimpleNamespace:
                        handle = SimpleNamespace(key_name=spec.io_key)
                        handles.append(handle)
                        presses.append((spec.io_key, dict(latched_keys)))
                        return handle

                    backend.key_down.side_effect = key_down
                    context = make_test_context(backend)
                    widget = KeyboardWidget(
                        layout_config=build_us_iso_layout_config(),
                        context=context,
                    )
                    shift = self._button_for_io_key(widget, shift_name)
                    opposite_shift = self._button_for_io_key(
                        widget,
                        "ShiftRight" if shift_name == "ShiftLeft" else "ShiftLeft",
                    )
                    ctrl = self._button_for_io_key(widget, ctrl_name)
                    shifted_letters = [
                        self._button_for_io_key(widget, key_name)
                        for key_name in ("B", "C", "D")
                    ]
                    final_letter = self._button_for_io_key(widget, "A")

                    ctrl.click()
                    shift.click()
                    ctrl.click()
                    for letter in shifted_letters:
                        letter.click()

                    opposite_shift.click()
                    final_letter.click()

                    self.assertEqual(
                        [handle.key_name for handle in handles],
                        [ctrl_name, shift_name, "B", "C", "D", "A"],
                    )
                    self.assertEqual(
                        [call.args[0].key_name for call in backend.key_up.call_args_list],
                        [ctrl_name, "B", "C", "D", shift_name, "A"],
                    )
                    for key_name, latched_keys in presses[2:5]:
                        self.assertIn(key_name, {"B", "C", "D"})
                        self.assertFalse(latched_keys["ctrl"])
                        self.assertTrue(latched_keys["shift"])
                    final_latched_keys = presses[-1][1]
                    self.assertFalse(final_latched_keys["ctrl"])
                    self.assertFalse(final_latched_keys["shift"])
                    self.assertFalse(ctrl.property("latched"))
                    self.assertFalse(shift.property("latched"))
                    self.assertFalse(opposite_shift.property("latched"))
                    widget.close()

    def test_key_down_without_backend_press_does_not_emit_pressed_state(self) -> None:
        backend = FakeKeyboardBackend()
        backend.key_down.return_value = None
        context = make_test_context(backend)
        spec = KeySpec(label="Caps", row=0, column=0, key_id="caps", io_key="capslock", latchable=True)
        events: list[KeyboardKeyStateChangedArguments] = []

        def record(event: KeyboardKeyStateChangedArguments) -> MessageResult:
            events.append(event)
            return []

        context.dispatcher.add_event_handler(KEYBOARD_KEY_STATE_CHANGED, record)
        context.keyboard.register_key_spec(LAYOUT_ID, spec, component_id="key:caps")
        context.dispatcher.dispatch_action(keyboard_key_down(LAYOUT_ID, "key:caps"))

        self.assertEqual(events, [])
        self.assertEqual(
            context.state.get(keyboard_key_states_namespace(LAYOUT_ID), "capslock"),
            {"pressed": False, "latched": False},
        )

    def test_shared_latch_keys_keep_distinct_backend_pressed_state(self) -> None:
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        left_shift = KeySpec(label="Shift", row=0, column=0, key_id="shift", io_key="leftshift", latchable=True)
        right_shift = KeySpec(label="Shift", row=0, column=1, key_id="shift", io_key="rightshift", latchable=True)

        context.keyboard.register_key_spec(LAYOUT_ID, left_shift)
        context.keyboard.register_key_spec(LAYOUT_ID, right_shift)
        backend.emit_key_state("rightshift", True)

        self.assertEqual(
            context.state.get(keyboard_key_states_namespace(LAYOUT_ID), "leftshift"),
            {"pressed": False, "latched": False},
        )
        self.assertEqual(
            context.state.get(keyboard_key_states_namespace(LAYOUT_ID), "rightshift"),
            {"pressed": True, "latched": False},
        )

    def test_service_reset_state_clears_latches_for_registered_layout(self) -> None:
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        spec = KeySpec(label="Shift", row=0, column=0, key_id="shift", io_key="leftshift", latchable=True)

        context.keyboard.register_key_spec(LAYOUT_ID, spec, component_id="key:shift")
        context.dispatcher.dispatch_action(keyboard_sync_latched_key(LAYOUT_ID, "key:shift", True))
        context.keyboard.reset_state()

        self.assertIsNone(context.state.get(keyboard_latches_namespace(LAYOUT_ID), "shift"))
        self.assertFalse(context.keyboard.is_latched(LAYOUT_ID, "shift"))

    def test_widget_renders_latched_style_from_snapshot(self) -> None:
        _app()
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        context.state.set(keyboard_latches_namespace(LAYOUT_ID), "shift", True)

        widget = KeyboardWidget(layout_config=build_us_iso_layout_config(), context=context)
        self.addCleanup(widget.close)

        button = self._button_for_key_id(widget, "shift")
        self.assertTrue(button.property("latched"))
        self.assertIn(button.property("interactionState"), {"latched", "latched_pressed"})

    def _button_for_io_key(self, widget: KeyboardWidget, io_key_name: str) -> QPushButton:
        for button in widget.findChildren(QPushButton):
            if button.property("ioKeyName") == io_key_name:
                return button
        raise AssertionError(f"button for {io_key_name!r} was not found")

    def _button_for_key_id(self, widget: KeyboardWidget, key_id: str) -> QPushButton:
        for button in widget.findChildren(QPushButton):
            if button.property("keyId") == key_id:
                return button
        raise AssertionError(f"button for {key_id!r} was not found")


if __name__ == "__main__":
    unittest.main()
