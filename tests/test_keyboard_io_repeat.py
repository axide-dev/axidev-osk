from __future__ import annotations

import unittest
from os import environ
from types import SimpleNamespace
from unittest.mock import Mock, patch

from axidev_osk.models import KeySpec
from axidev_osk.runtime.diagnostics import KEYBOARD_DEBUG_ENV
from axidev_osk.services.keyboard.io import AxidevIoKeyboardBackend


class KeyboardIoRepeatTests(unittest.TestCase):
    def test_key_down_sends_repeat_by_default(self) -> None:
        backend, sender = self._ready_backend()

        backend.key_down(KeySpec("A", row=0, column=0, io_key="A"), {})

        sender.key_down.assert_called_once_with("A", repeat=True)

    def test_key_down_can_disable_repeat_from_key_spec(self) -> None:
        backend, sender = self._ready_backend()

        backend.key_down(KeySpec("A", row=0, column=0, io_key="A", repeats=False), {})

        sender.key_down.assert_called_once_with("A", repeat=False)

    def test_key_down_preserves_repeat_flag_with_modifiers(self) -> None:
        backend, sender = self._ready_backend()

        backend.key_down(KeySpec("a", row=0, column=0, io_key="A"), {"shift": True})

        sender.key_down.assert_called_once_with("A", mods="Shift", repeat=True)

    def test_modifier_trace_records_transitions_without_typed_keys(self) -> None:
        backend, _sender = self._ready_backend()
        shift = KeySpec(
            "Shift",
            row=0,
            column=0,
            key_id="shift",
            io_key="ShiftLeft",
            latchable=True,
            holds_when_latched=True,
            repeats=False,
        )

        with patch.dict(environ, {KEYBOARD_DEBUG_ENV: "1"}, clear=False):
            with self.assertLogs("axidev_osk.services.keyboard.io", level="INFO") as logs:
                press = backend.key_down(shift, {})
                backend.key_up(press)

        trace = "\n".join(logs.output)
        self.assertIn("keyboard modifier request-down", trace)
        self.assertIn("keyboard modifier request-up", trace)
        self.assertNotIn("key_name='A'", trace)

    def _ready_backend(self) -> tuple[AxidevIoKeyboardBackend, SimpleNamespace]:
        backend = AxidevIoKeyboardBackend()
        sender = SimpleNamespace(key_down=Mock(), key_up=Mock())
        backend._keyboard = SimpleNamespace(sender=sender)
        backend._ready = True
        return backend, sender


if __name__ == "__main__":
    unittest.main()
