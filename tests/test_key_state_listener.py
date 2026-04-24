from __future__ import annotations

import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QPushButton

from axidev_osk.components.key_button import create_key_button
from axidev_osk.components.key_state_machine import KeyStateMachine
from axidev_osk.components.keyboard_widget import KeyboardWidget
from axidev_osk.keyboard_io import AxidevIoKeyboardBackend
from axidev_osk.models import KeySpec


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FakeKeys:
    def parse(self, key_name: str) -> str:
        return key_name

    def format(self, parsed_key: str) -> str:
        return parsed_key


class FakeNativeListener:
    def __init__(self) -> None:
        self.callback = None
        self.stop = Mock()

    def start(self, callback):
        self.callback = callback
        return self.stop


class FakeSender:
    def __init__(self) -> None:
        self.key_down = Mock()
        self.key_up = Mock()


class FakeWidgetKeyboardBackend:
    def __init__(self, pressed_key_names: set[str] | None = None) -> None:
        self._pressed_key_names = pressed_key_names or set()
        self._listeners = []

    def add_key_state_listener(self, listener):
        self._listeners.append(listener)

        def unsubscribe() -> None:
            self._listeners.remove(listener)

        return unsubscribe

    def is_key_down(self, key_name: str) -> bool:
        return key_name in self._pressed_key_names

    def key_name_for_spec(self, spec: KeySpec) -> str | None:
        return spec.io_key or (spec.label if len(spec.label) == 1 else None)

    def key_down(self, spec: KeySpec, latched_keys):
        return SimpleNamespace(spec=spec)

    def key_up(self, active_press) -> None:
        return None

    def sync_latched_key(self, spec: KeySpec, latched: bool, active_press=None):
        return active_press

    def emit_key_state(self, key_name: str, pressed: bool) -> None:
        if pressed:
            self._pressed_key_names.add(key_name)
        else:
            self._pressed_key_names.discard(key_name)

        for listener in tuple(self._listeners):
            listener(key_name, pressed)


class KeyStateListenerTests(unittest.TestCase):
    def test_backend_listener_updates_pressed_key_registry(self) -> None:
        backend = AxidevIoKeyboardBackend()
        fake_listener = FakeNativeListener()
        fake_keyboard = SimpleNamespace(
            initialize=Mock(),
            status=Mock(return_value=SimpleNamespace(backend_name="fake")),
            keys=FakeKeys(),
            listener=fake_listener,
        )
        fake_module = ModuleType("axidev_io")
        fake_module.keyboard = fake_keyboard
        events: list[tuple[str, bool]] = []

        with patch.dict("sys.modules", {"axidev_io": fake_module}):
            self.assertTrue(backend.initialize())

        self.assertIsNotNone(fake_listener.callback)
        backend.add_key_state_listener(
            lambda key_name, pressed: events.append((key_name, pressed))
        )

        fake_listener.callback(SimpleNamespace(key_name="A", pressed=True))
        self.assertTrue(backend.is_key_down("A"))
        self.assertEqual(events, [("A", True)])

        fake_listener.callback(SimpleNamespace(key_name="A", pressed=False))
        self.assertFalse(backend.is_key_down("A"))
        self.assertEqual(events, [("A", True), ("A", False)])

    def test_sent_key_updates_registry_immediately_before_listener_echo(self) -> None:
        backend = AxidevIoKeyboardBackend()
        fake_listener = FakeNativeListener()
        fake_sender = FakeSender()
        fake_keyboard = SimpleNamespace(
            initialize=Mock(),
            status=Mock(return_value=SimpleNamespace(backend_name="fake")),
            keys=FakeKeys(),
            listener=fake_listener,
            sender=fake_sender,
        )
        fake_module = ModuleType("axidev_io")
        fake_module.keyboard = fake_keyboard
        spec = KeySpec(label="A", row=0, column=0)
        events: list[tuple[str, bool]] = []

        with patch.dict("sys.modules", {"axidev_io": fake_module}):
            self.assertTrue(backend.initialize())

        backend.add_key_state_listener(
            lambda key_name, pressed: events.append((key_name, pressed))
        )

        press = backend.key_down(spec, {})
        self.assertIsNotNone(press)
        self.assertTrue(backend.is_key_down("A"))
        self.assertEqual(events, [("A", True)])

        fake_listener.callback(SimpleNamespace(key_name="A", pressed=True))
        self.assertEqual(events, [("A", True)])

        backend.key_up(press)
        self.assertFalse(backend.is_key_down("A"))
        self.assertEqual(events, [("A", True), ("A", False)])

        fake_listener.callback(SimpleNamespace(key_name="A", pressed=False))
        self.assertEqual(events, [("A", True), ("A", False)])

    def test_keyboard_widget_reflects_backend_key_state_for_sent_io_key(self) -> None:
        _app()
        backend = FakeWidgetKeyboardBackend(pressed_key_names={"A"})
        widget = KeyboardWidget(backend)
        self.addCleanup(widget.close)

        button = self._button_for_io_key(widget, "A")
        self.assertEqual(button.property("interactionState"), "pressed")

        backend.emit_key_state("A", False)
        QApplication.processEvents()
        self.assertEqual(button.property("interactionState"), "idle")

        backend.emit_key_state("A", True)
        QApplication.processEvents()
        self.assertEqual(button.property("interactionState"), "pressed")

    def test_key_button_runs_release_callback_immediately(self) -> None:
        _app()
        calls: list[str] = []
        state_machine = KeyStateMachine()
        button = create_key_button(
            "A",
            state_machine=state_machine,
            on_release=lambda: calls.append("released"),
        )
        self.addCleanup(button.close)

        button.pressed.emit()
        button.released.emit()

        self.assertEqual(button.property("interactionState"), "idle")
        self.assertEqual(calls, ["released"])

    def _button_for_io_key(self, widget: KeyboardWidget, io_key_name: str) -> QPushButton:
        for button in widget.findChildren(QPushButton):
            if button.property("ioKeyName") == io_key_name:
                return button
        raise AssertionError(f"button for {io_key_name!r} was not found")


if __name__ == "__main__":
    unittest.main()
