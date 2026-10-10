from __future__ import annotations

import unittest
from collections.abc import Mapping
from dataclasses import dataclass, field

from axidev_osk.config.profile import ConfigDecoder, ProfileConfig, PropertySpec
from axidev_osk.config.reader import ConfigError, ConfigReader
from axidev_osk.function_registry import FunctionRef, FunctionRegistry
from axidev_osk.messages import DataMap, MessageResult, RuntimeEvent
from axidev_osk.runtime.app_messages import register_app_events
from axidev_osk.runtime.dispatcher import Dispatcher
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
from axidev_osk.runtime.state import ReadRecorder, StateTree


@dataclass(frozen=True)
class FakeNodeKind:
    properties: Mapping[str, PropertySpec] = field(
        default_factory=lambda: {"label": PropertySpec(str), "latched": PropertySpec(bool)}
    )
    callbacks: Mapping[str, str] = field(default_factory=lambda: {"on_press": "probe.pressed"})
    has_children: bool = True
    widget_properties: frozenset[str] = frozenset()

    def decode_options(self, reader: ConfigReader) -> object:
        return reader.integer("size", 1)

    def decode_child_placement(self, reader: ConfigReader) -> object:
        return reader.integer("slot", 0)


def _action(name: str, **arguments: object) -> dict[str, object]:
    return {"action": name, "arguments": arguments}


def _root(**profile: object) -> dict[str, object]:
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
    return {"active_profile": "tiny", "profiles": {"tiny": defaults}}


def _with_spare_profile(spare: dict[str, object]) -> dict[str, object]:
    """The default root plus an inactive profile named ``spare``."""

    root = _root()
    return {**root, "profiles": {**root["profiles"], "spare": spare}}  # type: ignore[dict-item]


class StateTreeTests(unittest.TestCase):
    def test_set_get_copy_and_nil_removal(self) -> None:
        tree = StateTree({"cow": {"text": "moo"}})
        value = tree.get(("cow",))
        assert isinstance(value, dict)
        value["text"] = "changed"

        self.assertEqual(tree.get(("cow", "text")), "moo")
        self.assertTrue(tree.set(("cow", "count"), 2))
        self.assertFalse(tree.set(("cow", "count"), 2))
        self.assertTrue(tree.set(("cow", "count"), None))
        self.assertIsNone(tree.get(("cow", "count")))
        self.assertIsNone(tree.get(("missing", "deep")))

    def test_true_and_one_are_different_values(self) -> None:
        tree = StateTree({"x": 1})

        self.assertTrue(tree.set(("x",), True))
        self.assertIs(tree.get(("x",)), True)

    def test_maps_drop_nil_and_removals_leave_no_empty_branches(self) -> None:
        tree = StateTree({"a": {"b": None, "c": 1}})

        self.assertEqual(list(tree.view().a), ["c"])  # type: ignore[arg-type]
        self.assertTrue(tree.set(("a", "c"), None))
        self.assertIsNone(tree.get(("a",)))
        tree.set(("empty",), {})
        self.assertTrue(bool(tree.view().empty))

    def test_removing_a_missing_path_leaves_the_tree_unchanged(self) -> None:
        tree = StateTree({"cow": "moo"})

        self.assertFalse(tree.set(("a", "b", "c"), None))
        self.assertEqual(tree.get(()), {"cow": "moo"})

    def test_view_records_only_the_deepest_paths_read(self) -> None:
        tree = StateTree({"input": {"locks": {"capslock": True}, "keys": {"A": False}}, "shift": False})
        recorder = ReadRecorder()
        view = tree.view(recorder)

        upper = view.input.locks.capslock != view.shift
        missing = view.nothing

        self.assertTrue(upper)
        self.assertIsNone(missing)
        self.assertEqual(
            recorder.paths,
            frozenset({("input", "locks", "capslock"), ("shift",), ("nothing",)}),
        )

    def test_view_keeps_a_whole_branch_read_after_reading_its_children(self) -> None:
        tree = StateTree({"std": {"latched": {"shift": True}}})
        recorder = ReadRecorder()
        branch = tree.view(recorder).std.latched

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
        tree = StateTree({"cow": "moo"})
        seen: list[object] = []

        def callback(ctx: CallbackContext, event: DataMap) -> list[object]:
            seen.append((ctx.state.cow, event))
            return [_action("window.show", window="pad")]

        actions = call_callback(registry, registry.register(callback), tree, {"node": "cow"})

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
        self.decoder = ConfigDecoder(
            node_kinds={"probe": FakeNodeKind()},
            attachment_kinds={},
            functions=self.functions,
            check_profile=lambda profile, path: None,
        )

    def test_decodes_bindings_callbacks_children_and_on_table(self) -> None:
        def label(state: object) -> str:
            return "x"

        def pressed(ctx: CallbackContext, event: DataMap) -> None:
            del ctx, event

        root = self.decoder.decode_root(
            _root(
                state={"shift": False},
                on={"hot_corner.triggered": pressed},
                windows=[
                    {
                        "id": "pad",
                        "title": "Pad",
                        "show_on_start": True,
                        "content": {
                            "kind": "probe",
                            "id": "root",
                            "children": [
                                {
                                    "kind": "probe",
                                    "id": "a",
                                    "size": 3,
                                    "label": label,
                                    "latched": True,
                                    "on_press": pressed,
                                    "slot": 4,
                                }
                            ],
                        },
                    }
                ],
            )
        )

        profile = root
        child = profile.window("pad").content.children[0]
        self.assertEqual(profile.state, {"shift": False})
        self.assertEqual(child.options, 3)
        self.assertIsInstance(child.bindings["label"], FunctionRef)
        self.assertIs(child.bindings["latched"], True)
        self.assertEqual(child.callbacks, {"probe.pressed": self.functions.register(pressed)})
        self.assertEqual(child.placement, 4)
        self.assertIsNone(profile.window("pad").content.placement)
        self.assertEqual(tuple(profile.on), ("hot_corner.triggered",))

    def test_errors_name_the_config_path(self) -> None:
        cases = {
            "unknown keys: colour": {"kind": "probe", "id": "a", "colour": "red"},
            "unknown node kind 'nope'": {"kind": "nope", "id": "a"},
            "wrong type": {"kind": "probe", "id": "a", "latched": "yes"},
        }
        for message, node in cases.items():
            with self.subTest(message), self.assertRaisesRegex(ConfigError, message):
                self.decoder.decode_root(
                    _root(windows=[{"id": "pad", "title": "Pad", "content": {
                        "kind": "probe", "id": "root", "children": [node],
                    }}])
                )

    def test_plain_data_errors_name_the_config_path(self) -> None:
        with self.assertRaisesRegex(
            ConfigError, r"^config\.profiles\.tiny\.state\.a\.b must contain only finite numbers$"
        ):
            self.decoder.decode_root(_root(state={"a": {"b": float("inf")}}))

    def test_keys_set_to_none_count_as_absent(self) -> None:
        root = self.decoder.decode_root(
            _root(
                theme=None,
                windows=[
                    {
                        "id": "pad",
                        "title": "Pad",
                        "opacity": None,
                        "content": {"kind": "probe", "id": "root", "size": None, "label": None},
                    }
                ],
            )
        )

        window = root.window("pad")
        self.assertEqual((window.opacity, window.content.options), (1.0, 1))
        self.assertNotIn("label", window.content.bindings)

    def test_inactive_profiles_are_validated_too(self) -> None:
        root = _with_spare_profile({"windows": [], "colour": "red"})

        with self.assertRaisesRegex(ConfigError, "config.profiles.spare has unknown keys: colour"):
            self.decoder.decode_root(root)

    def test_nil_entries_are_skipped_and_only_lists_count_as_lists(self) -> None:
        profile = self.decoder.decode_root(
            _root(
                on={"hot_corner.triggered": None},
                windows=[{"id": "pad", "title": "Pad", "content": {"kind": "probe", "id": "root", "children": [None]}}],
            )
        )
        self.assertEqual((dict(profile.on), profile.window("pad").content.children), ({}, ()))

        with self.assertRaisesRegex(ConfigError, "children must be a list"):
            self.decoder.decode_root(
                _root(windows=[{"id": "pad", "title": "Pad", "content": {"kind": "probe", "id": "root", "children": ()}}])
            )

    def test_duplicate_node_ids_fail(self) -> None:
        with self.assertRaisesRegex(ConfigError, "Duplicate IDs"):
            self.decoder.decode_root(
                _root(windows=[{"id": "pad", "title": "Pad", "content": {
                    "kind": "probe", "id": "root",
                    "children": [{"kind": "probe", "id": "a"}, {"kind": "probe", "id": "a"}],
                }}])
            )


class ProfileRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dispatcher = Dispatcher()
        register_app_events(self.dispatcher)
        register_profile_events(self.dispatcher)
        self.functions = FunctionRegistry()
        self.state = StateTree()
        self.profile_runtime = ProfileRuntime(self.dispatcher, self.functions, self.state)
        self.tracker = BindingTracker(self.dispatcher, self.functions, self.state)
        self.changes: list[tuple[str, ...]] = []
        self.failures: list[CallbackFailedArguments] = []
        self.dispatcher.add_event_handler(STATE_CHANGED, self._record_change)
        self.dispatcher.add_event_handler(CALLBACK_FAILED, self._record_failure)

    def _record_change(self, event: StateChangedArguments) -> MessageResult:
        self.changes.append(event.path)
        return []

    def _record_failure(self, event: CallbackFailedArguments) -> MessageResult:
        self.failures.append(event)
        return []

    def _decode(self, root: dict[str, object]) -> ProfileConfig:
        decoder = ConfigDecoder(
            node_kinds={"probe": FakeNodeKind()},
            attachment_kinds={},
            functions=self.functions,
            check_profile=self.profile_runtime.check,
        )
        return decoder.decode_root(root)

    def _start(self, **profile: object) -> None:
        self.profile_runtime.start(self._decode(_root(**profile)))

    def test_state_set_updates_state_and_reports_the_path(self) -> None:
        self._start(state={"shift": False})
        self.changes.clear()

        self.dispatcher.dispatch(state_set("std.latched.shift", True))
        self.dispatcher.dispatch(state_set("std.latched.shift", True))

        self.assertEqual(self.state.get(("std", "latched", "shift")), True)
        self.assertEqual(self.changes, [("std", "latched", "shift")])

    def test_restarting_a_profile_reports_what_changed_so_bindings_rerun(self) -> None:
        self.profile_runtime.declare_root("input", {"keys": {"A": True}})
        self._start(state={"mode": "a", "same": 1, "gone": True})
        applied: list[object] = []
        self.tracker.bind(self.functions.register(lambda state: state.mode), "node:a.label", applied.append)
        self.changes.clear()

        self._start(state={"mode": "b", "same": 1})

        self.assertEqual(self.changes, [("gone",), ("mode",)])
        self.assertEqual(applied, ["a", "b"])
        self.assertEqual(self.state.get(("input", "keys", "A")), True)

    def test_profiles_cannot_define_runtime_roots_even_when_inactive(self) -> None:
        self.profile_runtime.declare_root("input", {"keys": {}})
        root = _with_spare_profile({"windows": [], "state": {"input": {}}})

        with self.assertRaisesRegex(ConfigError, r"config.profiles.spare.state cannot define runtime roots: input"):
            self._decode(root)

    def test_runtime_roots_set_to_none_count_as_absent(self) -> None:
        self.profile_runtime.declare_root("input", {"keys": {}})

        self._start(state={"input": None, "mode": {"a": None, "b": 1}})

        self.assertEqual(self.state.get(("mode",)), {"b": 1})
        self.assertEqual(self.state.get(("input",)), {"keys": {}})

    def test_profiles_cannot_set_runtime_state(self) -> None:
        self.profile_runtime.declare_root("input", {"keys": {}})
        self._start()
        failed: list[object] = []
        self.dispatcher.add_raw_event_handler("action.failed", lambda event: failed.append(event) or [])

        self.dispatcher.dispatch(state_set("input.keys.A", True))

        self.assertIsNone(self.state.get(("input", "keys", "A")))
        self.assertEqual(len(failed), 1)

    def test_on_callbacks_get_plain_events_and_their_actions_run(self) -> None:
        events: list[DataMap] = []

        def on_corner(ctx: CallbackContext, event: DataMap) -> list[object]:
            events.append(event)
            return [{"action": "state.set", "arguments": {"path": "corner", "value": event["corner"]}}]

        self._start(on={"hot_corner.triggered": on_corner})

        self.dispatcher.dispatch(RuntimeEvent("hot_corner.triggered", {"corner": "top_left"}))

        self.assertEqual(events, [{"corner": "top_left"}])
        self.assertEqual(self.state.get(("corner",)), "top_left")

    def test_failing_callback_reports_and_queue_continues(self) -> None:
        def broken(ctx: CallbackContext, event: DataMap) -> None:
            raise RuntimeError("boom")

        def fine(ctx: CallbackContext, event: DataMap) -> list[object]:
            return [{"action": "state.set", "arguments": {"path": "ok", "value": True}}]

        self._start(on={"hot_corner.triggered": [broken, fine]})

        self.dispatcher.dispatch(RuntimeEvent("hot_corner.triggered", {"corner": "top_left"}))

        self.assertEqual([failure.message for failure in self.failures], ["boom"])
        self.assertEqual(self.state.get(("ok",)), True)

    def test_unknown_on_event_fails_at_decode_even_when_inactive(self) -> None:
        root = _with_spare_profile({"windows": [], "on": {"nope.event": lambda ctx, event: None}})

        with self.assertRaisesRegex(ConfigError, r"config.profiles.spare.on handles unknown events: nope.event"):
            self._decode(root)

    def test_bindings_rerun_only_when_their_reads_change(self) -> None:
        self._start(state={"shift": False, "other": 0})
        calls: list[bool] = []
        applied: list[object] = []

        def legend(state: object) -> str:
            shift = state.shift  # type: ignore[attr-defined]
            calls.append(bool(shift))
            return "A" if shift else "a"

        self.tracker.bind(self.functions.register(legend), "node:a.label", applied.append)
        self.dispatcher.dispatch(state_set("other", 1))
        self.dispatcher.dispatch(state_set("shift", True))

        self.assertEqual(calls, [False, True])
        self.assertEqual(applied, ["a", "A"])

    def test_plain_values_apply_once_and_failing_bindings_report(self) -> None:
        self._start()
        applied: list[object] = []

        self.tracker.bind("Shift", "node:shift.label", applied.append)
        self.tracker.bind(self.functions.register(lambda state: 1 / 0), "node:a.label", applied.append)

        self.assertEqual(applied, ["Shift"])
        self.assertEqual([failure.kind for failure in self.failures], ["binding"])

    def test_failed_binding_reruns_when_the_state_it_read_appears(self) -> None:
        self._start()
        applied: list[object] = []

        def upper_mode(state: object) -> str:
            return state.mode.upper()  # type: ignore[attr-defined]

        self.tracker.bind(self.functions.register(upper_mode), "node:a.label", applied.append)
        self.dispatcher.dispatch(state_set("mode", "abc"))

        self.assertEqual(applied, ["ABC"])
        self.assertEqual(len(self.failures), 1)


if __name__ == "__main__":
    unittest.main()
