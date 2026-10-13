"""Engine actions, observation events, and the handlers that record observations.

Observations arrive as events. The handlers here copy them into runtime-owned
state (``input.*``, ``keyboard.*``, ``windows.*``, ``nodes.*``) before profile callbacks
for the same event run, so profiles always read up-to-date state.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Protocol

from ..config.variables import ListOf, MapOf, Record, Scalar, StatePath, Variable, record_default
from ..messages import DataMap, DataValue, MessageResult, RuntimeAction, RuntimeEvent
from .decoding import (
    bool_value,
    decode_empty,
    int_value,
    non_empty_string_value,
    optional_string_value,
    require_keys,
    string_list_value,
    string_value,
    validated_action,
    validated_event,
)
from .dispatcher import Dispatcher
from .event_fields import profile_node, profile_window, samples
from .profile_runtime import ProfileRuntime

_profile_logger = logging.getLogger("axidev_osk.profile")

INPUT_KEY = "input.key"
KEYBOARD_STATUS_CHANGED = "keyboard.status_changed"
KEYBOARD_PERMISSION_REQUIRED = "keyboard.permission_required"
KEYBOARD_RESET = "keyboard.reset"
PROCESS_EXITED = "process.exited"
WINDOW_STATE_CHANGED = "window.state_changed"
NODE_GEOMETRY_CHANGED = "node.geometry_changed"

KEYBOARD_DOWN = "keyboard.down"
KEYBOARD_UP = "keyboard.up"
KEYBOARD_TAP = "keyboard.tap"
KEYBOARD_TYPE_TEXT = "keyboard.type_text"
PROCESS_SPAWN = "process.spawn"
LOG_INFO = "log.info"
LOG_WARN = "log.warn"
LOG_ERROR = "log.error"

_LOCKS = ("capslock", "numlock")


def _boolean(default: bool = False) -> Variable:
    return Variable(Scalar("boolean"), default)


def _integer() -> Variable:
    return Variable(Scalar("integer"), 0)


def _string() -> Variable:
    return Variable(Scalar("string"), "")


def _record(**fields: Variable) -> Variable:
    record = Record(fields)
    return Variable(record, record_default(record))


# Variables the engine writes from observations; profiles read them but cannot set them. A value a
# binding can set, such as a window's opacity, has no setter action and no copy here: the variable
# its binding reads is its only source.
OBSERVED_VARIABLES: dict[StatePath, Variable] = {
    ("input", "keys"): Variable(MapOf(Scalar("boolean")), {}),
    ("input", "locks"): _record(**{lock: _boolean() for lock in _LOCKS}),
    ("keyboard",): _record(
        ready=_boolean(),
        status=_string(),
        needs_permission_setup=_boolean(),
        permission_setup_text=_string(),
    ),
    ("app",): _record(profile=_string(), profiles=Variable(ListOf(Scalar("string")), [])),
    ("windows",): Variable(
        MapOf(
            Record(
                {
                    "visible": _boolean(),
                    "minimized": _boolean(),
                    "position": _record(x=_integer(), y=_integer()),
                    "size": _record(width=_integer(), height=_integer()),
                }
            )
        ),
        {},
    ),
    ("nodes",): Variable(
        MapOf(
            Record(
                {
                    "position": _record(x=_integer(), y=_integer()),
                    "size": _record(width=_integer(), height=_integer()),
                }
            )
        ),
        {},
    ),
}
"""What the engine observes: keys and locks, keyboard output status, the running and available profiles, each built
window, and each node built with ``report_geometry``."""


@dataclass(frozen=True, slots=True)
class InputKeyArguments:
    key: str = samples("A")
    text: str | None = samples("a")
    modifiers: tuple[str, ...] = samples([])
    pressed: bool = samples(False, True)


@dataclass(frozen=True, slots=True)
class KeyboardStatusArguments:
    ready: bool = samples(False, True)
    status: str = samples("")
    needs_permission_setup: bool = samples(False, True)
    permission_setup_text: str = samples("")


@dataclass(frozen=True, slots=True)
class ProcessExitedArguments:
    tag: str = samples("example")
    code: int = samples(0)
    error: str | None = samples("example error")


@dataclass(frozen=True, slots=True)
class WindowStateArguments:
    window_id: str = profile_window(key="window")
    visible: bool = samples(False, True)
    minimized: bool = samples(False, True)
    x: int = samples(0)
    y: int = samples(0)
    width: int = samples(100)
    height: int = samples(100)


@dataclass(frozen=True, slots=True)
class NodeGeometryArguments:
    node: str = profile_node()
    x: int = samples(0)
    y: int = samples(0)
    width: int = samples(100)
    height: int = samples(100)


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
    return validated_event(
        INPUT_KEY,
        {"key": key, "text": text, "modifiers": list(modifiers), "pressed": pressed},
        decode_input_key,
    )


def keyboard_status_changed(
    ready: bool,
    status: str,
    needs_permission_setup: bool,
    permission_setup_text: str,
) -> RuntimeEvent:
    return validated_event(
        KEYBOARD_STATUS_CHANGED,
        {
            "ready": ready,
            "status": status,
            "needs_permission_setup": needs_permission_setup,
            "permission_setup_text": permission_setup_text,
        },
        decode_keyboard_status,
    )


def keyboard_permission_required() -> RuntimeEvent:
    return validated_event(KEYBOARD_PERMISSION_REQUIRED, {}, decode_empty)


def keyboard_reset() -> RuntimeEvent:
    return validated_event(KEYBOARD_RESET, {}, decode_empty)


def process_exited(tag: str, code: int, error: str | None = None) -> RuntimeEvent:
    """``error`` is left out when the program ran, as Lua leaves out ``nil``."""

    arguments: DataMap = {"tag": tag, "code": code}
    if error is not None:
        arguments["error"] = error
    return validated_event(PROCESS_EXITED, arguments, decode_process_exited)


def window_state_changed(
    window_id: str,
    *,
    visible: bool,
    minimized: bool,
    x: int,
    y: int,
    width: int,
    height: int,
) -> RuntimeEvent:
    """Report what a window looks like on screen; ``x`` and ``y`` are its top-left corner in screen coordinates."""

    return validated_event(
        WINDOW_STATE_CHANGED,
        {
            "window": window_id,
            "visible": visible,
            "minimized": minimized,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        },
        decode_window_state,
    )


def keyboard_down(key: str, mods: tuple[str, ...] = (), repeat: bool = True) -> RuntimeAction:
    return validated_action(KEYBOARD_DOWN, {"key": key, "mods": list(mods), "repeat": repeat}, decode_keyboard_down)


def decode_input_key(arguments: DataMap) -> InputKeyArguments:
    require_keys(arguments, ("key", "text", "modifiers", "pressed"))
    return InputKeyArguments(
        key=non_empty_string_value(arguments, "key"),
        text=optional_string_value(arguments, "text"),
        modifiers=string_list_value(arguments, "modifiers"),
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


def decode_process_exited(arguments: DataMap) -> ProcessExitedArguments:
    require_keys(arguments, ("tag", "code"), optional=("error",))
    return ProcessExitedArguments(
        tag=string_value(arguments, "tag"),
        code=int_value(arguments, "code"),
        error=optional_string_value(arguments, "error") if "error" in arguments else None,
    )


def decode_window_state(arguments: DataMap) -> WindowStateArguments:
    require_keys(arguments, ("window", "visible", "minimized", "x", "y", "width", "height"))
    return WindowStateArguments(
        window_id=non_empty_string_value(arguments, "window"),
        visible=bool_value(arguments, "visible"),
        minimized=bool_value(arguments, "minimized"),
        x=int_value(arguments, "x"),
        y=int_value(arguments, "y"),
        width=int_value(arguments, "width"),
        height=int_value(arguments, "height"),
    )


def node_geometry_changed(node_id: str, x: int, y: int, width: int, height: int) -> RuntimeEvent:
    """Report where a node built with ``report_geometry`` now is: ``x`` and ``y`` are its top-left corner
    in its window's content, in pixels."""

    arguments = {"node": node_id, "x": x, "y": y, "width": width, "height": height}
    return validated_event(NODE_GEOMETRY_CHANGED, arguments, decode_node_geometry)


def decode_node_geometry(arguments: DataMap) -> NodeGeometryArguments:
    require_keys(arguments, ("node", "x", "y", "width", "height"))
    return NodeGeometryArguments(
        node=non_empty_string_value(arguments, "node"),
        x=int_value(arguments, "x"),
        y=int_value(arguments, "y"),
        width=int_value(arguments, "width"),
        height=int_value(arguments, "height"),
    )


def decode_keyboard_down(arguments: DataMap) -> KeyboardDownArguments:
    require_keys(arguments, ("key",), optional=("mods", "repeat"))
    return KeyboardDownArguments(
        key=non_empty_string_value(arguments, "key"),
        mods=string_list_value(arguments, "mods") if "mods" in arguments else (),
        repeat=bool_value(arguments, "repeat") if "repeat" in arguments else True,
    )


def decode_keyboard_key(arguments: DataMap) -> KeyboardKeyArguments:
    require_keys(arguments, ("key",))
    return KeyboardKeyArguments(key=non_empty_string_value(arguments, "key"))


def decode_keyboard_tap(arguments: DataMap) -> KeyboardTapArguments:
    require_keys(arguments, ("key",), optional=("mods",))
    return KeyboardTapArguments(
        key=non_empty_string_value(arguments, "key"),
        mods=string_list_value(arguments, "mods") if "mods" in arguments else (),
    )


def decode_text(arguments: DataMap) -> TextArguments:
    require_keys(arguments, ("text",))
    return TextArguments(text=string_value(arguments, "text"))


def decode_process_spawn(arguments: DataMap) -> ProcessSpawnArguments:
    require_keys(arguments, ("argv", "tag"), optional=("detached",))
    argv = string_list_value(arguments, "argv")
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
    dispatcher.register_event(WINDOW_STATE_CHANGED, decode_window_state)
    dispatcher.register_event(NODE_GEOMETRY_CHANGED, decode_node_geometry)


def install_engine_handlers(
    dispatcher: Dispatcher,
    *,
    profile_runtime: ProfileRuntime,
    keyboard: KeyboardEffects,
    processes: ProcessEffects,
) -> None:
    """Declare the observed variables, then register engine actions and the handlers that record state.

    Call this before a profile starts so observation handlers run before
    profile callbacks for the same event.
    """

    profile_runtime.declare_observed(OBSERVED_VARIABLES)

    def record_input_key(event: InputKeyArguments) -> MessageResult:
        messages = profile_runtime.set_observed(("input", "keys", event.key), event.pressed)
        active = {name.lower() for name in event.modifiers}
        for lock in _LOCKS:
            messages.extend(profile_runtime.set_observed(("input", "locks", lock), lock in active))
        return messages

    def record_keyboard_status(event: KeyboardStatusArguments) -> MessageResult:
        messages: MessageResult = []
        for name, value in asdict(event).items():
            messages.extend(profile_runtime.set_observed(("keyboard", name), value))
        return messages

    def record_window_state(event: WindowStateArguments) -> MessageResult:
        observed: dict[str, DataValue] = {
            "visible": event.visible,
            "minimized": event.minimized,
            "position": {"x": event.x, "y": event.y},
            "size": {"width": event.width, "height": event.height},
        }
        messages: MessageResult = []
        for name, value in observed.items():
            messages.extend(profile_runtime.set_observed(("windows", event.window_id, name), value))
        return messages

    def record_node_geometry(event: NodeGeometryArguments) -> MessageResult:
        messages = profile_runtime.set_observed(("nodes", event.node, "position"), {"x": event.x, "y": event.y})
        size: dict[str, DataValue] = {"width": event.width, "height": event.height}
        messages.extend(profile_runtime.set_observed(("nodes", event.node, "size"), size))
        return messages

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
    dispatcher.add_event_handler(WINDOW_STATE_CHANGED, record_window_state)
    dispatcher.add_event_handler(NODE_GEOMETRY_CHANGED, record_node_geometry)
    dispatcher.register_action(KEYBOARD_DOWN, decode_keyboard_down, press)
    dispatcher.register_action(KEYBOARD_UP, decode_keyboard_key, release)
    dispatcher.register_action(KEYBOARD_TAP, decode_keyboard_tap, tap)
    dispatcher.register_action(KEYBOARD_TYPE_TEXT, decode_text, type_text)
    dispatcher.register_action(PROCESS_SPAWN, decode_process_spawn, spawn)
    dispatcher.register_action(LOG_INFO, decode_log, log_at(logging.INFO))
    dispatcher.register_action(LOG_WARN, decode_log, log_at(logging.WARNING))
    dispatcher.register_action(LOG_ERROR, decode_log, log_at(logging.ERROR))
