from __future__ import annotations

import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QPushButton

from axidev_osk.components.button.key import create_key_button
from axidev_osk.components.grid.keyboard import KeyboardWidget
from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.runtime.behavior_models import KeyboardOutput
from axidev_osk.runtime.config_paths import surface_source_path
from axidev_osk.runtime.testing import make_test_context
from axidev_osk.services.keyboard.io import AxidevIoKeyboardBackend


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
    ready = True
    status_text = "ready"
    needs_permission_setup = False
    permission_setup_text = ""

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

    def key_name_for_output(self, output: KeyboardOutput) -> str:
        return output.output_key

    def state_tags_for_key(self, output_key: str) -> frozenset[str]:
        return {
            "ShiftLeft": frozenset({"shift"}),
            "ShiftRight": frozenset({"shift"}),
            "CapsLock": frozenset({"caps"}),
        }.get(output_key, frozenset())

    def key_down(
        self,
        output: KeyboardOutput,
        active_state_tags: frozenset[str],
    ) -> SimpleNamespace:
        del active_state_tags
        self.emit_key_state(output.output_key, True)
        return SimpleNamespace(key_name=output.output_key)

    def key_up(self, press_handle) -> None:
        if press_handle is not None:
            self.emit_key_state(press_handle.key_name, False)

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
        output = KeyboardOutput("A")
        events: list[tuple[str, bool]] = []

        with patch.dict("sys.modules", {"axidev_io": fake_module}):
            self.assertTrue(backend.initialize())

        backend.add_key_state_listener(
            lambda key_name, pressed: events.append((key_name, pressed))
        )

        press = backend.key_down(output, frozenset())
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

    def test_keyboard_widget_renders_initial_and_updated_backend_state(self) -> None:
        _app()
        backend = FakeWidgetKeyboardBackend(pressed_key_names={"A"})
        config = build_default_app_config()
        context = make_test_context(backend, config=config)
        window = config.windows[0]
        keyboard_config = window.surface.components[0]
        source = surface_source_path(config, window.id, window.surface.id).child(
            "component", keyboard_config.id
        )
        widget = KeyboardWidget(
            layout_config=keyboard_config.layout,
            context=context,
            source_path=source,
        )
        self.addCleanup(widget.close)
        a_config = next(
            component
            for component in keyboard_config.layout.grids[0].components
            if component.visual.label == "a"
        )
        button = self._button_for_component(widget, a_config.id)

        self.assertEqual(button.property("interactionState"), "pressed")

        backend.emit_key_state("A", False)
        QApplication.processEvents()
        self.assertEqual(button.property("interactionState"), "idle")

        backend.emit_key_state("A", True)
        QApplication.processEvents()
        self.assertEqual(button.property("interactionState"), "pressed")

    def test_keyboard_widget_renders_legends_from_layout_state_tags(self) -> None:
        _app()
        backend = FakeWidgetKeyboardBackend()
        config = build_default_app_config()
        context = make_test_context(backend, config=config)
        window = config.windows[0]
        keyboard_config = window.surface.components[0]
        source = surface_source_path(config, window.id, window.surface.id).child(
            "component", keyboard_config.id
        )
        widget = KeyboardWidget(
            layout_config=keyboard_config.layout,
            context=context,
            source_path=source,
        )
        self.addCleanup(widget.close)
        a_config = next(
            component
            for component in keyboard_config.layout.grids[0].components
            if component.visual.label == "a"
        )
        button = self._button_for_component(widget, a_config.id)
        self.assertEqual(button.text(), "a")

        backend.emit_key_state("ShiftLeft", True)
        QApplication.processEvents()
        self.assertEqual(button.text(), "A")

        backend.emit_key_state("ShiftLeft", False)
        QApplication.processEvents()
        self.assertEqual(button.text(), "a")

    def test_key_button_runs_release_callback_without_owning_state(self) -> None:
        _app()
        calls: list[str] = []
        button = create_key_button(
            "A",
            component_id="component:test-key",
            on_release=lambda: calls.append("released"),
        )
        self.addCleanup(button.close)

        button.pressed.emit()
        button.released.emit()

        self.assertEqual(button.property("interactionState"), "idle")
        self.assertEqual(calls, ["released"])

    def _button_for_component(self, widget: KeyboardWidget, component_id: str) -> QPushButton:
        for button in widget.findChildren(QPushButton):
            if button.property("componentId") == component_id:
                return button
        raise AssertionError(f"button for {component_id!r} was not found")


if __name__ == "__main__":
    unittest.main()
