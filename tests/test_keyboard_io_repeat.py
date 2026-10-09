from __future__ import annotations

import unittest
from os import environ
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, call, patch

from axidev_osk.runtime.diagnostics import KEYBOARD_DEBUG_ENV
from axidev_osk.services.keyboard.io import AxidevIoKeyboardBackend, KeyObservation, KeyPressHandle


class FakeKeys:
    def parse(self, key_name: str) -> str:
        return key_name.casefold()

    def format(self, parsed_key: str) -> str:
        return {"a": "A", "shift_l": "ShiftLeft", "shiftleft": "ShiftLeft"}.get(parsed_key, parsed_key)


class FakeNativeListener:
    def __init__(self) -> None:
        self.callback = None
        self.stop = Mock()

    def start(self, callback):
        self.callback = callback
        return self.stop


class KeyboardIoRepeatTests(unittest.TestCase):
    def test_press_sends_the_repeat_flag(self) -> None:
        backend, sender = self._ready_backend()

        repeating = backend.press("A", (), True)
        single = backend.press("A", (), False)

        self.assertEqual(
            sender.key_down.call_args_list,
            [call("A", repeat=True), call("A", repeat=False)],
        )
        self.assertEqual(repeating, KeyPressHandle("A", None, True))
        self.assertEqual(single, KeyPressHandle("A", None, False))

    def test_press_joins_modifiers_and_key_up_repeats_them(self) -> None:
        backend, sender = self._ready_backend()

        press = backend.press("a", ("Shift", "Ctrl"), True)
        backend.key_up(press)

        sender.key_down.assert_called_once_with("A", mods="Shift+Ctrl", repeat=True)
        sender.key_up.assert_called_once_with("A", mods="Shift+Ctrl")

    def test_key_up_without_modifiers_sends_only_the_key(self) -> None:
        backend, sender = self._ready_backend()

        backend.key_up(backend.press("A", (), True))

        sender.key_up.assert_called_once_with("A")

    def test_unready_backend_sends_nothing(self) -> None:
        backend, sender = self._ready_backend()
        backend._ready = False

        self.assertIsNone(backend.press("A", (), True))
        backend.key_up(KeyPressHandle("A"))
        backend.tap("A", ())
        backend.type_text("moo")

        self.assertEqual(sender.method_calls, [])

    def test_tap_and_type_text_use_the_sender(self) -> None:
        backend, sender = self._ready_backend()

        backend.tap("a", ())
        backend.tap("a", ("Ctrl", "Alt"))
        backend.type_text("moo")

        self.assertEqual(
            sender.tap.call_args_list,
            [call("A"), call("A", mods=["Ctrl", "Alt"])],
        )
        sender.type_text.assert_called_once_with("moo")

    def test_canonical_key_uses_backend_spelling_and_falls_back_to_the_input(self) -> None:
        backend, _sender = self._ready_backend()

        self.assertEqual(backend.canonical_key("shift_L"), "ShiftLeft")
        self.assertEqual(backend.canonical_key("F13"), "f13")
        self.assertEqual(AxidevIoKeyboardBackend().canonical_key("a"), "a")

    def test_listener_events_become_key_observations(self) -> None:
        backend, fake_listener = self._initialized_backend()
        observations: list[KeyObservation] = []
        unsubscribe = backend.add_observation_listener(observations.append)

        fake_listener.callback(SimpleNamespace(key_name="A", text="a", modifiers=("Shift", "CapsLock"), pressed=True))
        fake_listener.callback(SimpleNamespace(key_name="CapsLock", text="", modifiers=[], pressed=False))
        fake_listener.callback(SimpleNamespace(key_name="", pressed=True))
        unsubscribe()
        fake_listener.callback(SimpleNamespace(key_name="B", pressed=True))

        self.assertEqual(
            observations,
            [
                KeyObservation("A", "a", ("Shift", "CapsLock"), True),
                KeyObservation("CapsLock", None, (), False),
            ],
        )

    def test_failing_observation_listener_does_not_block_the_next_one(self) -> None:
        backend, fake_listener = self._initialized_backend()
        observations: list[KeyObservation] = []
        backend.add_observation_listener(Mock(side_effect=RuntimeError("boom")))
        backend.add_observation_listener(observations.append)

        with self.assertLogs("axidev_osk.services.keyboard.io", level="ERROR"):
            fake_listener.callback(SimpleNamespace(key_name="A", pressed=True))

        self.assertEqual(observations, [KeyObservation("A", None, (), True)])

    def test_shutdown_stops_the_listener(self) -> None:
        backend, fake_listener = self._initialized_backend()

        backend.shutdown()

        fake_listener.stop.assert_called_once_with()
        self.assertFalse(backend.ready)

    def test_modifier_trace_records_transitions_without_typed_keys(self) -> None:
        backend, _sender = self._ready_backend()

        with patch.dict(environ, {KEYBOARD_DEBUG_ENV: "1"}, clear=False):
            with self.assertLogs("axidev_osk.services.keyboard.io", level="INFO") as logs:
                backend.key_up(backend.press("ShiftLeft", (), False))
                backend.key_up(backend.press("A", (), True))

        trace = "\n".join(logs.output)
        self.assertIn("keyboard modifier down: ShiftLeft", trace)
        self.assertIn("keyboard modifier up: ShiftLeft", trace)
        self.assertNotIn(": A ", trace)

    def _ready_backend(self) -> tuple[AxidevIoKeyboardBackend, Mock]:
        backend = AxidevIoKeyboardBackend()
        sender = Mock()
        backend._keyboard = SimpleNamespace(sender=sender, keys=FakeKeys())
        backend._ready = True
        return backend, sender

    def _initialized_backend(self) -> tuple[AxidevIoKeyboardBackend, FakeNativeListener]:
        backend = AxidevIoKeyboardBackend()
        fake_listener = FakeNativeListener()
        fake_keyboard = SimpleNamespace(
            initialize=Mock(),
            shutdown=Mock(),
            status=Mock(return_value=SimpleNamespace(backend_name="fake")),
            keys=FakeKeys(),
            listener=fake_listener,
            sender=Mock(),
        )
        fake_module = ModuleType("axidev_io")
        fake_module.keyboard = fake_keyboard  # type: ignore[attr-defined]
        with patch.dict("sys.modules", {"axidev_io": fake_module}):
            self.assertTrue(backend.initialize())
        self.assertIsNotNone(fake_listener.callback)
        return backend, fake_listener


if __name__ == "__main__":
    unittest.main()
