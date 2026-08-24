"""Runtime component behavior registration, validation, and routing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar, cast

from ..config.models import AppConfig, BehaviorBinding, BehaviorConfig, BehaviorHook
from ..messages import DataMap, DataValue, MessageResult, RuntimeAction, RuntimeMessage, runtime_action_to_data
from .actions import (
    keyboard_key_down,
    keyboard_key_up,
    keyboard_output_to_data,
    keyboard_register_output,
    state_replace,
    decode_keyboard_output,
)
from .behavior_models import (
    ActionBehavior,
    HookDecision,
    HookOutcome,
    KeyboardBehavior,
    KeyboardBehaviorMode,
    KeyboardOutput,
)
from .config_paths import iter_all_source_paths, iter_interactive_source_paths
from .decoding import map_value, require_keys, runtime_action_from_data, string_value
from .events import (
    COMPONENT_PRESSED,
    COMPONENT_RELEASED,
    KEYBOARD_KEY_STATE_CHANGED,
    KEYBOARD_OUTPUT_REGISTERED,
    ComponentPressedArguments,
    ComponentReleasedArguments,
    KeyboardKeyStateChangedArguments,
    KeyboardOutputRegisteredArguments,
    behavior_failed,
)
from .source import SourcePath, source_state_namespace

if TYPE_CHECKING:
    from .context import Context

COMPONENT_ACTIONS = "component.actions"
KEYBOARD_KEY = "keyboard.key"
BEHAVIOR_ACTIONS = "behavior.actions"

DecodedT = TypeVar("DecodedT")


@dataclass(frozen=True, slots=True)
class BehaviorInteraction:
    """Decoded component interaction plus its previous and proposed state."""

    event: str
    source: SourcePath
    previous_state: DataMap
    proposed_state: DataMap


BehaviorDecoder = Callable[[DataMap], object]
BehaviorHandler = Callable[[object, BehaviorInteraction, "BehaviorRegistry"], MessageResult]
HookHandler = Callable[[object, BehaviorInteraction, "BehaviorRegistry"], HookOutcome]


@dataclass(frozen=True, slots=True)
class _CompiledHook:
    config: BehaviorHook
    decoded: object
    handler: HookHandler


@dataclass(frozen=True, slots=True)
class _CompiledBinding:
    config: BehaviorBinding
    default_decoded: object
    default_handler: BehaviorHandler
    before_hooks: tuple[_CompiledHook, ...]
    after_hooks: tuple[_CompiledHook, ...]


class BehaviorRegistry:
    """Own registered behavior kinds and exact installed component bindings."""

    def __init__(self) -> None:
        self._behavior_kinds: dict[str, tuple[BehaviorDecoder, BehaviorHandler]] = {}
        self._hook_kinds: dict[str, tuple[BehaviorDecoder, HookHandler]] = {}
        self._bindings: dict[SourcePath, _CompiledBinding] = {}
        self._context: Context | None = None
        self._state_tags_by_source: dict[SourcePath, frozenset[str]] = {}

    def register_behavior(
        self,
        kind: str,
        decoder: Callable[[DataMap], DecodedT],
        handler: Callable[[DecodedT, BehaviorInteraction, "BehaviorRegistry"], MessageResult],
    ) -> None:
        if kind in self._behavior_kinds:
            raise ValueError(f"Behavior kind {kind!r} is already registered")
        self._behavior_kinds[kind] = (
            cast(BehaviorDecoder, decoder),
            cast(BehaviorHandler, handler),
        )

    def register_hook(
        self,
        kind: str,
        decoder: Callable[[DataMap], DecodedT],
        handler: Callable[[DecodedT, BehaviorInteraction, "BehaviorRegistry"], HookOutcome],
    ) -> None:
        if kind in self._hook_kinds:
            raise ValueError(f"Behavior hook kind {kind!r} is already registered")
        self._hook_kinds[kind] = (
            cast(BehaviorDecoder, decoder),
            cast(HookHandler, handler),
        )

    def load(self, config: AppConfig) -> None:
        """Validate and compile every root behavior binding."""

        all_paths = set(iter_all_source_paths(config))
        required_paths = set(iter_interactive_source_paths(config))
        targets = [binding.target for binding in config.behaviors]
        duplicate_targets = {target for target in targets if targets.count(target) > 1}
        if duplicate_targets:
            raise ValueError(f"Duplicate behavior targets: {_format_paths(duplicate_targets)}")

        target_set = set(targets)
        unresolved = target_set - all_paths
        missing = required_paths - target_set
        extra = target_set - required_paths
        if unresolved:
            raise ValueError(f"Behavior targets do not resolve: {_format_paths(unresolved)}")
        if missing:
            raise ValueError(f"Interactive controls lack behavior: {_format_paths(missing)}")
        if extra:
            raise ValueError(f"Behavior targets are not interactive controls: {_format_paths(extra)}")

        self._bindings = {
            binding.target: self._compile_binding(binding) for binding in config.behaviors
        }

    def bind_context(self, context: "Context") -> None:
        """Bind state/dispatcher ownership and install behavior event handlers."""

        self._context = context
        context.dispatcher.add_event_handler(COMPONENT_PRESSED, self._handle_pressed)
        context.dispatcher.add_event_handler(COMPONENT_RELEASED, self._handle_released)
        context.dispatcher.add_event_handler(
            KEYBOARD_OUTPUT_REGISTERED,
            self._handle_output_registered,
        )
        context.dispatcher.add_event_handler(
            KEYBOARD_KEY_STATE_CHANGED,
            self._handle_backend_state_changed,
        )

    def activate(self) -> None:
        """Register keyboard outputs and initialize complete component snapshots."""

        context = self._require_context()
        layout_paths: set[SourcePath] = set()
        keyboard_bindings: list[tuple[SourcePath, KeyboardBehavior]] = []
        for source, binding in self._bindings.items():
            state: DataMap = {"pressed": False}
            if isinstance(binding.default_decoded, KeyboardBehavior):
                state["latched"] = False
                layout_paths.add(source.through("layout"))
                keyboard_bindings.append((source, binding.default_decoded))
            context.dispatcher.dispatch_action(state_replace(source, state))
        for layout_path in sorted(layout_paths, key=repr):
            context.dispatcher.dispatch_action(
                state_replace(layout_path, {"state_tags": []})
            )
        for source, behavior in keyboard_bindings:
            context.dispatcher.dispatch_action(
                keyboard_register_output(source, behavior.output)
            )

    def state_snapshot(self, source: SourcePath) -> DataMap:
        value = self._require_context().state.get(source_state_namespace(source), "snapshot", {})
        return value if isinstance(value, dict) else {}

    def active_state_tags(self, layout_path: SourcePath) -> frozenset[str]:
        value = self.state_snapshot(layout_path).get("state_tags", [])
        if not isinstance(value, list):
            return frozenset()
        return frozenset(item for item in value if isinstance(item, str))

    def layout_state_action(
        self,
        source: SourcePath,
        override_state: DataMap,
    ) -> RuntimeAction:
        layout_path = source.through("layout")
        active_tags: set[str] = set()
        for candidate, binding in self._bindings.items():
            if not isinstance(binding.default_decoded, KeyboardBehavior):
                continue
            try:
                candidate_layout = candidate.through("layout")
            except ValueError:
                continue
            if candidate_layout != layout_path:
                continue
            state = override_state if candidate == source else self.state_snapshot(candidate)
            if bool(state.get("pressed", False)) or bool(state.get("latched", False)):
                active_tags.update(self._state_tags_by_source.get(candidate, frozenset()))
        state_tags: list[DataValue] = list(sorted(active_tags))
        return state_replace(layout_path, {"state_tags": state_tags})

    def _compile_binding(self, binding: BehaviorBinding) -> _CompiledBinding:
        default_registration = self._behavior_kinds.get(binding.default.kind)
        if default_registration is None:
            raise ValueError(f"Unknown behavior kind {binding.default.kind!r}")
        decoder, handler = default_registration
        default_decoded = decoder(binding.default.arguments)
        return _CompiledBinding(
            config=binding,
            default_decoded=default_decoded,
            default_handler=handler,
            before_hooks=tuple(self._compile_hook(hook) for hook in binding.before_hooks),
            after_hooks=tuple(self._compile_hook(hook) for hook in binding.after_hooks),
        )

    def _compile_hook(self, hook: BehaviorHook) -> _CompiledHook:
        registration = self._hook_kinds.get(hook.config.kind)
        if registration is None:
            raise ValueError(f"Unknown behavior hook kind {hook.config.kind!r}")
        decoder, handler = registration
        return _CompiledHook(config=hook, decoded=decoder(hook.config.arguments), handler=handler)

    def _handle_pressed(self, event: ComponentPressedArguments) -> MessageResult:
        return self._handle_interaction(COMPONENT_PRESSED, event.source)

    def _handle_released(self, event: ComponentReleasedArguments) -> MessageResult:
        return self._handle_interaction(COMPONENT_RELEASED, event.source)

    def _handle_interaction(self, event_name: str, source: SourcePath) -> MessageResult:
        binding = self._bindings.get(source)
        if binding is None:
            return [
                behavior_failed(
                    source,
                    "behavior.lookup",
                    "default",
                    "lookup",
                    "LookupError",
                    "No behavior binding is installed for this source",
                )
            ]

        previous = self.state_snapshot(source)
        proposed = dict(previous)
        proposed["pressed"] = event_name == COMPONENT_PRESSED
        interaction = BehaviorInteraction(event_name, source, previous, proposed)
        messages: MessageResult = [state_replace(source, proposed)]
        decision = HookDecision.CONTINUE
        replacement: tuple[RuntimeMessage, ...] = ()
        blocked = False

        for hook in binding.before_hooks:
            if event_name not in hook.config.events:
                continue
            try:
                outcome = hook.handler(hook.decoded, interaction, self)
                messages.extend(outcome.messages)
                if outcome.decision is not HookDecision.CONTINUE:
                    if not hook.config.blocking:
                        raise ValueError("A non-blocking before-hook cannot cancel or replace default behavior")
                    decision = outcome.decision
                    replacement = outcome.replacement
            except Exception as exc:
                blocked = True
                messages.append(self._failure(source, hook.config.config.kind, "before", exc))

        if not blocked:
            if decision is HookDecision.REPLACE:
                messages.extend(replacement)
            elif decision is HookDecision.CONTINUE:
                try:
                    messages.extend(
                        binding.default_handler(binding.default_decoded, interaction, self)
                    )
                except Exception as exc:
                    messages.append(
                        self._failure(source, binding.config.default.kind, "default", exc)
                    )

        for hook in binding.after_hooks:
            if event_name not in hook.config.events:
                continue
            try:
                outcome = hook.handler(hook.decoded, interaction, self)
                messages.extend(outcome.messages)
                if outcome.decision is not HookDecision.CONTINUE or outcome.replacement:
                    raise ValueError("After-hooks may extend behavior but cannot cancel or replace it")
            except Exception as exc:
                messages.append(self._failure(source, hook.config.config.kind, "after", exc))
        return messages

    def _handle_output_registered(
        self,
        event: KeyboardOutputRegisteredArguments,
    ) -> MessageResult:
        self._state_tags_by_source[event.source] = event.state_tags
        return []

    def _handle_backend_state_changed(
        self,
        event: KeyboardKeyStateChangedArguments,
    ) -> MessageResult:
        previous = self.state_snapshot(event.source)
        state = dict(previous)
        state["pressed"] = event.pressed
        self._state_tags_by_source[event.source] = event.state_tags
        return [
            state_replace(event.source, state),
            self.layout_state_action(event.source, state),
        ]

    def _failure(
        self,
        source: SourcePath,
        kind: str,
        phase: str,
        exc: Exception,
    ) -> RuntimeMessage:
        return behavior_failed(
            source,
            kind,
            phase,
            "handler",
            type(exc).__name__,
            str(exc),
        )

    def _require_context(self) -> "Context":
        if self._context is None:
            raise RuntimeError("Behavior registry is not bound to a runtime context")
        return self._context


def register_builtin_behaviors(registry: BehaviorRegistry) -> None:
    registry.register_behavior(COMPONENT_ACTIONS, decode_action_behavior, _handle_actions)
    registry.register_behavior(KEYBOARD_KEY, decode_keyboard_behavior, _handle_keyboard)
    registry.register_hook(BEHAVIOR_ACTIONS, decode_hook_outcome, _handle_action_hook)


def action_behavior(
    *,
    pressed_actions: tuple[RuntimeAction, ...] = (),
    released_actions: tuple[RuntimeAction, ...] = (),
) -> BehaviorConfig:
    return BehaviorConfig(
        COMPONENT_ACTIONS,
        {
            "pressed_actions": [runtime_action_to_data(action) for action in pressed_actions],
            "released_actions": [runtime_action_to_data(action) for action in released_actions],
        },
    )


def keyboard_behavior(mode: KeyboardBehaviorMode, output: KeyboardOutput) -> BehaviorConfig:
    return BehaviorConfig(
        KEYBOARD_KEY,
        {"mode": mode.value, "output": keyboard_output_to_data(output)},
    )


def action_hook(
    *,
    decision: HookDecision = HookDecision.CONTINUE,
    messages: tuple[RuntimeAction, ...] = (),
    replacement: tuple[RuntimeAction, ...] = (),
) -> BehaviorConfig:
    return BehaviorConfig(
        BEHAVIOR_ACTIONS,
        {
            "decision": decision.value,
            "messages": [runtime_action_to_data(action) for action in messages],
            "replacement": [runtime_action_to_data(action) for action in replacement],
        },
    )


def decode_action_behavior(arguments: DataMap) -> ActionBehavior:
    require_keys(arguments, ("pressed_actions", "released_actions"))
    return ActionBehavior(
        pressed_actions=_action_list(arguments, "pressed_actions"),
        released_actions=_action_list(arguments, "released_actions"),
    )


def decode_keyboard_behavior(arguments: DataMap) -> KeyboardBehavior:
    require_keys(arguments, ("mode", "output"))
    mode_value = string_value(arguments, "mode")
    try:
        mode = KeyboardBehaviorMode(mode_value)
    except ValueError as exc:
        raise ValueError(f"Unknown keyboard behavior mode {mode_value!r}") from exc
    return KeyboardBehavior(
        mode=mode,
        output=decode_keyboard_output(map_value(arguments, "output")),
    )


def decode_hook_outcome(arguments: DataMap) -> HookOutcome:
    require_keys(arguments, ("decision", "messages", "replacement"))
    decision_value = string_value(arguments, "decision")
    try:
        decision = HookDecision(decision_value)
    except ValueError as exc:
        raise ValueError(f"Unknown hook decision {decision_value!r}") from exc
    replacement = _action_list(arguments, "replacement")
    if decision is not HookDecision.REPLACE and replacement:
        raise ValueError("Only a replace hook outcome may contain replacement actions")
    return HookOutcome(
        decision=decision,
        messages=_action_list(arguments, "messages"),
        replacement=replacement,
    )


def _handle_actions(
    behavior: ActionBehavior,
    interaction: BehaviorInteraction,
    registry: BehaviorRegistry,
) -> MessageResult:
    del registry
    if interaction.event == COMPONENT_PRESSED:
        return list(behavior.pressed_actions)
    return list(behavior.released_actions)


def _handle_keyboard(
    behavior: KeyboardBehavior,
    interaction: BehaviorInteraction,
    registry: BehaviorRegistry,
) -> MessageResult:
    source = interaction.source
    layout_path = source.through("layout")
    active_tags = registry.active_state_tags(layout_path)
    messages: MessageResult = []

    if behavior.mode is KeyboardBehaviorMode.MOMENTARY:
        action = (
            keyboard_key_down(source, active_tags)
            if interaction.event == COMPONENT_PRESSED
            else keyboard_key_up(source, active_tags)
        )
        messages.append(action)
        messages.append(registry.layout_state_action(source, interaction.proposed_state))
        return messages

    if interaction.event == COMPONENT_PRESSED:
        if behavior.mode is KeyboardBehaviorMode.LOGICAL_TOGGLE or (
            behavior.mode is KeyboardBehaviorMode.HELD_TOGGLE
            and not bool(interaction.previous_state.get("latched", False))
        ):
            messages.append(keyboard_key_down(source, active_tags))
        messages.append(registry.layout_state_action(source, interaction.proposed_state))
        return messages

    state = dict(interaction.proposed_state)
    state["latched"] = not bool(interaction.previous_state.get("latched", False))
    messages.append(state_replace(source, state))
    messages.append(registry.layout_state_action(source, state))
    if behavior.mode is KeyboardBehaviorMode.LOGICAL_TOGGLE or (
        behavior.mode is KeyboardBehaviorMode.HELD_TOGGLE
        and not bool(state["latched"])
    ):
        messages.append(keyboard_key_up(source, active_tags))
    return messages


def _handle_action_hook(
    outcome: HookOutcome,
    interaction: BehaviorInteraction,
    registry: BehaviorRegistry,
) -> HookOutcome:
    del interaction, registry
    return outcome


def _action_list(arguments: DataMap, key: str) -> tuple[RuntimeAction, ...]:
    value = arguments[key]
    if not isinstance(value, list):
        raise TypeError(f"Argument {key!r} must be a list")
    actions: list[RuntimeAction] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise TypeError(f"Argument {key!r} item {index} must be a map")
        actions.append(runtime_action_from_data(item))
    return tuple(actions)


def _format_paths(paths: set[SourcePath]) -> str:
    return ", ".join(sorted(repr(path) for path in paths))
