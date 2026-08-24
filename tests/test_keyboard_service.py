from __future__ import annotations

import unittest
from dataclasses import dataclass

from axidev_osk.messages import MessageResult
from axidev_osk.runtime.behavior_models import KeyboardOutput
from axidev_osk.runtime.events import (
    KEYBOARD_KEY_STATE_CHANGED,
    KeyboardKeyStateChangedArguments,
)
from axidev_osk.runtime.source import SourcePath, SourcePathSegment
from axidev_osk.runtime.testing import make_test_context


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
        self.listeners = []
        self.pressed: set[str] = set()
        self.down_calls: list[tuple[KeyboardOutput, frozenset[str]]] = []
        self.up_calls: list[object | None] = []

    def initialize(self) -> bool:
        self.initialize_calls += 1
        return True

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def add_key_state_listener(self, listener):
        self.listeners.append(listener)

        def unsubscribe() -> None:
            self.listeners.remove(listener)

        return unsubscribe

    def key_name_for_output(self, output: KeyboardOutput) -> str:
        return output.output_key.casefold()

    def state_tags_for_key(self, output_key: str) -> frozenset[str]:
        return {
            "shiftleft": frozenset({"shift"}),
            "capslock": frozenset({"caps"}),
        }.get(output_key.casefold(), frozenset())

    def is_key_down(self, key_name: str) -> bool:
        return key_name in self.pressed

    def key_down(
        self,
        output: KeyboardOutput,
        active_state_tags: frozenset[str],
    ) -> PressHandle:
        self.down_calls.append((output, active_state_tags))
        key_name = self.key_name_for_output(output)
        self.emit(key_name, True)
        return PressHandle(key_name)

    def key_up(self, handle: object | None) -> None:
        self.up_calls.append(handle)
        if isinstance(handle, PressHandle):
            self.emit(handle.key_name, False)

    def emit(self, key_name: str, pressed: bool) -> None:
        if pressed:
            self.pressed.add(key_name)
        else:
            self.pressed.discard(key_name)
        for listener in tuple(self.listeners):
            listener(key_name, pressed)


def _source(component_id: str) -> SourcePath:
    return SourcePath(
        (
            SourcePathSegment("app", "axidev-osk"),
            SourcePathSegment("profile", "default"),
            SourcePathSegment("window", "keyboard"),
            SourcePathSegment("surface", "keyboard"),
            SourcePathSegment("component", "keyboard-grid"),
            SourcePathSegment("layout", "us-iso"),
            SourcePathSegment("grid", "main"),
            SourcePathSegment("component", component_id),
        )
    )


class KeyboardServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeKeyboardBackend()
        self.context = make_test_context(
            self.backend,
            activate_behaviors=False,
        )
        self.service = self.context.keyboard
        self.events: list[KeyboardKeyStateChangedArguments] = []

        def record(event: KeyboardKeyStateChangedArguments) -> MessageResult:
            self.events.append(event)
            return []

        self.context.dispatcher.add_event_handler(KEYBOARD_KEY_STATE_CHANGED, record)

    def test_start_initializes_backend_and_listener_once(self) -> None:
        self.service.start(self.context)
        self.service.bind_context(self.context)

        self.assertEqual(self.backend.initialize_calls, 1)
        self.assertEqual(len(self.backend.listeners), 1)

    def test_register_output_returns_canonical_name_and_state_tags(self) -> None:
        source = _source("shift-left")

        metadata = self.service.register_output(
            source,
            KeyboardOutput("ShiftLeft", repeats=False),
        )

        self.assertEqual(metadata, ("shiftleft", frozenset({"shift"})))

    def test_register_output_publishes_existing_backend_state(self) -> None:
        source = _source("caps-lock")
        self.backend.pressed.add("capslock")

        self.service.register_output(source, KeyboardOutput("CapsLock"))

        self.assertEqual(
            self.events,
            [KeyboardKeyStateChangedArguments(source, True, frozenset({"caps"}))],
        )

    def test_backend_update_is_published_for_every_exact_registered_source(self) -> None:
        first = _source("shift-left-first")
        second = _source("shift-left-second")
        output = KeyboardOutput("ShiftLeft")
        self.service.register_output(first, output)
        self.service.register_output(second, output)

        self.backend.emit("shiftleft", True)

        self.assertEqual(
            self.events,
            [
                KeyboardKeyStateChangedArguments(first, True, frozenset({"shift"})),
                KeyboardKeyStateChangedArguments(second, True, frozenset({"shift"})),
            ],
        )

    def test_key_down_passes_runtime_state_tags_and_publishes_once(self) -> None:
        source = _source("a")
        output = KeyboardOutput("A")
        self.service.register_output(source, output)

        self.service.key_down(source, frozenset({"shift", "caps"}))

        self.assertEqual(
            self.backend.down_calls,
            [(output, frozenset({"shift", "caps"}))],
        )
        self.assertEqual(
            self.events,
            [KeyboardKeyStateChangedArguments(source, True, frozenset())],
        )

    def test_key_up_releases_matching_handle_and_publishes_once(self) -> None:
        source = _source("a")
        self.service.register_output(source, KeyboardOutput("A"))
        self.service.key_down(source, frozenset())
        self.events.clear()

        self.service.key_up(source)

        self.assertEqual(self.backend.up_calls, [PressHandle("a")])
        self.assertEqual(
            self.events,
            [KeyboardKeyStateChangedArguments(source, False, frozenset())],
        )

    def test_unregistered_output_fails_before_backend_call(self) -> None:
        with self.assertRaisesRegex(ValueError, "No keyboard output registered"):
            self.service.key_down(_source("missing"), frozenset())

        self.assertEqual(self.backend.down_calls, [])

    def test_reset_releases_active_handles_and_discards_outputs(self) -> None:
        source = _source("a")
        self.service.register_output(source, KeyboardOutput("A"))
        self.service.key_down(source, frozenset())

        self.service.reset_state()

        self.assertEqual(self.backend.up_calls, [PressHandle("a")])
        with self.assertRaisesRegex(ValueError, "No keyboard output registered"):
            self.service.key_down(source, frozenset())

    def test_shutdown_releases_active_handles_and_runs_once(self) -> None:
        source = _source("a")
        self.service.register_output(source, KeyboardOutput("A"))
        self.service.key_down(source, frozenset())

        self.service.shutdown()
        self.service.shutdown()

        self.assertEqual(self.backend.up_calls, [PressHandle("a")])
        self.assertEqual(self.backend.shutdown_calls, 1)


if __name__ == "__main__":
    unittest.main()
