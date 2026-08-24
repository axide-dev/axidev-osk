from __future__ import annotations

import math
import unittest

from axidev_osk.messages import DataMap, MessageResult, RuntimeAction, RuntimeEvent
from axidev_osk.runtime.actions import window_toggle_opacity
from axidev_osk.runtime.dispatcher import Dispatcher
from axidev_osk.runtime.events import ACTION_FAILED, ActionFailedArguments, register_builtin_events
from axidev_osk.runtime.state_store import StateStore


def _identity(arguments: DataMap) -> DataMap:
    return arguments


class RuntimeMessageTests(unittest.TestCase):
    def test_action_copies_nested_arguments(self) -> None:
        source = {"nested": {"items": ["first"]}}

        action = RuntimeAction("test.copy", source)
        source["nested"]["items"].append("changed")

        self.assertEqual(action.arguments, {"nested": {"items": ["first"]}})

    def test_messages_reject_non_native_data(self) -> None:
        with self.assertRaisesRegex(TypeError, "unsupported value tuple"):
            RuntimeAction("test.invalid", {"value": (1, 2)})  # type: ignore[dict-item]
        with self.assertRaisesRegex(TypeError, "keys must be strings"):
            RuntimeEvent("test.invalid", {1: "value"})  # type: ignore[dict-item]
        with self.assertRaisesRegex(ValueError, "finite numbers"):
            RuntimeAction("test.invalid", {"value": math.inf})

    def test_names_must_be_lowercase_and_namespaced(self) -> None:
        for name in ("invalid", "Invalid.name", "invalid-name.value"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "dot-separated"):
                RuntimeAction(name, {})

    def test_duplicate_registration_requires_explicit_override(self) -> None:
        dispatcher = Dispatcher()
        calls: list[str] = []

        def first(_arguments: DataMap) -> MessageResult:
            calls.append("first")
            return []

        def replacement(_arguments: DataMap) -> MessageResult:
            calls.append("replacement")
            return []

        dispatcher.register_action("test.override", _identity, first)
        with self.assertRaisesRegex(ValueError, "already registered"):
            dispatcher.register_action("test.override", _identity, replacement)
        dispatcher.register_action("test.override", _identity, replacement, override=True)

        dispatcher.dispatch_action(RuntimeAction("test.override", {}))

        self.assertEqual(calls, ["replacement"])

    def test_handler_results_keep_fifo_order(self) -> None:
        dispatcher = Dispatcher()
        order: list[str] = []
        dispatcher.register_event("test.first", _identity)
        dispatcher.register_event("test.second", _identity)

        def action_handler(_arguments: DataMap) -> MessageResult:
            order.append("action")
            return [RuntimeEvent("test.first", {}), RuntimeEvent("test.second", {})]

        def first_handler(_arguments: DataMap) -> MessageResult:
            order.append("first")
            return [RuntimeEvent("test.second", {"source": "first"})]

        def second_handler(arguments: DataMap) -> MessageResult:
            order.append(str(arguments.get("source", "second")))
            return []

        dispatcher.register_action("test.start", _identity, action_handler)
        dispatcher.add_event_handler("test.first", first_handler)
        dispatcher.add_event_handler("test.second", second_handler)

        dispatcher.dispatch_action(RuntimeAction("test.start", {}))

        self.assertEqual(order, ["action", "first", "second", "first"])

    def test_action_decode_failure_emits_arguments_and_continues(self) -> None:
        dispatcher = Dispatcher()
        register_builtin_events(dispatcher)
        failures: list[ActionFailedArguments] = []

        def decode(_arguments: DataMap) -> DataMap:
            raise ValueError("bad field")

        def unused(_arguments: DataMap) -> MessageResult:
            self.fail("invalid action reached its handler")

        def record_failure(arguments: ActionFailedArguments) -> MessageResult:
            failures.append(arguments)
            return []

        dispatcher.register_action("test.failure", decode, unused)
        dispatcher.add_event_handler(ACTION_FAILED, record_failure)

        dispatcher.dispatch_action(RuntimeAction("test.failure", {"secret": "included"}))

        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].action, "test.failure")
        self.assertEqual(failures[0].arguments, {"secret": "included"})
        self.assertEqual(failures[0].stage, "decode")
        self.assertEqual(failures[0].exception_type, "ValueError")
        self.assertEqual(failures[0].message, "bad field")

    def test_unknown_action_emits_action_failed(self) -> None:
        dispatcher = Dispatcher()
        register_builtin_events(dispatcher)
        failures: list[ActionFailedArguments] = []

        def record_failure(arguments: ActionFailedArguments) -> MessageResult:
            failures.append(arguments)
            return []

        dispatcher.add_event_handler(ACTION_FAILED, record_failure)

        dispatcher.dispatch_action(RuntimeAction("test.missing", {"value": 1}))

        self.assertEqual(failures[0].stage, "lookup")
        self.assertEqual(failures[0].arguments, {"value": 1})

    def test_action_handler_failure_emits_action_failed(self) -> None:
        dispatcher = Dispatcher()
        register_builtin_events(dispatcher)
        failures: list[ActionFailedArguments] = []

        def fail(_arguments: DataMap) -> MessageResult:
            raise RuntimeError("handler broke")

        def record_failure(arguments: ActionFailedArguments) -> MessageResult:
            failures.append(arguments)
            return []

        dispatcher.register_action("test.execute", _identity, fail)
        dispatcher.add_event_handler(ACTION_FAILED, record_failure)

        dispatcher.dispatch_action(RuntimeAction("test.execute", {"value": 2}))

        self.assertEqual(failures[0].stage, "execute")
        self.assertEqual(failures[0].arguments, {"value": 2})

    def test_invalid_handler_result_does_not_enqueue_partial_results(self) -> None:
        dispatcher = Dispatcher()
        register_builtin_events(dispatcher)
        handled: list[str] = []
        failures: list[ActionFailedArguments] = []

        def invalid_result(_arguments: DataMap) -> MessageResult:
            return [RuntimeEvent("test.followup", {}), object()]  # type: ignore[list-item]

        def record_followup(_arguments: DataMap) -> MessageResult:
            handled.append("followup")
            return []

        def record_failure(arguments: ActionFailedArguments) -> MessageResult:
            failures.append(arguments)
            return []

        dispatcher.register_event("test.followup", _identity)
        dispatcher.add_event_handler("test.followup", record_followup)
        dispatcher.add_event_handler(ACTION_FAILED, record_failure)
        dispatcher.register_action("test.partial", _identity, invalid_result)

        dispatcher.dispatch_action(RuntimeAction("test.partial", {}))

        self.assertEqual(handled, [])
        self.assertEqual(failures[0].stage, "execute")

    def test_builtin_constructor_validates_arguments_immediately(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            window_toggle_opacity("", "component:ghost", 0.01)
        with self.assertRaisesRegex(ValueError, "less than 1.0"):
            window_toggle_opacity("window:keyboard", "component:ghost", 1.0)

    def test_state_store_copies_values_on_write_and_read(self) -> None:
        state = StateStore()
        source = {"nested": [1]}

        state.set("test", "value", source)
        source["nested"].append(2)
        stored = state.get("test", "value")
        self.assertEqual(stored, {"nested": [1]})

        assert isinstance(stored, dict)
        stored["nested"].append(3)
        self.assertEqual(state.get("test", "value"), {"nested": [1]})

    def test_event_handler_failure_skips_remaining_handlers_but_continues_queue(self) -> None:
        dispatcher = Dispatcher()
        order: list[str] = []
        dispatcher.register_event("test.source", _identity)
        dispatcher.register_event("test.followup", _identity)

        def enqueue_followup(_arguments: DataMap) -> MessageResult:
            order.append("first")
            return [RuntimeEvent("test.followup", {})]

        def fail(_arguments: DataMap) -> MessageResult:
            raise RuntimeError("broken handler")

        def skipped(_arguments: DataMap) -> MessageResult:
            order.append("skipped")
            return []

        def followup(_arguments: DataMap) -> MessageResult:
            order.append("followup")
            return []

        dispatcher.add_event_handler("test.source", enqueue_followup)
        dispatcher.add_event_handler("test.source", fail)
        dispatcher.add_event_handler("test.source", skipped)
        dispatcher.add_event_handler("test.followup", followup)

        with self.assertLogs("axidev_osk.runtime.dispatcher", level="ERROR"):
            dispatcher.dispatch_event(RuntimeEvent("test.source", {}))

        self.assertEqual(order, ["first", "followup"])

    def test_unbounded_drain_warns_every_ten_thousand_messages_without_stopping(self) -> None:
        dispatcher = Dispatcher()
        handled = 0

        def repeat(_arguments: DataMap) -> MessageResult:
            nonlocal handled
            handled += 1
            if handled >= 20_001:
                return []
            return [RuntimeAction("test.repeat", {})]

        dispatcher.register_action("test.repeat", _identity, repeat)

        with self.assertLogs("axidev_osk.runtime.dispatcher", level="WARNING") as logs:
            dispatcher.dispatch_action(RuntimeAction("test.repeat", {}))

        self.assertEqual(handled, 20_001)
        self.assertEqual(len(logs.output), 2)
        self.assertIn("10000 messages", logs.output[0])
        self.assertIn("20000 messages", logs.output[1])


if __name__ == "__main__":
    unittest.main()
