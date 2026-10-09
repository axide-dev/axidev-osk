"""Typed constructors and decoders for built-in engine actions owned by the runtime.

Keyboard, process, and log actions live in ``engine_messages``; ``state.set``
lives in ``profile_runtime``; ``dwell.set_enabled`` lives with attachments.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..messages import DataMap, RuntimeAction
from .decoding import int_value, non_empty_string_value, number_value, require_keys, string_set_value

APP_QUIT = "app.quit"
LINUX_OPEN_PERMISSION_SETUP = "linux.open_permission_setup"
SECURE_INPUT_PANEL_PREPARE = "secure_input_panel.prepare"
SECURE_INPUT_PANEL_RELEASE = "secure_input_panel.release"
WINDOW_BLOCK_INPUT = "window.block_input"
WINDOW_CLOSE = "window.close"
WINDOW_HIDE = "window.hide"
WINDOW_MOVE_BY = "window.move_by"
WINDOW_SET_OPACITY = "window.set_opacity"
WINDOW_SHOW = "window.show"
WINDOW_UNBLOCK_INPUT = "window.unblock_input"


@dataclass(frozen=True, slots=True)
class AppQuitArguments:
    exit_code: int


@dataclass(frozen=True, slots=True)
class NoArguments:
    pass


@dataclass(frozen=True, slots=True)
class WindowArguments:
    window_id: str


@dataclass(frozen=True, slots=True)
class WindowOpacityArguments:
    window_id: str
    opacity: float


@dataclass(frozen=True, slots=True)
class WindowBlockInputArguments:
    window_id: str
    allowed_node_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class WindowMoveByArguments:
    window_id: str
    dx: int
    dy: int


def app_quit(exit_code: int = 0) -> RuntimeAction:
    return _validated_action(APP_QUIT, {"exit_code": exit_code}, decode_app_quit)


def window_show(window_id: str) -> RuntimeAction:
    return _validated_action(WINDOW_SHOW, {"window": window_id}, decode_window)


def window_hide(window_id: str) -> RuntimeAction:
    return _validated_action(WINDOW_HIDE, {"window": window_id}, decode_window)


def window_close(window_id: str) -> RuntimeAction:
    return _validated_action(WINDOW_CLOSE, {"window": window_id}, decode_window)


def window_move_by(window_id: str, dx: int, dy: int) -> RuntimeAction:
    return _validated_action(WINDOW_MOVE_BY, {"window": window_id, "dx": dx, "dy": dy}, decode_window_move_by)


def secure_input_panel_prepare() -> RuntimeAction:
    return _validated_action(SECURE_INPUT_PANEL_PREPARE, {}, decode_no_arguments)


def secure_input_panel_release() -> RuntimeAction:
    return _validated_action(SECURE_INPUT_PANEL_RELEASE, {}, decode_no_arguments)


def decode_app_quit(arguments: DataMap) -> AppQuitArguments:
    require_keys(arguments, (), optional=("exit_code",))
    return AppQuitArguments(exit_code=int_value(arguments, "exit_code") if "exit_code" in arguments else 0)


def decode_no_arguments(arguments: DataMap) -> NoArguments:
    require_keys(arguments, ())
    return NoArguments()


def decode_window(arguments: DataMap) -> WindowArguments:
    require_keys(arguments, ("window",))
    return WindowArguments(window_id=non_empty_string_value(arguments, "window"))


def decode_window_set_opacity(arguments: DataMap) -> WindowOpacityArguments:
    require_keys(arguments, ("window", "opacity"))
    opacity = number_value(arguments, "opacity")
    if not 0.0 <= opacity <= 1.0:
        raise ValueError("Argument 'opacity' must be between 0.0 and 1.0")
    return WindowOpacityArguments(window_id=non_empty_string_value(arguments, "window"), opacity=opacity)


def decode_window_block_input(arguments: DataMap) -> WindowBlockInputArguments:
    require_keys(arguments, ("window",), optional=("except",))
    return WindowBlockInputArguments(
        window_id=non_empty_string_value(arguments, "window"),
        allowed_node_ids=string_set_value(arguments, "except") if "except" in arguments else frozenset(),
    )


def decode_window_move_by(arguments: DataMap) -> WindowMoveByArguments:
    require_keys(arguments, ("window", "dx", "dy"))
    return WindowMoveByArguments(
        window_id=non_empty_string_value(arguments, "window"),
        dx=int_value(arguments, "dx"),
        dy=int_value(arguments, "dy"),
    )


def _validated_action(
    name: str,
    arguments: DataMap,
    decoder: Callable[[DataMap], object],
) -> RuntimeAction:
    action = RuntimeAction(name, arguments)
    decoder(action.arguments)
    return action
