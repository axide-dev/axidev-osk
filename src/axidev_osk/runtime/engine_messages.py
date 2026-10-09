"""Engine actions, observation events, and the handlers that record observations.

Observations arrive as events. The handlers here copy them into runtime-owned
state (``input.*``, ``keyboard.*``, ``windows.*``) before profile callbacks
for the same event run, so profiles always read up-to-date state.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..messages import DataMap, DataValue, MessageResult, RuntimeAction, RuntimeEvent
from .decoding import (
    bool_value,
    int_value,
    non_empty_string_value,
    optional_string_value,
    require_keys,
    string_value,
)
from .dispatcher import Dispatcher
from .profile_runtime import ProfileRuntime

_profile_logger = logging.getLogger("axidev_osk.profile")

INPUT_KEY = "input.key"
KEYBOARD_STATUS_CHANGED = "keyboard.status_changed"
KEYBOARD_PERMISSION_REQUIRED = "keyboard.permission_required"
KEYBOARD_RESET = "keyboard.reset"
PROCESS_EXITED = "process.exited"
WINDOW_VISIBILITY_CHANGED = "window.visibility_changed"

KEYBOARD_DOWN = "keyboard.down"
KEYBOARD_UP = "keyboard.up"
KEYBOARD_TAP = "keyboard.tap"
KEYBOARD_TYPE_TEXT = "keyboard.type_text"
PROCESS_SPAWN = "process.spawn"
LOG_INFO = "log.info"
LOG_WARN = "log.warn"
LOG_ERROR = "log.error"

_LOCKS = ("capslock", "numlock")


@dataclass(frozen=True, slots=True)
class InputKeyArguments:
    key: str
    text: str | None
    modifiers: tuple[str, ...]
    pressed: bool


@dataclass(frozen=True, slots=True)
class KeyboardStatusArguments:
    ready: bool
    status: str
    needs_permission_setup: bool
    permission_setup_text: str


@dataclass(frozen=True, slots=True)
class EmptyArguments:
    pass


@dataclass(frozen=True, slots=True)
class ProcessExitedArguments:
    tag: str
    code: int
    error: str | None


@dataclass(frozen=True, slots=True)
class WindowVisibilityArguments:
    window: str
    visible: bool
    minimized: bool


@dataclass(frozen=True, slots=True)
class KeyboardDownArguments:
    key: str
    mods: tuple[str, ...]
    repeat: bool


@dataclass(frozen=True, slots=True)
class KeyboardKeyArguments:
    key: str


@dataclass(frozen=True, slots=True)
class KeyboardTapArguments:
    key: str
    mods: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TextArguments:
    text: str


@dataclass(frozen=True, slots=True)
class ProcessSpawnArguments:
    argv: tuple[str, ...]
    tag: str
    detached: bool


@dataclass(frozen=True, slots=True)
class LogArguments:
    message: str


class KeyboardEffects(Protocol):
    def press(self, key: str, mods: tuple[str, ...], repeat: bool) -> None: ...

    def release(self, key: str) -> None: ...

    def tap(self, key: str, mods: tuple[str, ...]) -> None: ...

    def type_text(self, text: str) -> None: ...


class ProcessEffects(Protocol):
    def spawn(self, argv: tuple[str, ...], tag: str, detached: bool) -> None: ...


def input_key(key: str, text: str | None, modifiers: tuple[str, ...], pressed: bool) -> RuntimeEvent:
    return RuntimeEvent(
        INPUT_KEY,
        {"key": key, "text": text, "modifiers": list(modifiers), "pressed": pressed},
    )


def keyboard_status_changed(
    ready: bool,
    status: str,
    needs_permission_setup: bool,
    permission_setup_text: str,
) -> RuntimeEvent:
    return RuntimeEvent(
        KEYBOARD_STATUS_CHANGED,
        {
            "ready": ready,
            "status": status,
            "needs_permission_setup": needs_permission_setup,
            "permission_setup_text": permission_setup_text,
        },
    )


def keyboard_permission_required() -> RuntimeEvent:
    return RuntimeEvent(KEYBOARD_PERMISSION_REQUIRED, {})


def keyboard_reset() -> RuntimeEvent:
    return RuntimeEvent(KEYBOARD_RESET, {})


def process_exited(tag: str, code: int, error: str | None = None) -> RuntimeEvent:
    return RuntimeEvent(PROCESS_EXITED, {"tag": tag, "code": code, "error": error})


def window_visibility_changed(window: str, visible: bool, minimized: bool) -> RuntimeEvent:
    return RuntimeEvent(
        WINDOW_VISIBILITY_CHANGED,
        {"window": window, "visible": visible, "minimized": minimized},
    )


def keyboard_down(key: str, mods: tuple[str, ...] = (), repeat: bool = True) -> RuntimeAction:
    return RuntimeAction(KEYBOARD_DOWN, {"key": key, "mods": list(mods), "repeat": repeat})


def keyboard_up(key: str) -> RuntimeAction:
    return RuntimeAction(KEYBOARD_UP, {"key": key})


def decode_input_key(arguments: DataMap) -> InputKeyArguments:
    require_keys(arguments, ("key", "text", "modifiers", "pressed"))
    return InputKeyArguments(
        key=non_empty_string_value(arguments, "key"),
        text=optional_string_value(arguments, "text"),
        modifiers=_strings(arguments, "modifiers"),
        pressed=bool_value(arguments, "pressed"),
    )


def decode_keyboard_status(arguments: DataMap) -> KeyboardStatusArguments:
    require_keys(arguments, ("ready", "status", "needs_permission_setup", "permission_setup_text"))
    return KeyboardStatusArguments(
        ready=bool_value(arguments, "ready"),
        status=string_value(arguments, "status"),
        needs_permission_setup=bool_value(arguments, "needs_permission_setup"),
        permission_setup_text=string_value(arguments, "permission_setup_text"),
    )


def decode_empty(arguments: DataMap) -> EmptyArguments:
    require_keys(arguments, ())
    return EmptyArguments()


def decode_process_exited(arguments: DataMap) -> ProcessExitedArguments:
    require_keys(arguments, ("tag", "code"), optional=("error",))
    return ProcessExitedArguments(
        tag=string_value(arguments, "tag"),
        code=int_value(arguments, "code"),
        error=optional_string_value(arguments, "error") if "error" in arguments else None,
    )


def decode_window_visibility(arguments: DataMap) -> WindowVisibilityArguments:
    require_keys(arguments, ("window", "visible", "minimized"))
    return WindowVisibilityArguments(
        window=non_empty_string_value(arguments, "window"),
        visible=bool_value(arguments, "visible"),
        minimized=bool_value(arguments, "minimized"),
    )


def decode_keyboard_down(arguments: DataMap) -> KeyboardDownArguments:
    require_keys(arguments, ("key",), optional=("mods", "repeat"))
    return KeyboardDownArguments(
        key=non_empty_string_value(arguments, "key"),
        mods=_strings(arguments, "mods") if "mods" in arguments else (),
        repeat=bool_value(arguments, "repeat") if "repeat" in arguments else True,
    )


def decode_keyboard_key(arguments: DataMap) -> KeyboardKeyArguments:
    require_keys(arguments, ("key",))
    return KeyboardKeyArguments(key=non_empty_string_value(arguments, "key"))


def decode_keyboard_tap(arguments: DataMap) -> KeyboardTapArguments:
    require_keys(arguments, ("key",), optional=("mods",))
    return KeyboardTapArguments(
        key=non_empty_string_value(arguments, "key"),
        mods=_strings(arguments, "mods") if "mods" in arguments else (),
    )


def decode_text(arguments: DataMap) -> TextArguments:
    require_keys(arguments, ("text",))
    return TextArguments(text=string_value(arguments, "text"))


def decode_process_spawn(arguments: DataMap) -> ProcessSpawnArguments:
    require_keys(arguments, ("argv", "tag"), optional=("detached",))
    argv = _strings(arguments, "argv")
    if not argv or not argv[0]:
        raise ValueError("Argument 'argv' must start with a program name")
    return ProcessSpawnArguments(
        argv=argv,
        tag=string_value(arguments, "tag"),
        detached=bool_value(arguments, "detached") if "detached" in arguments else False,
    )


def decode_log(arguments: DataMap) -> LogArguments:
    require_keys(arguments, ("message",))
    return LogArguments(message=string_value(arguments, "message"))


def register_engine_events(dispatcher: Dispatcher) -> None:
    dispatcher.register_event(INPUT_KEY, decode_input_key)
    dispatcher.register_event(KEYBOARD_STATUS_CHANGED, decode_keyboard_status)
    dispatcher.register_event(KEYBOARD_PERMISSION_REQUIRED, decode_empty)
    dispatcher.register_event(KEYBOARD_RESET, decode_empty)
    dispatcher.register_event(PROCESS_EXITED, decode_process_exited)
    dispatcher.register_event(WINDOW_VISIBILITY_CHANGED, decode_window_visibility)


def install_engine_handlers(
    dispatcher: Dispatcher,
    *,
    profile_runtime: ProfileRuntime,
    keyboard: KeyboardEffects,
    processes: ProcessEffects,
) -> None:
    """Register engine actions and the observation handlers that record state.

    Call this before a profile starts so observation handlers run before
    profile callbacks for the same event.
    """

    def record_input_key(event: InputKeyArguments) -> MessageResult:
        messages = profile_runtime.set_observed(("input", "keys", event.key), event.pressed)
        active = {name.lower() for name in event.modifiers}
        for lock in _LOCKS:
            messages.extend(profile_runtime.set_observed(("input", "locks", lock), lock in active))
        return messages

    def record_keyboard_status(event: KeyboardStatusArguments) -> MessageResult:
        values: dict[str, DataValue] = {
            "ready": event.ready,
            "status": event.status,
            "needs_permission_setup": event.needs_permission_setup,
            "permission_setup_text": event.permission_setup_text,
        }
        messages: MessageResult = []
        for name, value in values.items():
            messages.extend(profile_runtime.set_observed(("keyboard", name), value))
        return messages

    def record_window_visibility(event: WindowVisibilityArguments) -> MessageResult:
        return [
            *profile_runtime.set_observed(("windows", event.window, "visible"), event.visible),
            *profile_runtime.set_observed(("windows", event.window, "minimized"), event.minimized),
        ]

    def press(arguments: KeyboardDownArguments) -> MessageResult:
        keyboard.press(arguments.key, arguments.mods, arguments.repeat)
        return []

    def release(arguments: KeyboardKeyArguments) -> MessageResult:
        keyboard.release(arguments.key)
        return []

    def tap(arguments: KeyboardTapArguments) -> MessageResult:
        keyboard.tap(arguments.key, arguments.mods)
        return []

    def type_text(arguments: TextArguments) -> MessageResult:
        keyboard.type_text(arguments.text)
        return []

    def spawn(arguments: ProcessSpawnArguments) -> MessageResult:
        processes.spawn(arguments.argv, arguments.tag, arguments.detached)
        return []

    def log_at(level: int) -> "Callable[[LogArguments], MessageResult]":
        def log(arguments: LogArguments) -> MessageResult:
            _profile_logger.log(level, "%s", arguments.message)
            return []

        return log

    dispatcher.add_event_handler(INPUT_KEY, record_input_key)
    dispatcher.add_event_handler(KEYBOARD_STATUS_CHANGED, record_keyboard_status)
    dispatcher.add_event_handler(WINDOW_VISIBILITY_CHANGED, record_window_visibility)
    dispatcher.register_action(KEYBOARD_DOWN, decode_keyboard_down, press)
    dispatcher.register_action(KEYBOARD_UP, decode_keyboard_key, release)
    dispatcher.register_action(KEYBOARD_TAP, decode_keyboard_tap, tap)
    dispatcher.register_action(KEYBOARD_TYPE_TEXT, decode_text, type_text)
    dispatcher.register_action(PROCESS_SPAWN, decode_process_spawn, spawn)
    dispatcher.register_action(LOG_INFO, decode_log, log_at(logging.INFO))
    dispatcher.register_action(LOG_WARN, decode_log, log_at(logging.WARNING))
    dispatcher.register_action(LOG_ERROR, decode_log, log_at(logging.ERROR))


def _strings(arguments: DataMap, key: str) -> tuple[str, ...]:
    value = arguments[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"Argument {key!r} must be a list of strings")
    return tuple(item for item in value if isinstance(item, str))
