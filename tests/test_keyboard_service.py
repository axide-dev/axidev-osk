from __future__ import annotations

import threading
import unittest

from axidev_osk.messages import DataMap, MessageResult
from axidev_osk.runtime.engine_messages import (
    INPUT_KEY,
    KEYBOARD_PERMISSION_REQUIRED,
    KEYBOARD_RESET,
    KEYBOARD_STATUS_CHANGED,
)
from axidev_osk.runtime.testing import make_keyboard_test_context
from axidev_osk.services.keyboard.io import KeyObservation, KeyPressHandle
from support import RecordingBackend


def _upper_letters(key: str) -> str:
    return key.upper() if len(key) == 1 else key


class RefusingKeyboardBackend(RecordingBackend):
    def press(self, key: str, mods: tuple[str, ...], repeat: bool) -> KeyPressHandle:
        self.sent.append(("down", key, mods, repeat))
        raise RuntimeError("Keyboard output is not ready")


class FailingReleaseBackend(RecordingBackend):
    """Fails the first release, as a backend that lost its output would."""

    failures = 1

    def key_up(self, press: KeyPressHandle) -> None:
        if self.failures:
            self.failures -= 1
            raise RuntimeError("key_up failed")
        super().key_up(press)


class KeyboardServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = RecordingBackend(canonical=_upper_letters)
        self.context, self.service = make_keyboard_test_context(self.backend)
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

        self.assertEqual(self.backend.initialized, 1)
        self.assertEqual(len(self.backend.observers), 1)
        self.assertEqual(self.events, [])

    def test_press_and_release_send_canonical_key_with_explicit_mods_and_repeat(self) -> None:
        self.service.press("a", ("Shift",), False)
        self.service.release("a")

        self.assertEqual(
            self.backend.sent,
            [("down", "A", ("Shift",), False), ("up", "A")],
        )

    def test_releasing_an_unheld_key_does_nothing(self) -> None:
        self.service.release("a")
        self.service.press("a", (), True)
        self.service.release("a")
        self.service.release("a")

        self.assertEqual(self.backend.sent, [("down", "A", (), True), ("up", "A")])

    def test_pressing_a_held_key_again_releases_the_previous_press(self) -> None:
        self.service.press("a", (), True)
        self.service.press("A", ("Shift",), True)
        self.service.release("a")

        self.assertEqual(
            self.backend.sent,
            [
                ("down", "A", (), True),
                ("up", "A"),
                ("down", "A", ("Shift",), True),
                ("up", "A"),
            ],
        )

    def test_refused_press_holds_nothing(self) -> None:
        backend = RefusingKeyboardBackend(canonical=_upper_letters)
        service = make_keyboard_test_context(backend)[1]

        with self.assertRaisesRegex(RuntimeError, "not ready"):
            service.press("a", (), True)
        service.release("a")

        self.assertEqual(backend.sent, [("down", "A", (), True)])

    def test_a_key_whose_release_failed_stays_held_until_a_release_succeeds(self) -> None:
        backend = FailingReleaseBackend(canonical=_upper_letters)
        service = make_keyboard_test_context(backend)[1]
        service.press("a", (), True)

        with self.assertRaisesRegex(RuntimeError, "key_up failed"):
            service.release("a")
        service.reset_state()
        service.reset_state()

        self.assertEqual(backend.sent, [("down", "A", (), True), ("up", "A")])

    def test_tap_and_type_text_pass_through_to_the_backend(self) -> None:
        self.service.tap("Enter", ("Ctrl",))
        self.service.type_text("moo")

        self.assertEqual(self.backend.sent, [("tap", "Enter", ("Ctrl",)), ("type", "moo")])

    def test_reset_releases_held_keys_and_reports_reset(self) -> None:
        self.service.press("a", (), True)
        self.service.press("ShiftLeft", (), False)

        self.service.reset_state()
        self.service.release("a")

        self.assertEqual(self.backend.sent[2:], [("up", "A"), ("up", "ShiftLeft")])
        self.assertEqual(self._event_names(), [KEYBOARD_RESET])

    def test_shutdown_releases_held_keys_and_runs_once(self) -> None:
        self.service.press("a", (), True)

        self.service.shutdown()
        self.service.shutdown()

        self.assertEqual(self.backend.sent[1:], [("up", "A")])
        self.assertEqual(self.backend.shutdowns, 1)
        self.assertEqual(self._event_names(), [KEYBOARD_RESET])

    def test_initialize_after_shutdown_allows_another_shutdown(self) -> None:
        self.service.shutdown()
        self.service.initialize()
        self.service.shutdown()

        self.assertEqual(self.backend.shutdowns, 2)

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
