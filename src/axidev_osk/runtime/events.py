"""Typed constructors and decoders for built-in runtime events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..messages import DataMap, RuntimeAction, RuntimeEvent, runtime_action_to_data
from .decoding import (
    bool_value,
    map_value,
    optional_string_value,
    require_keys,
    runtime_action_from_data,
    string_value,
)

if TYPE_CHECKING:
    from .dispatcher import Dispatcher

ACTION_FAILED = "action.failed"
COMPONENT_PRESSED = "component.pressed"
COMPONENT_RELEASED = "component.released"
COMPONENT_STATE_CHANGED = "component.state_changed"
HOT_CORNER_TRIGGERED = "hot_corner.triggered"
KEYBOARD_KEY_REGISTERED = "keyboard.key_registered"
KEYBOARD_KEY_STATE_CHANGED = "keyboard.key_state_changed"
KEYBOARD_LATCH_CHANGED = "keyboard.latch_changed"
PROMPT_RESOLVED = "prompt.resolved"
WINDOW_CLOSE_REQUESTED = "window.close_requested"


@dataclass(frozen=True, slots=True)
class ActionFailedArguments:
    action: str
    arguments: DataMap
    stage: str
    exception_type: str
    message: str


@dataclass(frozen=True, slots=True)
class ComponentPressedArguments:
    component_id: str
    action: RuntimeAction | None


@dataclass(frozen=True, slots=True)
class ComponentReleasedArguments:
    component_id: str


@dataclass(frozen=True, slots=True)
class ComponentStateChangedArguments:
    component_id: str
    key_id: str
    latched: bool


@dataclass(frozen=True, slots=True)
class HotCornerTriggeredArguments:
    corner: str


@dataclass(frozen=True, slots=True)
class KeyboardKeyRegisteredArguments:
    layout_id: str
    component_id: str
    io_key_name: str | None


@dataclass(frozen=True, slots=True)
class KeyboardKeyStateChangedArguments:
    layout_id: str
    key_id: str
    pressed: bool
    latched: bool


@dataclass(frozen=True, slots=True)
class KeyboardLatchChangedArguments:
    layout_id: str
    key_id: str
    latched: bool


@dataclass(frozen=True, slots=True)
class PromptResolvedArguments:
    prompt_id: str
    result: str


@dataclass(frozen=True, slots=True)
class WindowCloseRequestedArguments:
    window_id: str


def component_pressed(component_id: str, action: RuntimeAction | None = None) -> RuntimeEvent:
    return RuntimeEvent(
        COMPONENT_PRESSED,
        {"component_id": component_id, "action": runtime_action_to_data(action) if action is not None else None},
    )


def component_released(component_id: str) -> RuntimeEvent:
    return RuntimeEvent(COMPONENT_RELEASED, {"component_id": component_id})


def component_state_changed(component_id: str, key_id: str, latched: bool) -> RuntimeEvent:
    return RuntimeEvent(
        COMPONENT_STATE_CHANGED,
        {"component_id": component_id, "key_id": key_id, "latched": latched},
    )


def hot_corner_triggered(corner: str) -> RuntimeEvent:
    return RuntimeEvent(HOT_CORNER_TRIGGERED, {"corner": corner})


def keyboard_key_registered(layout_id: str, component_id: str, io_key_name: str | None) -> RuntimeEvent:
    return RuntimeEvent(
        KEYBOARD_KEY_REGISTERED,
        {"layout_id": layout_id, "component_id": component_id, "io_key_name": io_key_name},
    )


def keyboard_key_state_changed(layout_id: str, key_id: str, pressed: bool, latched: bool) -> RuntimeEvent:
    return RuntimeEvent(
        KEYBOARD_KEY_STATE_CHANGED,
        {"layout_id": layout_id, "key_id": key_id, "pressed": pressed, "latched": latched},
    )


def keyboard_latch_changed(layout_id: str, key_id: str, latched: bool) -> RuntimeEvent:
    return RuntimeEvent(
        KEYBOARD_LATCH_CHANGED,
        {"layout_id": layout_id, "key_id": key_id, "latched": latched},
    )


def prompt_resolved(prompt_id: str, result: str) -> RuntimeEvent:
    return RuntimeEvent(PROMPT_RESOLVED, {"prompt_id": prompt_id, "result": result})


def window_close_requested(window_id: str) -> RuntimeEvent:
    return RuntimeEvent(WINDOW_CLOSE_REQUESTED, {"window_id": window_id})


def decode_action_failed(arguments: DataMap) -> ActionFailedArguments:
    require_keys(arguments, ("action", "arguments", "stage", "exception_type", "message"))
    return ActionFailedArguments(
        action=string_value(arguments, "action"),
        arguments=map_value(arguments, "arguments"),
        stage=string_value(arguments, "stage"),
        exception_type=string_value(arguments, "exception_type"),
        message=string_value(arguments, "message"),
    )


def decode_component_pressed(arguments: DataMap) -> ComponentPressedArguments:
    require_keys(arguments, ("component_id", "action"))
    action_value = arguments["action"]
    if action_value is not None and not isinstance(action_value, dict):
        raise TypeError("Argument 'action' must be a map or null")
    return ComponentPressedArguments(
        component_id=string_value(arguments, "component_id"),
        action=runtime_action_from_data(action_value) if isinstance(action_value, dict) else None,
    )


def decode_component_released(arguments: DataMap) -> ComponentReleasedArguments:
    require_keys(arguments, ("component_id",))
    return ComponentReleasedArguments(component_id=string_value(arguments, "component_id"))


def decode_component_state_changed(arguments: DataMap) -> ComponentStateChangedArguments:
    require_keys(arguments, ("component_id", "key_id", "latched"))
    return ComponentStateChangedArguments(
        component_id=string_value(arguments, "component_id"),
        key_id=string_value(arguments, "key_id"),
        latched=bool_value(arguments, "latched"),
    )


def decode_hot_corner_triggered(arguments: DataMap) -> HotCornerTriggeredArguments:
    require_keys(arguments, ("corner",))
    return HotCornerTriggeredArguments(corner=string_value(arguments, "corner"))


def decode_keyboard_key_registered(arguments: DataMap) -> KeyboardKeyRegisteredArguments:
    require_keys(arguments, ("layout_id", "component_id", "io_key_name"))
    return KeyboardKeyRegisteredArguments(
        layout_id=string_value(arguments, "layout_id"),
        component_id=string_value(arguments, "component_id"),
        io_key_name=optional_string_value(arguments, "io_key_name"),
    )


def decode_keyboard_key_state_changed(arguments: DataMap) -> KeyboardKeyStateChangedArguments:
    require_keys(arguments, ("layout_id", "key_id", "pressed", "latched"))
    return KeyboardKeyStateChangedArguments(
        layout_id=string_value(arguments, "layout_id"),
        key_id=string_value(arguments, "key_id"),
        pressed=bool_value(arguments, "pressed"),
        latched=bool_value(arguments, "latched"),
    )


def decode_keyboard_latch_changed(arguments: DataMap) -> KeyboardLatchChangedArguments:
    require_keys(arguments, ("layout_id", "key_id", "latched"))
    return KeyboardLatchChangedArguments(
        layout_id=string_value(arguments, "layout_id"),
        key_id=string_value(arguments, "key_id"),
        latched=bool_value(arguments, "latched"),
    )


def decode_prompt_resolved(arguments: DataMap) -> PromptResolvedArguments:
    require_keys(arguments, ("prompt_id", "result"))
    return PromptResolvedArguments(
        prompt_id=string_value(arguments, "prompt_id"),
        result=string_value(arguments, "result"),
    )


def decode_window_close_requested(arguments: DataMap) -> WindowCloseRequestedArguments:
    require_keys(arguments, ("window_id",))
    return WindowCloseRequestedArguments(window_id=string_value(arguments, "window_id"))


def register_builtin_events(dispatcher: "Dispatcher") -> None:
    """Register every built-in event decoder on a dispatcher-shaped object."""

    dispatcher.register_event(ACTION_FAILED, decode_action_failed)
    dispatcher.register_event(COMPONENT_PRESSED, decode_component_pressed)
    dispatcher.register_event(COMPONENT_RELEASED, decode_component_released)
    dispatcher.register_event(COMPONENT_STATE_CHANGED, decode_component_state_changed)
    dispatcher.register_event(HOT_CORNER_TRIGGERED, decode_hot_corner_triggered)
    dispatcher.register_event(KEYBOARD_KEY_REGISTERED, decode_keyboard_key_registered)
    dispatcher.register_event(KEYBOARD_KEY_STATE_CHANGED, decode_keyboard_key_state_changed)
    dispatcher.register_event(KEYBOARD_LATCH_CHANGED, decode_keyboard_latch_changed)
    dispatcher.register_event(PROMPT_RESOLVED, decode_prompt_resolved)
    dispatcher.register_event(WINDOW_CLOSE_REQUESTED, decode_window_close_requested)
