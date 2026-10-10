from __future__ import annotations

import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QCoreApplication, QDeadlineTimer

from axidev_osk.config.profile import ConfigDecoder
from axidev_osk.messages import DataMap, MessageResult, RuntimeAction
from axidev_osk.python_defaults import osk
from axidev_osk.runtime.app_messages import window_close_requested
from axidev_osk.runtime.dispatcher import ACTION_FAILED, Dispatcher
from axidev_osk.runtime.engine import build_engine
from axidev_osk.runtime.engine_messages import (
    KEYBOARD_PERMISSION_REQUIRED,
    KEYBOARD_RESET,
    PROCESS_EXITED,
    ProcessExitedArguments,
    input_key,
    process_exited,
    window_state_changed,
)
from axidev_osk.runtime.functions import CallbackContext
from axidev_osk.services.keyboard.io import KeyObservation
from axidev_osk.services.keyboard.service import KeyboardService
from axidev_osk.services.process import ProcessService
from support import RecordingBackend


class Harness:
    def __init__(self, profile: dict[str, object] | None = None) -> None:
        self.dispatcher = Dispatcher()
        self.backend = RecordingBackend(canonical=lambda key: key.upper() if len(key) == 1 else key)
        self.keyboard = KeyboardService(self.backend)  # type: ignore[arg-type]
        self.spawned: list[tuple[tuple[str, ...], str, bool]] = []
        processes = SimpleNamespace(spawn=lambda argv, tag, detached: self.spawned.append((argv, tag, detached)))
        self.engine = build_engine(self.dispatcher, keyboard=self.keyboard, processes=processes)  # type: ignore[arg-type]
        self.context = SimpleNamespace(dispatcher=self.dispatcher)
        self.keyboard.bind_context(self.context)  # type: ignore[arg-type]
        decoder = ConfigDecoder(
            node_kinds={"probe": _ProbeKind()},
            attachment_kinds={},
            functions=self.engine.functions,
            check_profile=self.engine.profile.check,
        )
        root = {
            "active_profile": "p",
            "profiles": {
                "p": {
                    "windows": [{"id": "pad", "title": "Pad", "content": {"kind": "probe", "id": "root"}}],
                    **(profile or {}),
                }
            },
        }
        self.engine.profile.start(decoder.decode_root(root))

    def act(self, name: str, **arguments: object) -> None:
        self.dispatcher.dispatch(RuntimeAction(name, arguments))  # type: ignore[arg-type]

    def events(self, name: str) -> list[object]:
        seen: list[object] = []
        self.dispatcher.add_event_handler(name, lambda event: seen.append(event) or [])
        return seen


class _ProbeKind:
    properties: dict[str, object] = {}
    callbacks: dict[str, str] = {}
    has_children = False
    widget_properties: frozenset[str] = frozenset()

    def decode_options(self, reader: object) -> None:
        return None


class ObservationTests(unittest.TestCase):
    def test_key_observation_updates_state_before_profile_callbacks(self) -> None:
        seen: list[tuple[object, object, DataMap]] = []

        def on_key(ctx: CallbackContext, event: DataMap) -> None:
            seen.append((ctx.state.input.keys.A, ctx.state.input.locks.capslock, event))

        harness = Harness({"on": {"input.key": on_key}})

        harness.dispatcher.dispatch(input_key("A", "A", ("Shift", "CapsLock"), True))

        self.assertEqual(
            seen,
            [(True, True, {"key": "A", "text": "A", "modifiers": ["Shift", "CapsLock"], "pressed": True})],
        )
        self.assertIs(harness.engine.profile.state.get(("input", "locks", "numlock")), False)

    def test_listener_thread_observations_wait_for_the_owner_thread(self) -> None:
        harness = Harness()
        listener = harness.backend.observers[0]
        thread = threading.Thread(target=lambda: listener(KeyObservation("B", "b", (), True)))  # type: ignore[operator]
        thread.start()
        thread.join()

        self.assertIsNone(harness.engine.profile.state.get(("input", "keys", "B")))
        harness.dispatcher.process_pending()
        self.assertIs(harness.engine.profile.state.get(("input", "keys", "B")), True)

    def test_status_is_observed_and_permission_setup_is_requested(self) -> None:
        harness = Harness()
        requests = harness.events(KEYBOARD_PERMISSION_REQUIRED)
        harness.backend.ready = False
        harness.backend.needs_permission_setup = True
        harness.backend.permission_setup_text = "run setup"

        harness.keyboard.publish_status()

        self.assertEqual(
            harness.engine.profile.state.get(("keyboard",)),
            {
                "ready": False,
                "status": "ready",
                "needs_permission_setup": True,
                "permission_setup_text": "run setup",
            },
        )
        self.assertEqual(len(requests), 1)

    def test_window_state_is_observed(self) -> None:
        harness = Harness()

        harness.dispatcher.dispatch(
            window_state_changed(
                "pad",
                visible=True,
                minimized=False,
                opacity=0.01,
                configured_opacity=0.85,
                input_blocked=True,
            )
        )

        self.assertEqual(
            harness.engine.profile.state.get(("windows", "pad")),
            {"visible": True, "minimized": False, "opacity": 0.01, "configured_opacity": 0.85, "input_blocked": True},
        )


class KeyboardEffectTests(unittest.TestCase):
    def test_a_failing_key_action_is_reported_to_the_profile(self) -> None:
        harness = Harness()
        failures = harness.events(ACTION_FAILED)
        harness.backend.press = Mock(side_effect=RuntimeError("Keyboard output is not ready: permission denied"))  # type: ignore[method-assign]

        harness.act("keyboard.down", key="a")

        self.assertEqual(
            [(failure.action, failure.message) for failure in failures],  # type: ignore[attr-defined]
            [("keyboard.down", "Keyboard output is not ready: permission denied")],
        )

    def test_event_constructors_reject_bad_arguments_where_they_are_called(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            window_close_requested("")

    def test_down_up_tap_and_text_reach_the_backend(self) -> None:
        harness = Harness()

        harness.act("keyboard.down", key="a", mods=["Shift"])
        harness.act("keyboard.up", key="a")
        harness.act("keyboard.up", key="a")
        harness.act("keyboard.tap", key="F5", mods=["Ctrl"])
        harness.act("keyboard.type_text", text="moo")

        self.assertEqual(
            harness.backend.sent,
            [
                ("down", "A", ("Shift",), True),
                ("up", "A"),
                ("tap", "F5", ("Ctrl",)),
                ("type", "moo"),
            ],
        )

    def test_reset_releases_held_keys_and_reports_reset(self) -> None:
        harness = Harness()
        resets = harness.events(KEYBOARD_RESET)
        harness.act("keyboard.down", key="ShiftLeft", repeat=False)

        harness.keyboard.reset_state()
        harness.keyboard.reset_state()

        self.assertEqual(harness.backend.sent[-1], ("up", "ShiftLeft"))
        self.assertEqual(len(resets), 2)

    def test_profile_log_and_spawn_actions_reach_the_log_and_the_process_lane(self) -> None:
        def on_window_close(ctx: CallbackContext, event: DataMap) -> list[osk.Map]:
            del ctx, event
            return [
                osk.log.info("hello"),
                osk.log.warn("careful"),
                osk.log.error("broken"),
                osk.process.spawn(["cowsay", "moo"], "cow"),
                osk.process.spawn(["notify-send", "hi"], "note", detached=True),
            ]

        harness = Harness({"on": {"window.close_requested": on_window_close}})

        with self.assertLogs("axidev_osk.profile", level="INFO") as logs:
            harness.dispatcher.dispatch(window_close_requested("pad"))

        self.assertEqual([record.getMessage() for record in logs.records], ["hello", "careful", "broken"])
        self.assertEqual(
            harness.spawned,
            [(("cowsay", "moo"), "cow", False), (("notify-send", "hi"), "note", True)],
        )

    def test_a_program_that_ran_reports_no_error_key(self) -> None:
        self.assertNotIn("error", process_exited("probe", 0).arguments)
        self.assertEqual(process_exited("probe", -1, "missing").arguments["error"], "missing")


class ProcessServiceTests(unittest.TestCase):
    def _run(self, argv: tuple[str, ...]) -> list[ProcessExitedArguments]:
        app = QCoreApplication.instance() or QCoreApplication([])
        dispatcher = Dispatcher()
        service = ProcessService()
        build_engine(dispatcher, keyboard=SimpleNamespace(), processes=service)  # type: ignore[arg-type]
        exits: list[ProcessExitedArguments] = []

        def record(event: ProcessExitedArguments) -> MessageResult:
            exits.append(event)
            return []

        dispatcher.add_event_handler(PROCESS_EXITED, record)
        service.start(SimpleNamespace(dispatcher=dispatcher))  # type: ignore[arg-type]
        service.spawn(argv, "probe", False)
        deadline = QDeadlineTimer(10_000)
        while not exits and not deadline.hasExpired():
            app.processEvents()
        return exits

    def test_attached_program_reports_its_exit_code(self) -> None:
        exits = self._run((sys.executable, "-c", "raise SystemExit(3)"))

        self.assertEqual([(event.tag, event.code, event.error) for event in exits], [("probe", 3, None)])

    def test_missing_program_reports_a_start_failure(self) -> None:
        exits = self._run(("axidev-osk-no-such-program",))

        self.assertEqual(len(exits), 1)
        self.assertEqual((exits[0].tag, exits[0].code), ("probe", -1))
        self.assertIsNotNone(exits[0].error)


if __name__ == "__main__":
    unittest.main()
