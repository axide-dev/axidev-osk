from __future__ import annotations

import threading
import unittest
from dataclasses import dataclass

from axidev_osk.messages import DataMap, MessageResult
from axidev_osk.runtime.engine_messages import (
    INPUT_KEY,
    KEYBOARD_PERMISSION_REQUIRED,
    KEYBOARD_RESET,
    KEYBOARD_STATUS_CHANGED,
)
from axidev_osk.runtime.testing import make_test_context
from axidev_osk.services.keyboard.io import KeyObservation


@dataclass(frozen=True)
class PressHandle:
    key_name: str


class FakeKeyboardBackend:
    ready = True
    status_text = "ready"
    needs_permission_setup = False
    permission_setup_text = ""

    def __init__(self) -> None:
        self.initialize_calls = 0
        self.shutdown_calls = 0
        self.listeners: list[object] = []
        self.sent: list[tuple[object, ...]] = []

    def initialize(self) -> bool:
        self.initialize_calls += 1
        return True

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def add_observation_listener(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def canonical_key(self, key: str) -> str:
        return key.upper() if len(key) == 1 else key

    def press(self, key: str, mods: tuple[str, ...], repeat: bool) -> PressHandle:
        self.sent.append(("down", key, mods, repeat))
        return PressHandle(key)

    def key_up(self, handle: object | None) -> None:
        self.sent.append(("up", handle))

    def tap(self, key: str, mods: tuple[str, ...]) -> None:
        self.sent.append(("tap", key, mods))

    def type_text(self, text: str) -> None:
        self.sent.append(("text", text))

    def observe(self, observation: KeyObservation) -> None:
        for listener in tuple(self.listeners):
            listener(observation)  # type: ignore[operator]


class RefusingKeyboardBackend(FakeKeyboardBackend):
    def press(self, key: str, mods: tuple[str, ...], repeat: bool) -> object:
        self.sent.append(("down", key, mods, repeat))
        raise RuntimeError("Keyboard output is not ready")


class KeyboardServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeKeyboardBackend()
        self.context = make_test_context(self.backend)
        self.service = self.context.keyboard
        self.events: list[tuple[str, DataMap]] = []
        for name in (INPUT_KEY, KEYBOARD_RESET, KEYBOARD_STATUS_CHANGED, KEYBOARD_PERMISSION_REQUIRED):
            self.context.dispatcher.add_raw_event_handler(name, self._recorder(name))

    def _recorder(self, name: str):
        def record(arguments: DataMap) -> MessageResult:
            self.events.append((name, arguments))
            return []

        return record

    def _event_names(self) -> list[str]:
        return [name for name, _arguments in self.events]

    def test_start_initializes_backend_and_listener_once_without_publishing_status(self) -> None:
        self.service.start(self.context)
        self.service.bind_context(self.context)

        self.assertEqual(self.backend.initialize_calls, 1)
        self.assertEqual(len(self.backend.listeners), 1)
        self.assertEqual(self.events, [])

    def test_press_and_release_send_canonical_key_with_explicit_mods_and_repeat(self) -> None:
        self.service.press("a", ("Shift",), False)
        self.service.release("a")

        self.assertEqual(
            self.backend.sent,
            [("down", "A", ("Shift",), False), ("up", PressHandle("A"))],
        )

    def test_releasing_an_unheld_key_does_nothing(self) -> None:
        self.service.release("a")
        self.service.press("a", (), True)
        self.service.release("a")
        self.service.release("a")

        self.assertEqual(self.backend.sent, [("down", "A", (), True), ("up", PressHandle("A"))])

    def test_pressing_a_held_key_again_releases_the_previous_press(self) -> None:
        self.service.press("a", (), True)
        self.service.press("A", ("Shift",), True)
        self.service.release("a")

        self.assertEqual(
            self.backend.sent,
            [
                ("down", "A", (), True),
                ("up", PressHandle("A")),
                ("down", "A", ("Shift",), True),
                ("up", PressHandle("A")),
            ],
        )

    def test_refused_press_holds_nothing(self) -> None:
        backend = RefusingKeyboardBackend()
        service = make_test_context(backend).keyboard

        with self.assertRaisesRegex(RuntimeError, "not ready"):
            service.press("a", (), True)
        service.release("a")

        self.assertEqual(backend.sent, [("down", "A", (), True)])

    def test_tap_and_type_text_pass_through_to_the_backend(self) -> None:
        self.service.tap("Enter", ("Ctrl",))
        self.service.type_text("moo")

        self.assertEqual(self.backend.sent, [("tap", "Enter", ("Ctrl",)), ("text", "moo")])

    def test_reset_releases_held_keys_and_reports_reset(self) -> None:
        self.service.press("a", (), True)
        self.service.press("ShiftLeft", (), False)

        self.service.reset_state()
        self.service.release("a")

        self.assertEqual(self.backend.sent[2:], [("up", PressHandle("A")), ("up", PressHandle("ShiftLeft"))])
        self.assertEqual(self._event_names(), [KEYBOARD_RESET])

    def test_shutdown_releases_held_keys_and_runs_once(self) -> None:
        self.service.press("a", (), True)

        self.service.shutdown()
        self.service.shutdown()

        self.assertEqual(self.backend.sent[1:], [("up", PressHandle("A"))])
        self.assertEqual(self.backend.shutdown_calls, 1)
        self.assertEqual(self._event_names(), [KEYBOARD_RESET])

    def test_initialize_after_shutdown_allows_another_shutdown(self) -> None:
        self.service.shutdown()
        self.service.initialize()
        self.service.shutdown()

        self.assertEqual(self.backend.shutdown_calls, 2)

    def test_publish_status_reports_readiness(self) -> None:
        self.service.publish_status()

        self.assertEqual(
            self.events,
            [
                (
                    KEYBOARD_STATUS_CHANGED,
                    {"ready": True, "status": "ready", "needs_permission_setup": False, "permission_setup_text": ""},
                )
            ],
        )

    def test_publish_status_requests_permission_setup_when_needed(self) -> None:
        self.backend.ready = False
        self.backend.status_text = "blocked"
        self.backend.needs_permission_setup = True
        self.backend.permission_setup_text = "run setup"

        self.service.publish_status()

        self.assertEqual(self._event_names(), [KEYBOARD_STATUS_CHANGED, KEYBOARD_PERMISSION_REQUIRED])
        self.assertEqual(self.context.engine.profile.state.get(("keyboard", "ready")), False)

    def test_observations_are_forwarded_as_input_key_events(self) -> None:
        self.backend.observe(KeyObservation("A", "a", ("CapsLock",), True))

        self.assertEqual(
            self.events,
            [(INPUT_KEY, {"key": "A", "text": "a", "modifiers": ["CapsLock"], "pressed": True})],
        )

    def test_observations_from_another_thread_wait_for_the_owner_thread(self) -> None:
        listener = threading.Thread(
            target=self.backend.observe,
            args=(KeyObservation("B", None, (), False),),
        )
        listener.start()
        listener.join()

        self.assertEqual(self.events, [])
        self.context.dispatcher.process_pending()

        self.assertEqual(self._event_names(), [INPUT_KEY])
        self.assertEqual(self.events[0][1]["key"], "B")


if __name__ == "__main__":
    unittest.main()
