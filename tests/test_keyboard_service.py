from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtWidgets import QApplication, QPushButton

from axidev_osk.components.grid.keyboard import KeyboardWidget
from axidev_osk.config.defaults.us_iso import build_us_iso_layout_config
from axidev_osk.models import KeySpec
from axidev_osk.runtime.commands import KeyboardKeyDown, KeyboardKeyUp, KeyboardSyncLatchedKey
from axidev_osk.runtime.events import BackendKeyStateChanged, KeyLatchChanged
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
        self.permission_setup_script_path = None
        self._pressed_key_names = pressed_key_names or set()
        self._listeners = []
        self.key_down = Mock(return_value=SimpleNamespace(name="press"))
        self.key_up = Mock()
        self.sync_latched_key = Mock(return_value=None)

    def initialize(self) -> bool:
        return True

    def shutdown(self) -> None:
        return None

    def setup_permissions(self):
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
    def test_service_emits_backend_key_state_changed_on_backend_update(self) -> None:
        backend = FakeKeyboardBackend()
        context = make_test_context(backend, services={"keyboard"})
        spec = KeySpec(label="A", row=0, column=0, io_key="A")
        events: list[BackendKeyStateChanged] = []
        context.dispatcher.add_event_handler(lambda event: events.append(event) if isinstance(event, BackendKeyStateChanged) else None)

        context.keyboard.register_key_spec(LAYOUT_ID, spec)
        backend.emit_key_state("A", True)

        self.assertEqual(events, [BackendKeyStateChanged(layout_id=LAYOUT_ID, key_id="A", pressed=True, latched=False)])

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
        events: list[KeyLatchChanged] = []
        context.dispatcher.add_event_handler(lambda event: events.append(event) if isinstance(event, KeyLatchChanged) else None)

        context.dispatcher.dispatch_command(KeyboardSyncLatchedKey(LAYOUT_ID, spec, True))

        self.assertEqual(events, [KeyLatchChanged(layout_id=LAYOUT_ID, key_id="shift", latched=True)])
        self.assertTrue(context.state.get(keyboard_latches_namespace(LAYOUT_ID), "shift"))

    def test_non_held_latch_does_not_emit_backend_pressed_state(self) -> None:
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        spec = KeySpec(label="Caps", row=0, column=0, key_id="caps", io_key="capslock", latchable=True)
        events: list[BackendKeyStateChanged] = []
        context.dispatcher.add_event_handler(lambda event: events.append(event) if isinstance(event, BackendKeyStateChanged) else None)

        context.dispatcher.dispatch_command(KeyboardSyncLatchedKey(LAYOUT_ID, spec, True))

        self.assertEqual(events, [])
        self.assertTrue(context.state.get(keyboard_latches_namespace(LAYOUT_ID), "caps"))

    def test_held_latch_stays_backend_pressed_after_release(self) -> None:
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        spec = KeySpec(
            label="Shift",
            row=0,
            column=0,
            key_id="shift",
            io_key="leftshift",
            latchable=True,
            holds_when_latched=True,
        )
        events: list[BackendKeyStateChanged] = []
        context.dispatcher.add_event_handler(lambda event: events.append(event) if isinstance(event, BackendKeyStateChanged) else None)

        context.dispatcher.dispatch_command(KeyboardKeyDown(LAYOUT_ID, spec))
        context.dispatcher.dispatch_command(KeyboardSyncLatchedKey(LAYOUT_ID, spec, True))
        context.dispatcher.dispatch_command(KeyboardKeyUp(LAYOUT_ID, spec))

        self.assertEqual(events[-1], BackendKeyStateChanged(layout_id=LAYOUT_ID, key_id="leftshift", pressed=True, latched=True))
        backend.key_up.assert_not_called()

    def test_key_down_without_backend_press_does_not_emit_pressed_state(self) -> None:
        backend = FakeKeyboardBackend()
        backend.key_down.return_value = None
        context = make_test_context(backend)
        spec = KeySpec(label="Caps", row=0, column=0, key_id="caps", io_key="capslock", latchable=True)
        events: list[BackendKeyStateChanged] = []
        context.dispatcher.add_event_handler(lambda event: events.append(event) if isinstance(event, BackendKeyStateChanged) else None)

        context.dispatcher.dispatch_command(KeyboardKeyDown(LAYOUT_ID, spec))

        self.assertEqual(events, [])
        self.assertIsNone(context.state.get(keyboard_key_states_namespace(LAYOUT_ID), "capslock"))

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

        context.keyboard.register_key_spec(LAYOUT_ID, spec)
        context.dispatcher.dispatch_command(KeyboardSyncLatchedKey(LAYOUT_ID, spec, True))
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
