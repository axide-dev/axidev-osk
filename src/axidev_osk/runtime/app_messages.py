"""Messages the application runtime handles or sends.

These cover windows, title-bar drags, displays, hot corners, the lock-screen
panel, profile switching, quit requests, second-launch activation, and Linux permission setup.
``build_engine`` registers every event here, so profiles can handle them; the
application registers the action handlers, because they need the objects it
owns. Messages the engine itself handles (keyboard, processes, logging,
observed state) live in ``engine_messages``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

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
from .event_fields import profile_window, samples

if TYPE_CHECKING:
    from .dispatcher import Dispatcher

APP_ACTIVATED = "app.activated"
APP_QUIT_REQUESTED = "app.quit_requested"
DISPLAY_CONFIGURATION_CHANGED = "display.configuration_changed"
HOT_CORNER_TRIGGERED = "hot_corner.triggered"
LINUX_PERMISSION_SETUP_OPENED = "linux.permission_setup_opened"
POINTER_MOTION_OBSERVED = "pointer.motion_observed"
SECURE_INPUT_PANEL_PREPARED = "secure_input_panel.prepared"
SECURE_INPUT_PANEL_RELEASED = "secure_input_panel.released"
WINDOW_CLOSE_REQUESTED = "window.close_requested"
WINDOW_DRAG_ENDED = "window.drag_ended"
WINDOW_DRAG_STARTED = "window.drag_started"

APP_QUIT = "app.quit"
PROFILE_SWITCH = "profile.switch"
PROFILE_START = "profile.start"
LINUX_OPEN_PERMISSION_SETUP = "linux.open_permission_setup"
SECURE_INPUT_PANEL_PREPARE = "secure_input_panel.prepare"
SECURE_INPUT_PANEL_RELEASE = "secure_input_panel.release"
WINDOW_CLOSE = "window.close"
WINDOW_HIDE = "window.hide"
WINDOW_MOVE_BY = "window.move_by"
WINDOW_SHOW = "window.show"


class ScreenCorner(str, Enum):
    """The screen corners a ``hot_corners`` attachment watches and ``hot_corner.triggered`` names."""

    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


HOT_CORNERS = tuple(corner.value for corner in ScreenCorner)


class QuitReason(str, Enum):
    """Why the application asks a profile before quitting, as ``app.quit_requested`` reports it."""

    SIGNAL = "signal"
    STDIN_CLOSED = "stdin_closed"
    WINDOW_CLOSED = "window_closed"


QUIT_REASONS = tuple(reason.value for reason in QuitReason)


@dataclass(frozen=True, slots=True)
class HotCornerTriggeredArguments:
    corner: str = samples(*HOT_CORNERS)


@dataclass(frozen=True, slots=True)
class PointerMotionObservedArguments:
    dx: float = samples(0.0)
    dy: float = samples(0.0)


@dataclass(frozen=True, slots=True)
class QuitRequestedArguments:
    reason: str = samples(*QUIT_REASONS)


@dataclass(frozen=True, slots=True)
class PermissionSetupOpenedArguments:
    opened: bool


@dataclass(frozen=True, slots=True)
class AppQuitArguments:
    exit_code: int


@dataclass(frozen=True, slots=True)
class ProfileSwitchArguments:
    profile: str


@dataclass(frozen=True, slots=True)
class WindowArguments:
    window_id: str = profile_window(key="window")


@dataclass(frozen=True, slots=True)
class WindowMoveByArguments:
    window_id: str
    dx: int
    dy: int


def app_activated() -> RuntimeEvent:
    return validated_event(APP_ACTIVATED, {}, decode_empty)


def app_quit_requested(reason: QuitReason) -> RuntimeEvent:
    return validated_event(APP_QUIT_REQUESTED, {"reason": reason.value}, decode_quit_requested)


def display_configuration_changed() -> RuntimeEvent:
    return validated_event(DISPLAY_CONFIGURATION_CHANGED, {}, decode_empty)


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


def window_close_requested(window_id: str) -> RuntimeEvent:
    return validated_event(WINDOW_CLOSE_REQUESTED, {"window": window_id}, decode_window)


def window_drag_started(window_id: str) -> RuntimeEvent:
    return validated_event(WINDOW_DRAG_STARTED, {"window": window_id}, decode_window)


def window_drag_ended(window_id: str) -> RuntimeEvent:
    return validated_event(WINDOW_DRAG_ENDED, {"window": window_id}, decode_window)


def app_quit(exit_code: int = 0) -> RuntimeAction:
    return validated_action(APP_QUIT, {"exit_code": exit_code}, decode_app_quit)


def profile_switch(profile: str) -> RuntimeAction:
    return validated_action(PROFILE_SWITCH, {"profile": profile}, decode_profile_switch)


def profile_start() -> RuntimeAction:
    """Start the profile a switch tore the running one down for; the switch sends it."""

    return validated_action(PROFILE_START, {}, decode_empty)


def window_show(window_id: str) -> RuntimeAction:
    return validated_action(WINDOW_SHOW, {"window": window_id}, decode_window)


def window_hide(window_id: str) -> RuntimeAction:
    return validated_action(WINDOW_HIDE, {"window": window_id}, decode_window)


def window_close(window_id: str) -> RuntimeAction:
    return validated_action(WINDOW_CLOSE, {"window": window_id}, decode_window)


def window_move_by(window_id: str, dx: int, dy: int) -> RuntimeAction:
    return validated_action(WINDOW_MOVE_BY, {"window": window_id, "dx": dx, "dy": dy}, decode_window_move_by)


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


def decode_profile_switch(arguments: DataMap) -> ProfileSwitchArguments:
    require_keys(arguments, ("profile",))
    return ProfileSwitchArguments(profile=non_empty_string_value(arguments, "profile"))


def decode_window(arguments: DataMap) -> WindowArguments:
    require_keys(arguments, ("window",))
    return WindowArguments(window_id=non_empty_string_value(arguments, "window"))


def decode_window_move_by(arguments: DataMap) -> WindowMoveByArguments:
    require_keys(arguments, ("window", "dx", "dy"))
    return WindowMoveByArguments(
        window_id=non_empty_string_value(arguments, "window"),
        dx=int_value(arguments, "dx"),
        dy=int_value(arguments, "dy"),
    )


# The application's actions and their decoders, listed once: the application registers them from here and
# ``axidev-osk check`` decodes the actions callbacks return with them.
APP_ACTION_DECODERS: dict[str, Callable[[DataMap], Any]] = {
    APP_QUIT: decode_app_quit,
    LINUX_OPEN_PERMISSION_SETUP: decode_empty,
    PROFILE_START: decode_empty,
    PROFILE_SWITCH: decode_profile_switch,
    SECURE_INPUT_PANEL_PREPARE: decode_empty,
    SECURE_INPUT_PANEL_RELEASE: decode_empty,
    WINDOW_CLOSE: decode_window,
    WINDOW_HIDE: decode_window,
    WINDOW_MOVE_BY: decode_window_move_by,
    WINDOW_SHOW: decode_window,
}
"""Every action the application runtime registers, with its decoder.

The application registers each of these with its handler, and the config
check decodes them without the application.
"""


def register_app_events(dispatcher: "Dispatcher") -> None:
    """Register every event the application runtime sends."""

    dispatcher.register_event(APP_ACTIVATED, decode_empty)
    dispatcher.register_event(APP_QUIT_REQUESTED, decode_quit_requested)
    dispatcher.register_event(DISPLAY_CONFIGURATION_CHANGED, decode_empty)
    dispatcher.register_event(HOT_CORNER_TRIGGERED, decode_hot_corner_triggered)
    dispatcher.register_event(LINUX_PERMISSION_SETUP_OPENED, decode_permission_setup_opened)
    dispatcher.register_event(POINTER_MOTION_OBSERVED, decode_pointer_motion_observed)
    dispatcher.register_event(SECURE_INPUT_PANEL_PREPARED, decode_empty)
    dispatcher.register_event(SECURE_INPUT_PANEL_RELEASED, decode_empty)
    dispatcher.register_event(WINDOW_CLOSE_REQUESTED, decode_window)
    dispatcher.register_event(WINDOW_DRAG_ENDED, decode_window)
    dispatcher.register_event(WINDOW_DRAG_STARTED, decode_window)
