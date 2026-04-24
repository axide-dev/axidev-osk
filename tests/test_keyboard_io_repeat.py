from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from axidev_osk.keyboard_io import AxidevIoKeyboardBackend
from axidev_osk.models import KeySpec


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

    def _ready_backend(self) -> tuple[AxidevIoKeyboardBackend, SimpleNamespace]:
        backend = AxidevIoKeyboardBackend()
        sender = SimpleNamespace(key_down=Mock(), key_up=Mock())
        backend._keyboard = SimpleNamespace(sender=sender)
        backend._ready = True
        return backend, sender


if __name__ == "__main__":
    unittest.main()
