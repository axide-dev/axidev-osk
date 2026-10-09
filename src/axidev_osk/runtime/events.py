"""Typed constructors and decoders for built-in runtime events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..messages import DataMap, DataValue, RuntimeEvent
from .decoding import bool_value, map_value, non_empty_string_value, number_value, require_keys, string_set_value, string_value
from .source import SourcePath, source_path_from_data, source_path_to_data

if TYPE_CHECKING:
    from .dispatcher import Dispatcher

ACTION_FAILED = "action.failed"
BEHAVIOR_FAILED = "behavior.failed"
COMPONENT_PRESSED = "component.pressed"
COMPONENT_RELEASED = "component.released"
DISPLAY_CONFIGURATION_CHANGED = "display.configuration_changed"
HOT_CORNER_TRIGGERED = "hot_corner.triggered"
KEYBOARD_KEY_STATE_CHANGED = "keyboard.key_state_changed"
KEYBOARD_LOCK_STATE_CHANGED = "keyboard.lock_state_changed"
KEYBOARD_OUTPUT_REGISTERED = "keyboard.output_registered"
POINTER_MOTION_OBSERVED = "pointer.motion_observed"
PROMPT_RESOLVED = "prompt.resolved"
SECURE_INPUT_PANEL_PREPARED = "secure_input_panel.prepared"
SECURE_INPUT_PANEL_RELEASED = "secure_input_panel.released"
STATE_CHANGED = "legacy.state_changed"
WINDOW_CLOSE_REQUESTED = "window.close_requested"
WINDOW_DRAG_ENDED = "window.drag_ended"
WINDOW_DRAG_STARTED = "window.drag_started"


@dataclass(frozen=True, slots=True)
class ActionFailedArguments:
    action: str
    arguments: DataMap
    stage: str
    exception_type: str
    message: str


@dataclass(frozen=True, slots=True)
class BehaviorFailedArguments:
    source: SourcePath
    kind: str
    phase: str
    stage: str
    exception_type: str
    message: str


@dataclass(frozen=True, slots=True)
class ComponentPressedArguments:
    source: SourcePath


@dataclass(frozen=True, slots=True)
class ComponentReleasedArguments:
    source: SourcePath


@dataclass(frozen=True, slots=True)
class HotCornerTriggeredArguments:
    corner: str


@dataclass(frozen=True, slots=True)
class KeyboardKeyStateChangedArguments:
    source: SourcePath
    pressed: bool
    state_tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class KeyboardLockStateChangedArguments:
    source: SourcePath
    locked: bool


@dataclass(frozen=True, slots=True)
class KeyboardOutputRegisteredArguments:
    source: SourcePath
    output_key: str
    state_tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class DisplayConfigurationChangedArguments:
    pass


@dataclass(frozen=True, slots=True)
class NoEventArguments:
    pass


@dataclass(frozen=True, slots=True)
class PointerMotionObservedArguments:
    dx: float
    dy: float


@dataclass(frozen=True, slots=True)
class PromptResolvedArguments:
    prompt_id: str
    result: str


@dataclass(frozen=True, slots=True)
class StateChangedArguments:
    source: SourcePath
    state: DataMap


@dataclass(frozen=True, slots=True)
class WindowCloseRequestedArguments:
    window_id: str


@dataclass(frozen=True, slots=True)
class WindowDragArguments:
    window_id: str


def component_pressed(source: SourcePath) -> RuntimeEvent:
    return RuntimeEvent(COMPONENT_PRESSED, {"source": source_path_to_data(source)})


def component_released(source: SourcePath) -> RuntimeEvent:
    return RuntimeEvent(COMPONENT_RELEASED, {"source": source_path_to_data(source)})


def behavior_failed(
    source: SourcePath,
    kind: str,
    phase: str,
    stage: str,
    exception_type: str,
    message: str,
) -> RuntimeEvent:
    return RuntimeEvent(
        BEHAVIOR_FAILED,
        {
            "source": source_path_to_data(source),
            "kind": kind,
            "phase": phase,
            "stage": stage,
            "exception_type": exception_type,
            "message": message,
        },
    )


def display_configuration_changed() -> RuntimeEvent:
    return RuntimeEvent(DISPLAY_CONFIGURATION_CHANGED, {})


def hot_corner_triggered(corner: str) -> RuntimeEvent:
    return RuntimeEvent(HOT_CORNER_TRIGGERED, {"corner": corner})


def keyboard_key_state_changed(
    source: SourcePath,
    pressed: bool,
    state_tags: frozenset[str],
) -> RuntimeEvent:
    tags: list[DataValue] = list(sorted(state_tags))
    return RuntimeEvent(
        KEYBOARD_KEY_STATE_CHANGED,
        {
            "source": source_path_to_data(source),
            "pressed": pressed,
            "state_tags": tags,
        },
    )


def keyboard_lock_state_changed(source: SourcePath, locked: bool) -> RuntimeEvent:
    return RuntimeEvent(
        KEYBOARD_LOCK_STATE_CHANGED,
        {"source": source_path_to_data(source), "locked": locked},
    )


def keyboard_output_registered(
    source: SourcePath,
    output_key: str,
    state_tags: frozenset[str],
) -> RuntimeEvent:
    tags: list[DataValue] = list(sorted(state_tags))
    return RuntimeEvent(
        KEYBOARD_OUTPUT_REGISTERED,
        {
            "source": source_path_to_data(source),
            "output_key": output_key,
            "state_tags": tags,
        },
    )


def pointer_motion_observed(dx: float, dy: float) -> RuntimeEvent:
    return RuntimeEvent(POINTER_MOTION_OBSERVED, {"dx": dx, "dy": dy})


def prompt_resolved(prompt_id: str, result: str) -> RuntimeEvent:
    return RuntimeEvent(PROMPT_RESOLVED, {"prompt_id": prompt_id, "result": result})


def secure_input_panel_prepared() -> RuntimeEvent:
    return RuntimeEvent(SECURE_INPUT_PANEL_PREPARED, {})


def secure_input_panel_released() -> RuntimeEvent:
    return RuntimeEvent(SECURE_INPUT_PANEL_RELEASED, {})


def state_changed(source: SourcePath, state: DataMap) -> RuntimeEvent:
    return RuntimeEvent(STATE_CHANGED, {"source": source_path_to_data(source), "state": state})


def window_close_requested(window_id: str) -> RuntimeEvent:
    return RuntimeEvent(WINDOW_CLOSE_REQUESTED, {"window": window_id})


def window_drag_started(window_id: str) -> RuntimeEvent:
    return RuntimeEvent(WINDOW_DRAG_STARTED, {"window": window_id})


def window_drag_ended(window_id: str) -> RuntimeEvent:
    return RuntimeEvent(WINDOW_DRAG_ENDED, {"window": window_id})


def decode_action_failed(arguments: DataMap) -> ActionFailedArguments:
    require_keys(arguments, ("action", "arguments", "stage", "exception_type", "message"))
    return ActionFailedArguments(
        action=string_value(arguments, "action"),
        arguments=map_value(arguments, "arguments"),
        stage=string_value(arguments, "stage"),
        exception_type=string_value(arguments, "exception_type"),
        message=string_value(arguments, "message"),
    )


def decode_behavior_failed(arguments: DataMap) -> BehaviorFailedArguments:
    require_keys(arguments, ("source", "kind", "phase", "stage", "exception_type", "message"))
    return BehaviorFailedArguments(
        source=source_path_from_data(arguments["source"]),
        kind=string_value(arguments, "kind"),
        phase=string_value(arguments, "phase"),
        stage=string_value(arguments, "stage"),
        exception_type=string_value(arguments, "exception_type"),
        message=string_value(arguments, "message"),
    )


def decode_component_pressed(arguments: DataMap) -> ComponentPressedArguments:
    require_keys(arguments, ("source",))
    return ComponentPressedArguments(source=source_path_from_data(arguments["source"]))


def decode_component_released(arguments: DataMap) -> ComponentReleasedArguments:
    require_keys(arguments, ("source",))
    return ComponentReleasedArguments(source=source_path_from_data(arguments["source"]))


def decode_display_configuration_changed(arguments: DataMap) -> DisplayConfigurationChangedArguments:
    require_keys(arguments, ())
    return DisplayConfigurationChangedArguments()


def decode_no_event_arguments(arguments: DataMap) -> NoEventArguments:
    require_keys(arguments, ())
    return NoEventArguments()


def decode_hot_corner_triggered(arguments: DataMap) -> HotCornerTriggeredArguments:
    require_keys(arguments, ("corner",))
    return HotCornerTriggeredArguments(corner=string_value(arguments, "corner"))


def decode_keyboard_key_state_changed(arguments: DataMap) -> KeyboardKeyStateChangedArguments:
    require_keys(arguments, ("source", "pressed", "state_tags"))
    return KeyboardKeyStateChangedArguments(
        source=source_path_from_data(arguments["source"]),
        pressed=bool_value(arguments, "pressed"),
        state_tags=string_set_value(arguments, "state_tags"),
    )


def decode_keyboard_lock_state_changed(arguments: DataMap) -> KeyboardLockStateChangedArguments:
    require_keys(arguments, ("source", "locked"))
    return KeyboardLockStateChangedArguments(
        source=source_path_from_data(arguments["source"]),
        locked=bool_value(arguments, "locked"),
    )


def decode_keyboard_output_registered(arguments: DataMap) -> KeyboardOutputRegisteredArguments:
    require_keys(arguments, ("source", "output_key", "state_tags"))
    return KeyboardOutputRegisteredArguments(
        source=source_path_from_data(arguments["source"]),
        output_key=string_value(arguments, "output_key"),
        state_tags=string_set_value(arguments, "state_tags"),
    )


def decode_pointer_motion_observed(arguments: DataMap) -> PointerMotionObservedArguments:
    require_keys(arguments, ("dx", "dy"))
    return PointerMotionObservedArguments(
        dx=number_value(arguments, "dx"),
        dy=number_value(arguments, "dy"),
    )


def decode_prompt_resolved(arguments: DataMap) -> PromptResolvedArguments:
    require_keys(arguments, ("prompt_id", "result"))
    return PromptResolvedArguments(
        prompt_id=string_value(arguments, "prompt_id"),
        result=string_value(arguments, "result"),
    )


def decode_state_changed(arguments: DataMap) -> StateChangedArguments:
    require_keys(arguments, ("source", "state"))
    return StateChangedArguments(
        source=source_path_from_data(arguments["source"]),
        state=map_value(arguments, "state"),
    )


def decode_window_close_requested(arguments: DataMap) -> WindowCloseRequestedArguments:
    require_keys(arguments, ("window",))
    return WindowCloseRequestedArguments(window_id=string_value(arguments, "window"))


def decode_window_drag(arguments: DataMap) -> WindowDragArguments:
    require_keys(arguments, ("window",))
    return WindowDragArguments(window_id=non_empty_string_value(arguments, "window"))


def register_builtin_events(dispatcher: "Dispatcher") -> None:
    """Register every built-in event decoder."""

    dispatcher.register_event(ACTION_FAILED, decode_action_failed)
    dispatcher.register_event(BEHAVIOR_FAILED, decode_behavior_failed)
    dispatcher.register_event(COMPONENT_PRESSED, decode_component_pressed)
    dispatcher.register_event(COMPONENT_RELEASED, decode_component_released)
    dispatcher.register_event(DISPLAY_CONFIGURATION_CHANGED, decode_display_configuration_changed)
    dispatcher.register_event(HOT_CORNER_TRIGGERED, decode_hot_corner_triggered)
    dispatcher.register_event(KEYBOARD_KEY_STATE_CHANGED, decode_keyboard_key_state_changed)
    dispatcher.register_event(KEYBOARD_LOCK_STATE_CHANGED, decode_keyboard_lock_state_changed)
    dispatcher.register_event(KEYBOARD_OUTPUT_REGISTERED, decode_keyboard_output_registered)
    dispatcher.register_event(POINTER_MOTION_OBSERVED, decode_pointer_motion_observed)
    dispatcher.register_event(PROMPT_RESOLVED, decode_prompt_resolved)
    dispatcher.register_event(SECURE_INPUT_PANEL_PREPARED, decode_no_event_arguments)
    dispatcher.register_event(SECURE_INPUT_PANEL_RELEASED, decode_no_event_arguments)
    dispatcher.register_event(STATE_CHANGED, decode_state_changed)
    dispatcher.register_event(WINDOW_CLOSE_REQUESTED, decode_window_close_requested)
    dispatcher.register_event(WINDOW_DRAG_ENDED, decode_window_drag)
    dispatcher.register_event(WINDOW_DRAG_STARTED, decode_window_drag)
