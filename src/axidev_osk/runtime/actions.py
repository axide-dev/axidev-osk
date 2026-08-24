"""Typed constructors and decoders for built-in runtime actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..messages import DataMap, DataValue, RuntimeAction
from ..models import KeySpec, key_spec_to_data
from .decoding import (
    bool_value,
    data_value,
    int_value,
    key_spec_from_data,
    map_value,
    non_empty_string_value,
    number_value,
    require_keys,
)

APP_QUIT = "app.quit"
KEYBOARD_KEY_DOWN = "keyboard.key_down"
KEYBOARD_KEY_UP = "keyboard.key_up"
KEYBOARD_REGISTER_KEY_SPEC = "keyboard.register_key_spec"
KEYBOARD_SYNC_LATCHED_KEY = "keyboard.sync_latched_key"
STATE_SET = "state.set"
WINDOW_CLOSE = "window.close"
WINDOW_HIDE = "window.hide"
WINDOW_SHOW = "window.show"
WINDOW_TOGGLE_OPACITY = "window.toggle_opacity"


@dataclass(frozen=True, slots=True)
class AppQuitArguments:
    exit_code: int


@dataclass(frozen=True, slots=True)
class KeyboardRegisterKeySpecArguments:
    layout_id: str
    component_id: str
    key_spec: KeySpec


@dataclass(frozen=True, slots=True)
class KeyboardKeyArguments:
    layout_id: str
    component_id: str


@dataclass(frozen=True, slots=True)
class KeyboardSyncLatchedKeyArguments:
    layout_id: str
    component_id: str
    latched: bool


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


def keyboard_register_key_spec(layout_id: str, component_id: str, key_spec: KeySpec) -> RuntimeAction:
    return _validated_action(
        KEYBOARD_REGISTER_KEY_SPEC,
        {"layout_id": layout_id, "component_id": component_id, "key_spec": key_spec_to_data(key_spec)},
        decode_keyboard_register_key_spec,
    )


def keyboard_key_down(layout_id: str, component_id: str) -> RuntimeAction:
    return _validated_action(
        KEYBOARD_KEY_DOWN,
        {"layout_id": layout_id, "component_id": component_id},
        decode_keyboard_key,
    )


def keyboard_key_up(layout_id: str, component_id: str) -> RuntimeAction:
    return _validated_action(
        KEYBOARD_KEY_UP,
        {"layout_id": layout_id, "component_id": component_id},
        decode_keyboard_key,
    )


def keyboard_sync_latched_key(layout_id: str, component_id: str, latched: bool) -> RuntimeAction:
    return _validated_action(
        KEYBOARD_SYNC_LATCHED_KEY,
        {"layout_id": layout_id, "component_id": component_id, "latched": latched},
        decode_keyboard_sync_latched_key,
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


def decode_app_quit(arguments: DataMap) -> AppQuitArguments:
    require_keys(arguments, ("exit_code",))
    return AppQuitArguments(exit_code=int_value(arguments, "exit_code"))


def decode_keyboard_register_key_spec(arguments: DataMap) -> KeyboardRegisterKeySpecArguments:
    require_keys(arguments, ("layout_id", "component_id", "key_spec"))
    return KeyboardRegisterKeySpecArguments(
        layout_id=non_empty_string_value(arguments, "layout_id"),
        component_id=non_empty_string_value(arguments, "component_id"),
        key_spec=key_spec_from_data(map_value(arguments, "key_spec")),
    )


def decode_keyboard_key(arguments: DataMap) -> KeyboardKeyArguments:
    require_keys(arguments, ("layout_id", "component_id"))
    return KeyboardKeyArguments(
        layout_id=non_empty_string_value(arguments, "layout_id"),
        component_id=non_empty_string_value(arguments, "component_id"),
    )


def decode_keyboard_sync_latched_key(arguments: DataMap) -> KeyboardSyncLatchedKeyArguments:
    require_keys(arguments, ("layout_id", "component_id", "latched"))
    return KeyboardSyncLatchedKeyArguments(
        layout_id=non_empty_string_value(arguments, "layout_id"),
        component_id=non_empty_string_value(arguments, "component_id"),
        latched=bool_value(arguments, "latched"),
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


def _validated_action(
    name: str,
    arguments: DataMap,
    decoder: Callable[[DataMap], object],
) -> RuntimeAction:
    action = RuntimeAction(name, arguments)
    decoder(action.arguments)
    return action
