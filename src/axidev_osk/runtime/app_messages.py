"""Messages the application runtime handles or sends.

These cover windows, title-bar and resize-grip drags, dwell clicks, displays, hot corners, the lock-screen
panel, quit requests, second-launch activation, and Linux permission setup.
``build_engine`` registers every event here, so profiles can handle them; the
application registers the action handlers, because they need the objects it
owns. Messages the engine itself handles (keyboard, processes, logging,
observed state) live in ``engine_messages``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..messages import DataMap, RuntimeAction, RuntimeEvent
from .decoding import (
    bool_value,
    decode_empty,
    int_value,
    non_empty_string_value,
    number_value,
    require_keys,
    string_value,
    validated_action,
    validated_event,
)

if TYPE_CHECKING:
    from .dispatcher import Dispatcher

APP_ACTIVATED = "app.activated"
APP_QUIT_REQUESTED = "app.quit_requested"
DWELL_COMPLETED = "dwell.completed"
HOT_CORNER_ENTERED = "hot_corner.entered"
HOT_CORNER_LEFT = "hot_corner.left"
HOT_CORNER_TRIGGERED = "hot_corner.triggered"
LINUX_PERMISSION_SETUP_OPENED = "linux.permission_setup_opened"
POINTER_MOTION_OBSERVED = "pointer.motion_observed"
SECURE_INPUT_PANEL_PREPARED = "secure_input_panel.prepared"
SECURE_INPUT_PANEL_RELEASED = "secure_input_panel.released"
WINDOW_CLOSE_REQUESTED = "window.close_requested"
WINDOW_DRAG_ENDED = "window.drag_ended"
WINDOW_DRAG_STARTED = "window.drag_started"
WINDOW_DRAGGED = "window.dragged"
WINDOW_RESIZE_DRAGGED = "window.resize_dragged"
WINDOW_RESIZE_DRAG_ENDED = "window.resize_drag_ended"
WINDOW_RESIZE_DRAG_STARTED = "window.resize_drag_started"

APP_QUIT = "app.quit"
LINUX_OPEN_PERMISSION_SETUP = "linux.open_permission_setup"
SECURE_INPUT_PANEL_PREPARE = "secure_input_panel.prepare"
SECURE_INPUT_PANEL_RELEASE = "secure_input_panel.release"
WINDOW_CLICK = "window.click"
WINDOW_CLOSE = "window.close"
WINDOW_HIDE = "window.hide"
WINDOW_MOVE_BY = "window.move_by"
WINDOW_MOVE_TO = "window.move_to"
WINDOW_RESIZE_BY = "window.resize_by"
WINDOW_RESIZE_TO = "window.resize_to"
WINDOW_SHOW = "window.show"


@dataclass(frozen=True, slots=True)
class HotCornerTriggeredArguments:
    corner: str


@dataclass(frozen=True, slots=True)
class PointerMotionObservedArguments:
    dx: float
    dy: float


@dataclass(frozen=True, slots=True)
class QuitRequestedArguments:
    reason: str


@dataclass(frozen=True, slots=True)
class PermissionSetupOpenedArguments:
    opened: bool


@dataclass(frozen=True, slots=True)
class AppQuitArguments:
    exit_code: int


@dataclass(frozen=True, slots=True)
class WindowArguments:
    window_id: str


@dataclass(frozen=True, slots=True)
class WindowSizeArguments:
    """A window and a size in pixels."""

    window_id: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class WindowDeltaArguments:
    """A window and a distance in pixels: a drag, or how far to move or resize it."""

    window_id: str
    dx: int
    dy: int


@dataclass(frozen=True, slots=True)
class WindowDragArguments:
    """How far a window's title bar or resize grip was dragged, and with which mouse button."""

    window_id: str
    dx: int
    dy: int
    button: str


@dataclass(frozen=True, slots=True)
class WindowButtonArguments:
    """A window and the mouse button behind what happened to it."""

    window_id: str
    button: str


@dataclass(frozen=True, slots=True)
class WindowCloseRequestedArguments:
    """A request to close a window: ``button`` names the mouse button on its close button, or is ``None``
    when the system asked."""

    window_id: str
    button: str | None


@dataclass(frozen=True, slots=True)
class WindowPointArguments:
    """A window and a point on the screen, in pixels."""

    window_id: str
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class WindowClickArguments:
    window_id: str
    x: int
    y: int
    button: str


def app_activated() -> RuntimeEvent:
    return validated_event(APP_ACTIVATED, {}, decode_empty)


def app_quit_requested(reason: str) -> RuntimeEvent:
    return validated_event(APP_QUIT_REQUESTED, {"reason": reason}, decode_quit_requested)


def hot_corner_entered(corner: str) -> RuntimeEvent:
    return validated_event(HOT_CORNER_ENTERED, {"corner": corner}, decode_hot_corner_triggered)


def hot_corner_left(corner: str) -> RuntimeEvent:
    return validated_event(HOT_CORNER_LEFT, {"corner": corner}, decode_hot_corner_triggered)


def hot_corner_triggered(corner: str) -> RuntimeEvent:
    return validated_event(HOT_CORNER_TRIGGERED, {"corner": corner}, decode_hot_corner_triggered)


def linux_permission_setup_opened(opened: bool) -> RuntimeEvent:
    return validated_event(LINUX_PERMISSION_SETUP_OPENED, {"opened": opened}, decode_permission_setup_opened)


def pointer_motion_observed(dx: float, dy: float) -> RuntimeEvent:
    return validated_event(POINTER_MOTION_OBSERVED, {"dx": dx, "dy": dy}, decode_pointer_motion_observed)


def secure_input_panel_prepared() -> RuntimeEvent:
    return validated_event(SECURE_INPUT_PANEL_PREPARED, {}, decode_empty)


def secure_input_panel_released() -> RuntimeEvent:
    return validated_event(SECURE_INPUT_PANEL_RELEASED, {}, decode_empty)


def window_close_requested(window_id: str, button: str | None = None) -> RuntimeEvent:
    return validated_event(
        WINDOW_CLOSE_REQUESTED, {"window": window_id, "button": button}, decode_window_close_requested
    )


def window_drag_started(window_id: str, button: str) -> RuntimeEvent:
    return validated_event(WINDOW_DRAG_STARTED, {"window": window_id, "button": button}, decode_window_button)


def window_dragged(window_id: str, dx: int, dy: int, button: str) -> RuntimeEvent:
    arguments = {"window": window_id, "dx": dx, "dy": dy, "button": button}
    return validated_event(WINDOW_DRAGGED, arguments, decode_window_drag)


def window_resize_dragged(window_id: str, dx: int, dy: int, button: str) -> RuntimeEvent:
    arguments = {"window": window_id, "dx": dx, "dy": dy, "button": button}
    return validated_event(WINDOW_RESIZE_DRAGGED, arguments, decode_window_drag)


def window_resize_drag_started(window_id: str, button: str) -> RuntimeEvent:
    return validated_event(WINDOW_RESIZE_DRAG_STARTED, {"window": window_id, "button": button}, decode_window_button)


def window_resize_drag_ended(window_id: str) -> RuntimeEvent:
    return validated_event(WINDOW_RESIZE_DRAG_ENDED, {"window": window_id}, decode_window)


def dwell_completed(window_id: str, x: int, y: int) -> RuntimeEvent:
    return validated_event(DWELL_COMPLETED, {"window": window_id, "x": x, "y": y}, decode_window_point)


def window_drag_ended(window_id: str) -> RuntimeEvent:
    return validated_event(WINDOW_DRAG_ENDED, {"window": window_id}, decode_window)


def app_quit(exit_code: int = 0) -> RuntimeAction:
    return validated_action(APP_QUIT, {"exit_code": exit_code}, decode_app_quit)


def window_show(window_id: str) -> RuntimeAction:
    return validated_action(WINDOW_SHOW, {"window": window_id}, decode_window)


def window_hide(window_id: str) -> RuntimeAction:
    return validated_action(WINDOW_HIDE, {"window": window_id}, decode_window)


def window_close(window_id: str) -> RuntimeAction:
    return validated_action(WINDOW_CLOSE, {"window": window_id}, decode_window)


def window_move_by(window_id: str, dx: int, dy: int) -> RuntimeAction:
    return validated_action(WINDOW_MOVE_BY, {"window": window_id, "dx": dx, "dy": dy}, decode_window_delta)


def window_resize_by(window_id: str, dx: int, dy: int) -> RuntimeAction:
    return validated_action(WINDOW_RESIZE_BY, {"window": window_id, "dx": dx, "dy": dy}, decode_window_delta)


def window_move_to(window_id: str, x: int, y: int) -> RuntimeAction:
    """Ask to put a window's top-left corner at the screen point ``(x, y)``."""

    return validated_action(WINDOW_MOVE_TO, {"window": window_id, "x": x, "y": y}, decode_window_point)


def window_resize_to(window_id: str, width: int, height: int) -> RuntimeAction:
    """Ask to give a window this size, never below its minimum size."""

    return validated_action(
        WINDOW_RESIZE_TO, {"window": window_id, "width": width, "height": height}, decode_window_size
    )


def window_click(window_id: str, x: int, y: int, button: str = "left") -> RuntimeAction:
    return validated_action(WINDOW_CLICK, {"window": window_id, "x": x, "y": y, "button": button}, decode_window_click)


def secure_input_panel_prepare() -> RuntimeAction:
    return validated_action(SECURE_INPUT_PANEL_PREPARE, {}, decode_empty)


def secure_input_panel_release() -> RuntimeAction:
    return validated_action(SECURE_INPUT_PANEL_RELEASE, {}, decode_empty)


def decode_hot_corner_triggered(arguments: DataMap) -> HotCornerTriggeredArguments:
    require_keys(arguments, ("corner",))
    return HotCornerTriggeredArguments(corner=string_value(arguments, "corner"))


def decode_pointer_motion_observed(arguments: DataMap) -> PointerMotionObservedArguments:
    require_keys(arguments, ("dx", "dy"))
    return PointerMotionObservedArguments(dx=number_value(arguments, "dx"), dy=number_value(arguments, "dy"))


def decode_quit_requested(arguments: DataMap) -> QuitRequestedArguments:
    require_keys(arguments, ("reason",))
    return QuitRequestedArguments(reason=non_empty_string_value(arguments, "reason"))


def decode_permission_setup_opened(arguments: DataMap) -> PermissionSetupOpenedArguments:
    require_keys(arguments, ("opened",))
    return PermissionSetupOpenedArguments(opened=bool_value(arguments, "opened"))


def decode_app_quit(arguments: DataMap) -> AppQuitArguments:
    require_keys(arguments, (), optional=("exit_code",))
    return AppQuitArguments(exit_code=int_value(arguments, "exit_code") if "exit_code" in arguments else 0)


def decode_window(arguments: DataMap) -> WindowArguments:
    require_keys(arguments, ("window",))
    return WindowArguments(window_id=non_empty_string_value(arguments, "window"))


def decode_window_delta(arguments: DataMap) -> WindowDeltaArguments:
    require_keys(arguments, ("window", "dx", "dy"))
    return WindowDeltaArguments(
        window_id=non_empty_string_value(arguments, "window"),
        dx=int_value(arguments, "dx"),
        dy=int_value(arguments, "dy"),
    )


def decode_window_size(arguments: DataMap) -> WindowSizeArguments:
    require_keys(arguments, ("window", "width", "height"))
    width, height = int_value(arguments, "width"), int_value(arguments, "height")
    if width < 0 or height < 0:
        raise ValueError("width and height must be at least 0")
    return WindowSizeArguments(window_id=non_empty_string_value(arguments, "window"), width=width, height=height)


def decode_window_drag(arguments: DataMap) -> WindowDragArguments:
    require_keys(arguments, ("window", "dx", "dy", "button"))
    return WindowDragArguments(
        window_id=non_empty_string_value(arguments, "window"),
        dx=int_value(arguments, "dx"),
        dy=int_value(arguments, "dy"),
        button=non_empty_string_value(arguments, "button"),
    )


def decode_window_button(arguments: DataMap) -> WindowButtonArguments:
    require_keys(arguments, ("window", "button"))
    return WindowButtonArguments(
        window_id=non_empty_string_value(arguments, "window"),
        button=non_empty_string_value(arguments, "button"),
    )


def decode_window_close_requested(arguments: DataMap) -> WindowCloseRequestedArguments:
    require_keys(arguments, ("window",), optional=("button",))
    button = arguments.get("button")
    return WindowCloseRequestedArguments(
        window_id=non_empty_string_value(arguments, "window"),
        button=None if button is None else non_empty_string_value(arguments, "button"),
    )


def decode_window_point(arguments: DataMap) -> WindowPointArguments:
    require_keys(arguments, ("window", "x", "y"))
    return WindowPointArguments(
        window_id=non_empty_string_value(arguments, "window"),
        x=int_value(arguments, "x"),
        y=int_value(arguments, "y"),
    )


def decode_window_click(arguments: DataMap) -> WindowClickArguments:
    require_keys(arguments, ("window", "x", "y"), optional=("button",))
    return WindowClickArguments(
        window_id=non_empty_string_value(arguments, "window"),
        x=int_value(arguments, "x"),
        y=int_value(arguments, "y"),
        button=non_empty_string_value(arguments, "button") if "button" in arguments else "left",
    )


def register_app_events(dispatcher: "Dispatcher") -> None:
    """Register every event the application runtime sends."""

    dispatcher.register_event(APP_ACTIVATED, decode_empty)
    dispatcher.register_event(APP_QUIT_REQUESTED, decode_quit_requested)
    dispatcher.register_event(DWELL_COMPLETED, decode_window_point)
    dispatcher.register_event(HOT_CORNER_ENTERED, decode_hot_corner_triggered)
    dispatcher.register_event(HOT_CORNER_LEFT, decode_hot_corner_triggered)
    dispatcher.register_event(HOT_CORNER_TRIGGERED, decode_hot_corner_triggered)
    dispatcher.register_event(LINUX_PERMISSION_SETUP_OPENED, decode_permission_setup_opened)
    dispatcher.register_event(POINTER_MOTION_OBSERVED, decode_pointer_motion_observed)
    dispatcher.register_event(SECURE_INPUT_PANEL_PREPARED, decode_empty)
    dispatcher.register_event(SECURE_INPUT_PANEL_RELEASED, decode_empty)
    dispatcher.register_event(WINDOW_CLOSE_REQUESTED, decode_window_close_requested)
    dispatcher.register_event(WINDOW_DRAG_ENDED, decode_window)
    dispatcher.register_event(WINDOW_DRAG_STARTED, decode_window_button)
    dispatcher.register_event(WINDOW_DRAGGED, decode_window_drag)
    dispatcher.register_event(WINDOW_RESIZE_DRAGGED, decode_window_drag)
    dispatcher.register_event(WINDOW_RESIZE_DRAG_ENDED, decode_window)
    dispatcher.register_event(WINDOW_RESIZE_DRAG_STARTED, decode_window_button)
