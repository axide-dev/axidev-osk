from __future__ import annotations

import unittest
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from axidev_osk.config.profile import ConfigDecoder, ProfileConfig
from axidev_osk.config.reader import ConfigError, ConfigReader, Resolver
from axidev_osk.config.variables import Variable, VariableError, decode_state
from axidev_osk.function_registry import FunctionRegistry
from axidev_osk.messages import DataMap, MessageResult, RuntimeEvent
from axidev_osk.runtime.app_messages import register_app_events
from axidev_osk.runtime.dispatcher import ActionFailedArguments, Dispatcher
from axidev_osk.runtime.functions import CallbackContext, call_callback
from axidev_osk.runtime.profile_runtime import (
    CALLBACK_FAILED,
    STATE_CHANGED,
    BindingTracker,
    CallbackFailedArguments,
    ProfileRuntime,
    StateChangedArguments,
    register_profile_events,
    state_set,
)
from axidev_osk.runtime.state import ReadRecorder, StatePath, StateTree


@dataclass(frozen=True)
class FakeNodeKind:
    callbacks: Mapping[str, str] = field(default_factory=lambda: {"on_press": "probe.pressed"})
    has_children: bool = True
    widget_properties: frozenset[str] = frozenset()

    def decode_structure(self, reader: ConfigReader) -> object:
        return None

    def decode_options(self, reader: ConfigReader) -> object:
        return {
            "size": reader.integer("size", 1),
            "label": reader.optional_string("label"),
            "latched": reader.boolean("latched", False),
        }

    def decode_child_placement(self, reader: ConfigReader) -> object:
        return reader.integer("slot", 0)

    def check_options(self, reader: ConfigReader, options: object, children: tuple[str, ...]) -> None:
        return None


def var(var_type: object, default: object = None) -> dict[str, object]:
    return {"var": var_type} if default is None else {"var": var_type, "default": default}


def declared(state: Mapping[str, object]) -> dict[StatePath, Variable]:
    return decode_state(state, "test")


def tree(state: Mapping[str, object], owner: str = "profile") -> StateTree:
    result = StateTree()
    result.declare(declared(state), owner)
    return result


def reads(function: Callable[[object], object]) -> Callable[[Resolver], object]:
    """A decode that resolves one binding, as a node or window value does."""

    return lambda resolve: resolve(function, "test.value")


def _root(shared: dict[str, object] | None = None, **profile: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "windows": [
            {
                "id": "pad",
                "title": "Pad",
                "content": {"kind": "probe", "id": "root", "children": []},
            }
        ],
    }
    defaults.update(profile)
    root: dict[str, object] = {"active_profile": "tiny", "profiles": {"tiny": defaults}}
    if shared is not None:
        root["state"] = shared
    return root


def _with_spare_profile(spare: dict[str, object]) -> dict[str, object]:
    """The default root plus an inactive profile named ``spare``."""

    root = _root()
    return {**root, "profiles": {**root["profiles"], "spare": spare}}  # type: ignore[dict-item]


def _pad(content: dict[str, object], **window: object) -> list[dict[str, object]]:
    return [{"id": "pad", "title": "Pad", "content": content, **window}]


class StateTreeTests(unittest.TestCase):
    def test_variables_start_at_their_defaults_and_none_resets_them(self) -> None:
        state = tree({"cow": {"text": var("string", "moo"), "count": var("integer", 0)}})

        self.assertEqual(state.get(()), {"cow": {"text": "moo", "count": 0}})
        self.assertTrue(state.set(("cow", "count"), 2))
        self.assertFalse(state.set(("cow", "count"), 2))
        self.assertTrue(state.set(("cow", "count"), None))
        self.assertEqual(state.get(("cow", "count")), 0)

    def test_values_are_copied_in_and_out(self) -> None:
        state = tree({"names": var({"list": "string"})})
        names = ["a"]
        state.set(("names",), names)
        names.append("b")
        read = state.get(("names",))
        assert isinstance(read, list)
        read.append("c")

        self.assertEqual(state.get(("names",)), ["a"])

    def test_reading_or_writing_an_undeclared_path_fails(self) -> None:
        state = tree({"cow": var("string", "moo")})

        for path in (("missing",), ("cow", "deep")):
            with self.subTest(path), self.assertRaisesRegex(VariableError, "not declared|undeclared"):
                state.get(path)
            with self.subTest(path), self.assertRaisesRegex(VariableError, "not declared|undeclared"):
                state.set(path, "x")
        with self.assertRaises(VariableError):
            _ = state.view().missing

    def test_values_must_fit_their_declared_type(self) -> None:
        state = tree({"x": var("integer", 1), "ratio": var("number", 0.5)})

        with self.assertRaisesRegex(VariableError, "x must be a integer, got bool"):
            state.set(("x",), True)
        self.assertTrue(state.set(("ratio",), 1))
        self.assertEqual(state.get(("x",)), 1)

    def test_none_removes_map_entries_and_the_branches_they_emptied(self) -> None:
        state = tree({"held": var({"map": {"map": "string"}})})

        state.set(("held", "A", "shift"), "Shift")
        self.assertEqual(state.get(("held",)), {"A": {"shift": "Shift"}})
        self.assertTrue(state.set(("held", "A", "shift"), None))
        self.assertEqual(state.get(("held",)), {})
        self.assertIsNone(state.get(("held", "B")))
        self.assertFalse(state.set(("held", "B"), None))

    def test_creating_a_map_entry_counts_as_a_change_even_at_its_default(self) -> None:
        state = tree({"m": var({"map": {"record": {"f": var("boolean", False)}}})})

        self.assertTrue(state.set(("m", "x", "f"), False))
        self.assertEqual(state.get(("m",)), {"x": {"f": False}})
        self.assertFalse(state.set(("m", "x", "f"), False))

    def test_record_fields_reset_to_their_own_defaults(self) -> None:
        state = tree({"size": var({"record": {"width": var("integer", 10), "height": var("integer", 20)}})})

        state.set(("size",), {"width": 3, "height": 4})
        state.set(("size", "width"), None)
        self.assertEqual(state.get(("size",)), {"width": 10, "height": 4})
        with self.assertRaisesRegex(VariableError, "depth is not a field of the record size"):
            state.set(("size", "depth"), 1)
        with self.assertRaisesRegex(VariableError, "unknown fields: depth"):
            state.set(("size",), {"depth": 1})

    def test_overlapping_declarations_are_rejected(self) -> None:
        state = tree({"std": {"latched": var({"map": "boolean"})}})

        for clash in ({"std": var("string", "x")}, {"std": {"latched": {"shift": var("boolean", False)}}}):
            with self.subTest(clash), self.assertRaisesRegex(VariableError, "overlaps"):
                state.declare(declared(clash), "other")

    def test_undeclare_removes_only_that_owners_variables(self) -> None:
        state = tree({"std": {"a": var("integer", 1)}})
        state.declare(declared({"std": {"b": var("integer", 2)}}), "shared")

        state.undeclare("profile")

        self.assertEqual(state.get(()), {"std": {"b": 2}})

    def test_view_records_only_the_deepest_paths_read(self) -> None:
        state = tree(
            {
                "input": {"locks": {"capslock": var("boolean", True)}, "keys": var({"map": "boolean"})},
                "shift": var("boolean", False),
            }
        )
        recorder = ReadRecorder()
        view = state.view(recorder)

        upper = view.input.locks.capslock != view.shift
        absent_key = view.input.keys.A

        self.assertTrue(upper)
        self.assertIsNone(absent_key)
        self.assertEqual(
            recorder.paths,
            frozenset({("input", "locks", "capslock"), ("shift",), ("input", "keys", "A")}),
        )

    def test_view_keeps_a_whole_branch_read_after_reading_its_children(self) -> None:
        state = tree({"std": {"latched": var({"map": "boolean"}, {"shift": True})}})
        recorder = ReadRecorder()
        branch = state.view(recorder).std.latched

        names = [name for name in branch if branch[name]]  # type: ignore[union-attr]

        self.assertEqual(names, ["shift"])
        self.assertIn(("std", "latched"), recorder.paths)


class FunctionTests(unittest.TestCase):
    def test_registry_reuses_ids_for_the_same_function(self) -> None:
        registry = FunctionRegistry()

        def callback(ctx: CallbackContext, event: DataMap) -> None:
            del ctx, event

        self.assertEqual(registry.register(callback), registry.register(callback))
        self.assertNotEqual(registry.register(callback), registry.register(lambda ctx, event: None))

    def test_callback_receives_state_and_plain_event_and_returns_actions(self) -> None:
        registry = FunctionRegistry()
        state = tree({"cow": var("string", "moo")})
        seen: list[object] = []

        def callback(ctx: CallbackContext, event: DataMap) -> list[object]:
            seen.append((ctx.state.cow, event))
            return [{"action": "window.show", "arguments": {"window": "pad"}}]

        actions = call_callback(registry, registry.register(callback), state, {"node": "cow"})

        self.assertEqual(seen, [("moo", {"node": "cow"})])
        self.assertEqual([(action.action, action.arguments) for action in actions], [("window.show", {"window": "pad"})])

    def test_callback_must_return_action_maps(self) -> None:
        registry = FunctionRegistry()
        ref = registry.register(lambda ctx, event: ["window.show"])

        with self.assertRaises(TypeError):
            call_callback(registry, ref, StateTree(), {})


class ConfigDecoderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.functions = FunctionRegistry()
        dispatcher = Dispatcher()
        self.profile_runtime = ProfileRuntime(dispatcher, self.functions, StateTree())
        self.profile_runtime.declare_observed(declared({"input": {"keys": var({"map": "boolean"})}}))
        self.decoder = ConfigDecoder(
            node_kinds={"probe": FakeNodeKind()},
            attachment_kinds={},
            functions=self.functions,
            check_profile=lambda profile, path: None,
            load_state=self.profile_runtime.load_state,
        )

    def test_decodes_state_bindings_callbacks_children_and_on_table(self) -> None:
        def label(state: object) -> str:
            return "A" if state.shift else "a"  # type: ignore[attr-defined]

        def pressed(ctx: CallbackContext, event: DataMap) -> None:
            del ctx, event

        profile = self.decoder.decode_config(
            _root(
                {"opacity": var("number", 0.85)},
                state={"shift": var("boolean", False)},
                on={"hot_corner.triggered": pressed},
                windows=_pad(
                    {
                        "kind": "probe",
                        "id": "root",
                        "children": [
                            {"kind": "probe", "id": "a", "size": 3, "label": label, "on_press": pressed, "slot": 4}
                        ],
                    },
                    show_on_start=True,
                    opacity=lambda state: state.opacity,
                ),
            )
        ).active

        child = profile.window("pad").content.children[0]
        self.assertEqual(profile.state, declared({"shift": var("boolean", False)}))
        self.assertEqual(profile.shared, declared({"opacity": var("number", 0.85)}))
        self.assertEqual(child.values.initial.options, {"size": 3, "label": "a", "latched": False})
        self.assertEqual(profile.window("pad").values.initial.opacity, 0.85)
        self.assertEqual(child.callbacks, {"probe.pressed": self.functions.register(pressed)})
        self.assertEqual(child.placement, 4)
        self.assertIsNone(profile.window("pad").content.placement)
        self.assertEqual(tuple(profile.on), ("hot_corner.triggered",))

    def test_errors_name_the_config_path(self) -> None:
        cases = {
            "unknown keys: colour": {"kind": "probe", "id": "a", "colour": "red"},
            "unknown node kind 'nope'": {"kind": "nope", "id": "a"},
            r"children\[0\]\.latched must be a boolean": {"kind": "probe", "id": "a", "latched": "yes"},
            r"children\[0\]\.latched must be a boolean$": {"kind": "probe", "id": "a", "latched": lambda state: "yes"},
            r"children\[0\]\.id is fixed and cannot be a function": {"kind": "probe", "id": lambda state: "a"},
            r"children\[0\]\.label: VariableError: State path 'nothing' is not declared": {
                "kind": "probe", "id": "a", "label": lambda state: state.nothing,
            },
        }
        for message, node in cases.items():
            with self.subTest(message), self.assertRaisesRegex(ConfigError, message):
                self.decoder.decode_config(_root(windows=_pad({"kind": "probe", "id": "root", "children": [node]}))).active

    def test_state_declaration_errors_name_the_config_path(self) -> None:
        cases = {
            r"^config\.profiles\.tiny\.state\.a\.b\.default is required for a integer$": {"a": {"b": {"var": "integer"}}},
            r"^config\.profiles\.tiny\.state\.a\.default must be a finite number|must be a number": {
                "a": var("number", float("inf"))
            },
            r"^config\.profiles\.tiny\.state\.a must be a variable declaration": {"a": 1},
        }
        for message, state in cases.items():
            with self.subTest(message), self.assertRaisesRegex(ConfigError, message):
                self.decoder.decode_config(_root(state=state)).active

    def test_declarations_overlapping_engine_or_shared_state_are_rejected(self) -> None:
        cases = {
            "engine": _with_spare_profile({"windows": [], "state": {"input": {"keys": var("string", "x")}}}),
            "shared": _root({"mode": var("string", "a")}, state={"mode": var("string", "b")}),
        }
        for name, root in cases.items():
            with self.subTest(name), self.assertRaisesRegex(ConfigError, r"\.state: State variable .* overlaps"):
                self.decoder.decode_config(root).active

    def test_keys_set_to_none_count_as_absent(self) -> None:
        profile = self.decoder.decode_config(
            _root(
                theme=None,
                windows=_pad({"kind": "probe", "id": "root", "size": None, "label": None}, opacity=None),
            )
        ).active

        window = profile.window("pad")
        self.assertEqual((window.values.initial.opacity, window.content.values.initial.options), (1.0, {"size": 1, "label": None, "latched": False}))

    def test_inactive_profiles_are_validated_too(self) -> None:
        root = _with_spare_profile({"windows": [], "colour": "red"})

        with self.assertRaisesRegex(ConfigError, "config.profiles.spare has unknown keys: colour"):
            self.decoder.decode_config(root).active

    def test_nil_entries_are_skipped_and_only_lists_count_as_lists(self) -> None:
        profile = self.decoder.decode_config(
            _root(
                on={"hot_corner.triggered": None},
                windows=_pad({"kind": "probe", "id": "root", "children": [None]}),
            )
        ).active
        self.assertEqual((dict(profile.on), profile.window("pad").content.children), ({}, ()))

        with self.assertRaisesRegex(ConfigError, "children must be a list"):
            self.decoder.decode_config(_root(windows=_pad({"kind": "probe", "id": "root", "children": ()}))).active

    def test_duplicate_node_ids_fail(self) -> None:
        with self.assertRaisesRegex(ConfigError, "Duplicate IDs"):
            self.decoder.decode_config(
                _root(windows=_pad({
                    "kind": "probe", "id": "root",
                    "children": [{"kind": "probe", "id": "a"}, {"kind": "probe", "id": "a"}],
                }))
            ).active


class ProfileRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dispatcher = Dispatcher()
        register_app_events(self.dispatcher)
        register_profile_events(self.dispatcher)
        self.functions = FunctionRegistry()
        self.state = StateTree()
        self.profile_runtime = ProfileRuntime(self.dispatcher, self.functions, self.state)
        self.profile_runtime.declare_observed(declared({"input": {"keys": var({"map": "boolean"})}}))
        self.tracker = BindingTracker(self.dispatcher, self.functions, self.state)
        self.changes: list[tuple[str, ...]] = []
        self.failures: list[CallbackFailedArguments] = []
        self.failed_actions: list[ActionFailedArguments] = []
        self.dispatcher.add_event_handler(STATE_CHANGED, self._record_change)
        self.dispatcher.add_event_handler(CALLBACK_FAILED, self._record_failure)
        self.dispatcher.add_event_handler("action.failed", self._record_failed_action)

    def _record_change(self, event: StateChangedArguments) -> MessageResult:
        self.changes.append(event.path)
        return []

    def _record_failure(self, event: CallbackFailedArguments) -> MessageResult:
        self.failures.append(event)
        return []

    def _record_failed_action(self, event: ActionFailedArguments) -> MessageResult:
        self.failed_actions.append(event)
        return []

    def _decode(self, root: dict[str, object]) -> ProfileConfig:
        decoder = ConfigDecoder(
            node_kinds={"probe": FakeNodeKind()},
            attachment_kinds={},
            functions=self.functions,
            check_profile=self.profile_runtime.check,
            load_state=self.profile_runtime.load_state,
        )
        return decoder.decode_config(root).active

    def _start(self, shared: dict[str, object] | None = None, **profile: object) -> None:
        self.profile_runtime.start(self._decode(_root(shared, **profile)))

    def test_state_set_updates_declared_state_and_reports_the_path(self) -> None:
        self._start(state={"std": {"latched": var({"map": "boolean"})}})
        self.changes.clear()

        self.dispatcher.dispatch(state_set("std.latched.shift", True))
        self.dispatcher.dispatch(state_set("std.latched.shift", True))

        self.assertEqual(self.state.get(("std", "latched", "shift")), True)
        self.assertEqual(self.changes, [("std", "latched", "shift")])

    def test_state_set_rejects_undeclared_paths_and_wrong_types(self) -> None:
        self._start(state={"mode": var("string", "a")})
        self.changes.clear()

        self.dispatcher.dispatch(state_set("typo", "b"), state_set("mode", 3))

        self.assertEqual(self.state.get(("mode",)), "a")
        self.assertEqual(self.changes, [])
        self.assertEqual(
            [(failure.action, failure.exception_type) for failure in self.failed_actions],
            [("state.set", "VariableError"), ("state.set", "VariableError")],
        )

    def test_restarting_resets_profile_state_and_keeps_shared_and_observed_state(self) -> None:
        shared = {"opacity": var("number", 0.85)}
        self._start(shared, state={"mode": var("string", "a"), "gone": var("boolean", True)})
        self.profile_runtime.set_observed(("input", "keys", "A"), True)
        self.dispatcher.dispatch(state_set("opacity", 0.5), state_set("mode", "b"))
        applied: list[object] = []
        self.tracker.bind(reads(lambda state: state.mode), "node:a.label", lambda value, previous: applied.append(value), fallback=None)
        self.changes.clear()

        self._start(shared, state={"mode": var("string", "a")})

        self.assertEqual(self.state.get(()), {"input": {"keys": {"A": True}}, "opacity": 0.5, "mode": "a"})
        self.assertEqual(self.changes, [("gone",), ("mode",)])
        self.assertEqual(applied, ["b", "a"])

    def test_profiles_cannot_set_observed_state(self) -> None:
        self._start()

        self.dispatcher.dispatch(state_set("input.keys.A", True))

        self.assertIsNone(self.state.get(("input", "keys", "A")))
        self.assertEqual([failure.action for failure in self.failed_actions], ["state.set"])

    def test_on_callbacks_get_plain_events_and_their_actions_run(self) -> None:
        events: list[DataMap] = []

        def on_corner(ctx: CallbackContext, event: DataMap) -> list[object]:
            events.append(event)
            return [{"action": "state.set", "arguments": {"path": "corner", "value": event["corner"]}}]

        self._start(state={"corner": var("string", "")}, on={"hot_corner.triggered": on_corner})

        self.dispatcher.dispatch(RuntimeEvent("hot_corner.triggered", {"corner": "top_left"}))

        self.assertEqual(events, [{"corner": "top_left"}])
        self.assertEqual(self.state.get(("corner",)), "top_left")

    def test_failing_callback_reports_and_queue_continues(self) -> None:
        def broken(ctx: CallbackContext, event: DataMap) -> None:
            raise RuntimeError("boom")

        def fine(ctx: CallbackContext, event: DataMap) -> list[object]:
            return [{"action": "state.set", "arguments": {"path": "ok", "value": True}}]

        self._start(state={"ok": var("boolean", False)}, on={"hot_corner.triggered": [broken, fine]})

        self.dispatcher.dispatch(RuntimeEvent("hot_corner.triggered", {"corner": "top_left"}))

        self.assertEqual([failure.message for failure in self.failures], ["boom"])
        self.assertEqual(self.state.get(("ok",)), True)

    def test_unknown_on_event_fails_at_decode_even_when_inactive(self) -> None:
        root = _with_spare_profile({"windows": [], "on": {"nope.event": lambda ctx, event: None}})

        with self.assertRaisesRegex(ConfigError, r"config.profiles.spare.on handles unknown events: nope.event"):
            self._decode(root)

    def test_bindings_rerun_only_when_their_reads_change(self) -> None:
        self._start(state={"shift": var("boolean", False), "other": var("integer", 0)})
        calls: list[bool] = []
        applied: list[object] = []

        def legend(state: object) -> str:
            shift = state.shift  # type: ignore[attr-defined]
            calls.append(bool(shift))
            return "A" if shift else "a"

        self.tracker.bind(reads(legend), "node:a.label", lambda value, previous: applied.append(value), fallback=None)
        self.dispatcher.dispatch(state_set("other", 1))
        self.dispatcher.dispatch(state_set("shift", True))

        self.assertEqual(calls, [False, True])
        self.assertEqual(applied, ["a", "A"])

    def test_a_failing_first_binding_applies_the_fallback_and_reports(self) -> None:
        self._start(state={"mode": var("string", "")})
        applied: list[object] = []

        def upper_mode(state: object) -> str:
            if not state.mode:  # type: ignore[attr-defined]
                raise ValueError("no mode yet")
            return state.mode.upper()  # type: ignore[attr-defined]

        self.tracker.bind(reads(upper_mode), "node:a.label", lambda value, previous: applied.append(value), fallback="?")
        self.dispatcher.dispatch(state_set("mode", "abc"))

        self.assertEqual(applied, ["?", "ABC"])
        self.assertEqual([(failure.kind, failure.source) for failure in self.failures], [("binding", "node:a.label")])
        self.assertIsNotNone(self.failures[0].function)

    def test_invalid_values_keep_the_last_value_and_report_without_a_function(self) -> None:
        self._start(state={"size": var("integer", 1)})
        applied: list[object] = []

        def decode(resolve: Resolver) -> int:
            size = resolve(lambda state: state.size, "test.size")
            assert isinstance(size, int)
            if size < 0:
                raise ConfigError("test.size must be at least 0")
            return size

        self.tracker.bind(decode, "node:a", lambda value, previous: applied.append(value), fallback=0)
        self.dispatcher.dispatch(state_set("size", -1))
        self.dispatcher.dispatch(state_set("size", 2))

        self.assertEqual(applied, [1, 2])
        self.assertEqual([(failure.function, failure.message) for failure in self.failures], [(None, "test.size must be at least 0")])


    def test_apply_gets_the_values_it_applied_before(self) -> None:
        self._start(state={"mode": var("string", "a")})
        calls: list[tuple[object, object]] = []

        self.tracker.bind(reads(lambda state: state.mode), "node:a", lambda value, previous: calls.append((value, previous)), fallback=None)
        self.dispatcher.dispatch(state_set("mode", "b"))

        self.assertEqual(calls, [("a", None), ("b", "a")])

    def test_true_and_one_are_different_values(self) -> None:
        self._start(state={"flag": var("boolean", True)})
        applied: list[object] = []

        def decode(resolve: Resolver) -> object:
            return 1 if resolve(lambda state: state.flag, "test.flag") is False else True

        self.tracker.bind(decode, "node:a", lambda value, previous: applied.append(value), fallback=None)
        self.dispatcher.dispatch(state_set("flag", False))

        self.assertEqual(applied, [True, 1])

    def test_a_fallback_that_cannot_apply_raises_once_and_stays_unbound(self) -> None:
        self._start(state={"mode": var("string", "a")})
        applied: list[object] = []

        def apply(value: object, previous: object) -> None:
            raise ValueError(f"cannot apply {value}")

        with self.assertRaisesRegex(ValueError, "cannot apply fallback"), self.assertLogs(level="ERROR"):
            self.tracker.bind(reads(lambda state: state.mode), "node:a", apply, fallback="fallback")
        self.dispatcher.dispatch(state_set("mode", "b"))

        self.assertEqual((applied, self.failures), ([], []))

    def test_a_failure_handler_that_changes_state_reaches_the_new_binding(self) -> None:
        self._start(state={"mode": var("string", "")})
        applied: list[object] = []
        self.dispatcher.add_event_handler(CALLBACK_FAILED, lambda failure: [state_set("mode", "fixed")])

        def upper_mode(state: object) -> str:
            if not state.mode:  # type: ignore[attr-defined]
                raise ValueError("no mode yet")
            return state.mode.upper()  # type: ignore[attr-defined]

        with self.assertLogs(level="ERROR"):
            self.tracker.bind(reads(upper_mode), "node:a", lambda value, previous: applied.append(value), fallback="?")
            self.assertEqual(applied, ["?"])
            self.dispatcher.process_pending()

        self.assertEqual(applied, ["?", "FIXED"])


if __name__ == "__main__":
    unittest.main()
