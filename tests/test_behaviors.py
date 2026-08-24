from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.config.models import BehaviorBinding, BehaviorConfig, BehaviorHook
from axidev_osk.messages import DataMap, MessageResult, RuntimeAction
from axidev_osk.runtime.behavior_models import HookDecision, HookOutcome, KeyboardOutput
from axidev_osk.runtime.behaviors import (
    KEYBOARD_KEY,
    BehaviorInteraction,
    BehaviorRegistry,
    action_behavior,
    action_hook,
    register_builtin_behaviors,
)
from axidev_osk.runtime.events import (
    BEHAVIOR_FAILED,
    COMPONENT_RELEASED,
    BehaviorFailedArguments,
    component_pressed,
    component_released,
)
from axidev_osk.runtime.source import SourcePath
from axidev_osk.runtime.testing import make_test_context


class FakeKeyboardBackend:
    ready = True
    status_text = "ready"
    needs_permission_setup = False
    permission_setup_text = ""

    def __init__(self) -> None:
        self.listeners = []
        self.pressed: set[str] = set()
        self.down_calls: list[tuple[str, frozenset[str]]] = []
        self.up_calls: list[str] = []

    def add_key_state_listener(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def key_name_for_output(self, output: KeyboardOutput) -> str:
        return output.output_key

    def state_tags_for_key(self, output_key: str) -> frozenset[str]:
        return {
            "ShiftLeft": frozenset({"shift"}),
            "ShiftRight": frozenset({"shift"}),
            "CapsLock": frozenset({"caps"}),
        }.get(output_key, frozenset())

    def is_key_down(self, key_name: str) -> bool:
        return key_name in self.pressed

    def key_down(
        self,
        output: KeyboardOutput,
        active_state_tags: frozenset[str],
    ) -> SimpleNamespace:
        self.down_calls.append((output.output_key, active_state_tags))
        self._emit(output.output_key, True)
        return SimpleNamespace(key_name=output.output_key)

    def key_up(self, handle) -> None:
        if handle is not None:
            self.up_calls.append(handle.key_name)
            self._emit(handle.key_name, False)

    def _emit(self, key_name: str, pressed: bool) -> None:
        if pressed:
            self.pressed.add(key_name)
        else:
            self.pressed.discard(key_name)
        for listener in tuple(self.listeners):
            listener(key_name, pressed)


def _keyboard_source(config, output_key: str) -> SourcePath:
    for binding in config.behaviors:
        if binding.default.kind != KEYBOARD_KEY:
            continue
        output = binding.default.arguments.get("output")
        if isinstance(output, dict) and output.get("output_key") == output_key:
            return binding.target
    raise AssertionError(f"No keyboard behavior emits {output_key!r}")


def _ghost_binding(config) -> BehaviorBinding:
    for binding in config.behaviors:
        for field in ("pressed_actions", "released_actions"):
            actions = binding.default.arguments.get(field)
            if isinstance(actions, list) and any(
                isinstance(action, dict) and action.get("action") == "window.toggle_opacity"
                for action in actions
            ):
                return binding
    raise AssertionError("Ghost behavior was not found")


def _replace_binding(config, replacement: BehaviorBinding):
    return replace(
        config,
        behaviors=tuple(
            replacement if binding.target == replacement.target else binding
            for binding in config.behaviors
        ),
    )


def _decode_record(arguments: DataMap) -> str:
    label = arguments.get("label")
    if not isinstance(label, str):
        raise TypeError("record label must be a string")
    return label


def _record_action(label: str) -> RuntimeAction:
    return RuntimeAction("test.record", {"label": label})


class KeyboardBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeKeyboardBackend()
        self.config = build_default_app_config()
        self.context = make_test_context(self.backend, config=self.config)

    def test_momentary_key_presses_and_releases_output(self) -> None:
        source = _keyboard_source(self.config, "A")

        self.context.dispatcher.dispatch_event(component_pressed(source))
        self.assertEqual(
            self.context.behaviors.state_snapshot(source),
            {"pressed": True, "latched": False},
        )
        self.context.dispatcher.dispatch_event(component_released(source))

        self.assertEqual(self.backend.down_calls, [("A", frozenset())])
        self.assertEqual(self.backend.up_calls, ["A"])
        self.assertEqual(
            self.context.behaviors.state_snapshot(source),
            {"pressed": False, "latched": False},
        )

    def test_logical_toggle_taps_output_and_toggles_latched_state(self) -> None:
        source = _keyboard_source(self.config, "CapsLock")

        self.context.dispatcher.dispatch_event(component_pressed(source))
        self.context.dispatcher.dispatch_event(component_released(source))

        self.assertEqual(self.backend.down_calls, [("CapsLock", frozenset())])
        self.assertEqual(self.backend.up_calls, ["CapsLock"])
        self.assertEqual(
            self.context.behaviors.state_snapshot(source),
            {"pressed": False, "latched": True},
        )

        self.context.dispatcher.dispatch_event(component_pressed(source))
        self.context.dispatcher.dispatch_event(component_released(source))
        self.assertEqual(
            self.context.behaviors.state_snapshot(source),
            {"pressed": False, "latched": False},
        )
        self.assertEqual(self.backend.up_calls, ["CapsLock", "CapsLock"])

    def test_held_toggle_keeps_output_down_until_second_release(self) -> None:
        source = _keyboard_source(self.config, "ShiftLeft")
        layout = source.through("layout")

        self.context.dispatcher.dispatch_event(component_pressed(source))
        self.context.dispatcher.dispatch_event(component_released(source))

        self.assertEqual(self.backend.down_calls, [("ShiftLeft", frozenset())])
        self.assertEqual(self.backend.up_calls, [])
        self.assertEqual(
            self.context.behaviors.state_snapshot(source),
            {"pressed": False, "latched": True},
        )
        self.assertEqual(self.context.behaviors.active_state_tags(layout), frozenset({"shift"}))

        self.context.dispatcher.dispatch_event(component_pressed(source))
        self.context.dispatcher.dispatch_event(component_released(source))

        self.assertEqual(self.backend.down_calls, [("ShiftLeft", frozenset())])
        self.assertEqual(self.backend.up_calls, ["ShiftLeft"])
        self.assertEqual(
            self.context.behaviors.state_snapshot(source),
            {"pressed": False, "latched": False},
        )
        self.assertEqual(self.context.behaviors.active_state_tags(layout), frozenset())

    def test_active_layout_tags_are_passed_to_following_output(self) -> None:
        shift = _keyboard_source(self.config, "ShiftLeft")
        letter = _keyboard_source(self.config, "A")
        self.context.dispatcher.dispatch_event(component_pressed(shift))
        self.context.dispatcher.dispatch_event(component_released(shift))

        self.context.dispatcher.dispatch_event(component_pressed(letter))

        self.assertEqual(self.backend.down_calls[-1], ("A", frozenset({"shift"})))

    def test_left_and_right_modifiers_keep_independent_latches(self) -> None:
        left = _keyboard_source(self.config, "ShiftLeft")
        right = _keyboard_source(self.config, "ShiftRight")
        layout = left.through("layout")
        for source in (left, right):
            self.context.dispatcher.dispatch_event(component_pressed(source))
            self.context.dispatcher.dispatch_event(component_released(source))

        self.assertTrue(self.context.behaviors.state_snapshot(left)["latched"])
        self.assertTrue(self.context.behaviors.state_snapshot(right)["latched"])

        self.context.dispatcher.dispatch_event(component_pressed(left))
        self.context.dispatcher.dispatch_event(component_released(left))

        self.assertFalse(self.context.behaviors.state_snapshot(left)["latched"])
        self.assertTrue(self.context.behaviors.state_snapshot(right)["latched"])
        self.assertEqual(self.context.behaviors.active_state_tags(layout), frozenset({"shift"}))


class BehaviorHookTests(unittest.TestCase):
    def _context_with_binding(
        self,
        binding: BehaviorBinding,
        *,
        registry: BehaviorRegistry | None = None,
    ):
        config = _replace_binding(build_default_app_config(), binding)
        context = make_test_context(
            FakeKeyboardBackend(),
            config=config,
            behavior_registry=registry,
        )
        calls: list[str] = []
        context.dispatcher.register_action(
            "test.record",
            _decode_record,
            lambda label: calls.append(label) or [],
        )
        return context, calls

    def test_all_before_hooks_run_and_last_control_decision_wins(self) -> None:
        original = _ghost_binding(build_default_app_config())
        binding = replace(
            original,
            default=action_behavior(released_actions=(_record_action("default"),)),
            before_hooks=(
                BehaviorHook(
                    frozenset({COMPONENT_RELEASED}),
                    True,
                    action_hook(
                        decision=HookDecision.CANCEL,
                        messages=(_record_action("before-1"),),
                    ),
                ),
                BehaviorHook(
                    frozenset({COMPONENT_RELEASED}),
                    True,
                    action_hook(
                        decision=HookDecision.REPLACE,
                        messages=(_record_action("before-2"),),
                        replacement=(_record_action("replacement"),),
                    ),
                ),
            ),
            after_hooks=(
                BehaviorHook(
                    frozenset({COMPONENT_RELEASED}),
                    False,
                    action_hook(messages=(_record_action("after"),)),
                ),
            ),
        )
        context, calls = self._context_with_binding(binding)

        context.dispatcher.dispatch_event(component_released(binding.target))

        self.assertEqual(calls, ["before-1", "before-2", "replacement", "after"])

    def test_failing_before_hook_blocks_default_but_later_hooks_run(self) -> None:
        registry = BehaviorRegistry()
        register_builtin_behaviors(registry)

        def fail_hook(
            decoded: object,
            interaction: BehaviorInteraction,
            owner: BehaviorRegistry,
        ) -> HookOutcome:
            del decoded, interaction, owner
            raise RuntimeError("before broke")

        registry.register_hook("test.fail", lambda arguments: arguments, fail_hook)
        original = _ghost_binding(build_default_app_config())
        binding = replace(
            original,
            default=action_behavior(released_actions=(_record_action("default"),)),
            before_hooks=(
                BehaviorHook(
                    frozenset({COMPONENT_RELEASED}),
                    True,
                    BehaviorConfig("test.fail", {}),
                ),
                BehaviorHook(
                    frozenset({COMPONENT_RELEASED}),
                    False,
                    action_hook(messages=(_record_action("later-before"),)),
                ),
            ),
        )
        context, calls = self._context_with_binding(binding, registry=registry)
        failures: list[BehaviorFailedArguments] = []
        context.dispatcher.add_event_handler(
            BEHAVIOR_FAILED,
            lambda event: failures.append(event) or [],
        )

        context.dispatcher.dispatch_event(component_released(binding.target))

        self.assertEqual(calls, ["later-before"])
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].phase, "before")
        self.assertEqual(failures[0].message, "before broke")

    def test_failing_after_hook_reports_failure_after_default_effect(self) -> None:
        registry = BehaviorRegistry()
        register_builtin_behaviors(registry)

        def fail_hook(
            decoded: object,
            interaction: BehaviorInteraction,
            owner: BehaviorRegistry,
        ) -> HookOutcome:
            del decoded, interaction, owner
            raise RuntimeError("after broke")

        registry.register_hook("test.fail", lambda arguments: arguments, fail_hook)
        original = _ghost_binding(build_default_app_config())
        binding = replace(
            original,
            default=action_behavior(released_actions=(_record_action("default"),)),
            after_hooks=(
                BehaviorHook(
                    frozenset({COMPONENT_RELEASED}),
                    False,
                    BehaviorConfig("test.fail", {}),
                ),
            ),
        )
        context, calls = self._context_with_binding(binding, registry=registry)
        failures: list[BehaviorFailedArguments] = []
        context.dispatcher.add_event_handler(
            BEHAVIOR_FAILED,
            lambda event: failures.append(event) or [],
        )

        context.dispatcher.dispatch_event(component_released(binding.target))

        self.assertEqual(calls, ["default"])
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].phase, "after")


class BehaviorValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = build_default_app_config()
        self.registry = BehaviorRegistry()
        register_builtin_behaviors(self.registry)

    def test_missing_interactive_binding_fails_eagerly(self) -> None:
        config = replace(self.config, behaviors=self.config.behaviors[1:])

        with self.assertRaisesRegex(ValueError, "Interactive controls lack behavior"):
            self.registry.load(config)

    def test_unresolved_binding_target_fails_eagerly(self) -> None:
        binding = self.config.behaviors[0]
        unresolved = replace(
            binding,
            target=binding.target.child("component", "missing"),
        )
        config = replace(
            self.config,
            behaviors=(unresolved, *self.config.behaviors[1:]),
        )

        with self.assertRaisesRegex(ValueError, "Behavior targets do not resolve"):
            self.registry.load(config)

    def test_unknown_behavior_kind_fails_eagerly(self) -> None:
        binding = self.config.behaviors[0]
        config = _replace_binding(
            self.config,
            replace(binding, default=BehaviorConfig("test.unknown", {})),
        )

        with self.assertRaisesRegex(ValueError, "Unknown behavior kind 'test.unknown'"):
            self.registry.load(config)

    def test_duplicate_binding_target_fails_at_root_config_boundary(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate config IDs in app behavior targets"):
            replace(
                self.config,
                behaviors=(*self.config.behaviors, self.config.behaviors[0]),
            )


if __name__ == "__main__":
    unittest.main()
