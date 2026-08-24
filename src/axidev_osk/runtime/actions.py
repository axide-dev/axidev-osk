"""Typed constructors and decoders for built-in runtime actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..messages import DataMap, DataValue, RuntimeAction
from .behavior_models import KeyboardOutput
from .decoding import (
    bool_value,
    data_value,
    int_value,
    map_value,
    non_empty_string_value,
    number_value,
    require_keys,
    string_set_value,
)
from .source import SourcePath, source_path_from_data, source_path_to_data

APP_QUIT = "app.quit"
KEYBOARD_KEY_DOWN = "keyboard.key_down"
KEYBOARD_KEY_UP = "keyboard.key_up"
KEYBOARD_REGISTER_OUTPUT = "keyboard.register_output"
PROMPT_RESOLVE = "prompt.resolve"
STATE_REPLACE = "state.replace"
STATE_SET = "state.set"
WINDOW_CLOSE = "window.close"
WINDOW_HIDE = "window.hide"
WINDOW_SHOW = "window.show"
WINDOW_TOGGLE_OPACITY = "window.toggle_opacity"


@dataclass(frozen=True, slots=True)
class AppQuitArguments:
    exit_code: int


@dataclass(frozen=True, slots=True)
class KeyboardKeyArguments:
    source: SourcePath
    active_state_tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class KeyboardRegisterOutputArguments:
    source: SourcePath
    output: KeyboardOutput


@dataclass(frozen=True, slots=True)
class PromptResolveArguments:
    prompt_id: str
    result: str


@dataclass(frozen=True, slots=True)
class StateReplaceArguments:
    source: SourcePath
    state: DataMap


@dataclass(frozen=True, slots=True)
class StateSetArguments:
    namespace: str
    key: str
    value: DataValue


@dataclass(frozen=True, slots=True)
class WindowArguments:
    window_id: str


@dataclass(frozen=True, slots=True)
class WindowToggleOpacityArguments:
    window_id: str
    component_id: str
    opacity: float


def app_quit(exit_code: int = 0) -> RuntimeAction:
    return _validated_action(APP_QUIT, {"exit_code": exit_code}, decode_app_quit)


def keyboard_register_output(source: SourcePath, output: KeyboardOutput) -> RuntimeAction:
    return _validated_action(
        KEYBOARD_REGISTER_OUTPUT,
        {"source": source_path_to_data(source), "output": keyboard_output_to_data(output)},
        decode_keyboard_register_output,
    )


def keyboard_key_down(source: SourcePath, active_state_tags: frozenset[str]) -> RuntimeAction:
    return _keyboard_key_action(KEYBOARD_KEY_DOWN, source, active_state_tags)


def keyboard_key_up(source: SourcePath, active_state_tags: frozenset[str]) -> RuntimeAction:
    return _keyboard_key_action(KEYBOARD_KEY_UP, source, active_state_tags)


def prompt_resolve(prompt_id: str, result: str) -> RuntimeAction:
    return _validated_action(
        PROMPT_RESOLVE,
        {"prompt_id": prompt_id, "result": result},
        decode_prompt_resolve,
    )


def state_replace(source: SourcePath, state: DataMap) -> RuntimeAction:
    return _validated_action(
        STATE_REPLACE,
        {"source": source_path_to_data(source), "state": state},
        decode_state_replace,
    )


def state_set(namespace: str, key: str, value: DataValue) -> RuntimeAction:
    return _validated_action(
        STATE_SET,
        {"namespace": namespace, "key": key, "value": value},
        decode_state_set,
    )


def window_show(window_id: str) -> RuntimeAction:
    return _validated_action(WINDOW_SHOW, {"window_id": window_id}, decode_window)


def window_hide(window_id: str) -> RuntimeAction:
    return _validated_action(WINDOW_HIDE, {"window_id": window_id}, decode_window)


def window_close(window_id: str) -> RuntimeAction:
    return _validated_action(WINDOW_CLOSE, {"window_id": window_id}, decode_window)


def window_toggle_opacity(window_id: str, component_id: str, opacity: float) -> RuntimeAction:
    return _validated_action(
        WINDOW_TOGGLE_OPACITY,
        {"window_id": window_id, "component_id": component_id, "opacity": opacity},
        decode_window_toggle_opacity,
    )


def keyboard_output_to_data(output: KeyboardOutput) -> DataMap:
    return {
        "output_key": output.output_key,
        "repeats": output.repeats,
        "uses_active_state_tags": output.uses_active_state_tags,
    }


def decode_keyboard_output(arguments: DataMap) -> KeyboardOutput:
    require_keys(arguments, ("output_key", "repeats", "uses_active_state_tags"))
    return KeyboardOutput(
        output_key=non_empty_string_value(arguments, "output_key"),
        repeats=bool_value(arguments, "repeats"),
        uses_active_state_tags=bool_value(arguments, "uses_active_state_tags"),
    )


def decode_app_quit(arguments: DataMap) -> AppQuitArguments:
    require_keys(arguments, ("exit_code",))
    return AppQuitArguments(exit_code=int_value(arguments, "exit_code"))


def decode_keyboard_register_output(arguments: DataMap) -> KeyboardRegisterOutputArguments:
    require_keys(arguments, ("source", "output"))
    return KeyboardRegisterOutputArguments(
        source=source_path_from_data(arguments["source"]),
        output=decode_keyboard_output(map_value(arguments, "output")),
    )


def decode_keyboard_key(arguments: DataMap) -> KeyboardKeyArguments:
    require_keys(arguments, ("source", "active_state_tags"))
    return KeyboardKeyArguments(
        source=source_path_from_data(arguments["source"]),
        active_state_tags=string_set_value(arguments, "active_state_tags"),
    )


def decode_prompt_resolve(arguments: DataMap) -> PromptResolveArguments:
    require_keys(arguments, ("prompt_id", "result"))
    return PromptResolveArguments(
        prompt_id=non_empty_string_value(arguments, "prompt_id"),
        result=non_empty_string_value(arguments, "result"),
    )


def decode_state_replace(arguments: DataMap) -> StateReplaceArguments:
    require_keys(arguments, ("source", "state"))
    return StateReplaceArguments(
        source=source_path_from_data(arguments["source"]),
        state=map_value(arguments, "state"),
    )


def decode_state_set(arguments: DataMap) -> StateSetArguments:
    require_keys(arguments, ("namespace", "key", "value"))
    return StateSetArguments(
        namespace=non_empty_string_value(arguments, "namespace"),
        key=non_empty_string_value(arguments, "key"),
        value=data_value(arguments, "value"),
    )


def decode_window(arguments: DataMap) -> WindowArguments:
    require_keys(arguments, ("window_id",))
    return WindowArguments(window_id=non_empty_string_value(arguments, "window_id"))


def decode_window_toggle_opacity(arguments: DataMap) -> WindowToggleOpacityArguments:
    require_keys(arguments, ("window_id", "component_id", "opacity"))
    opacity = number_value(arguments, "opacity")
    if not 0.0 <= opacity < 1.0:
        raise ValueError("Argument 'opacity' must be at least 0.0 and less than 1.0")
    return WindowToggleOpacityArguments(
        window_id=non_empty_string_value(arguments, "window_id"),
        component_id=non_empty_string_value(arguments, "component_id"),
        opacity=opacity,
    )


def _keyboard_key_action(
    name: str,
    source: SourcePath,
    active_state_tags: frozenset[str],
) -> RuntimeAction:
    state_tags: list[DataValue] = list(sorted(active_state_tags))
    return _validated_action(
        name,
        {"source": source_path_to_data(source), "active_state_tags": state_tags},
        decode_keyboard_key,
    )


def _validated_action(
    name: str,
    arguments: DataMap,
    decoder: Callable[[DataMap], object],
) -> RuntimeAction:
    action = RuntimeAction(name, arguments)
    decoder(action.arguments)
    return action
