from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtWidgets import QApplication, QPushButton

from axidev_osk.components.grid.keyboard import KeyboardWidget
from axidev_osk.config.defaults.us_iso import build_us_iso_layout_config
from axidev_osk.models import KeySpec
from axidev_osk.runtime.events import BackendKeyStateChanged
from axidev_osk.runtime.testing import make_test_context


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
        context = make_test_context(backend)
        spec = KeySpec(label="A", row=0, column=0, io_key="A")
        events: list[BackendKeyStateChanged] = []
        context.dispatcher.add_event_handler(lambda event: events.append(event) if isinstance(event, BackendKeyStateChanged) else None)

        context.keyboard.register_key_spec("default", spec)
        backend.emit_key_state("A", True)

        self.assertEqual(events, [BackendKeyStateChanged(layout="default", key_id="A", pressed=True, latched=False)])

    def test_service_writes_keyboard_key_state_namespace(self) -> None:
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        spec = KeySpec(label="A", row=0, column=0, io_key="A")

        context.keyboard.register_key_spec("default", spec)
        backend.emit_key_state("A", True)

        self.assertEqual(
            context.state.get("keyboard.key_states:default", "A"),
            {"pressed": True, "latched": False},
        )

    def test_widget_renders_from_snapshot_without_backend_press(self) -> None:
        _app()
        backend = FakeKeyboardBackend()
        context = make_test_context(backend)
        context.state.set("keyboard.key_states:us-iso", "A", {"pressed": True, "latched": False})

        widget = KeyboardWidget(layout_config=build_us_iso_layout_config(), context=context)
        self.addCleanup(widget.close)

        button = self._button_for_io_key(widget, "A")
        self.assertEqual(button.property("interactionState"), "pressed")
        backend.key_down.assert_not_called()
        backend.key_up.assert_not_called()
        backend.sync_latched_key.assert_not_called()

    def _button_for_io_key(self, widget: KeyboardWidget, io_key_name: str) -> QPushButton:
        for button in widget.findChildren(QPushButton):
            if button.property("ioKeyName") == io_key_name:
                return button
        raise AssertionError(f"button for {io_key_name!r} was not found")


if __name__ == "__main__":
    unittest.main()
