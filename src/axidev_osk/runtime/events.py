"""Typed constructors and decoders for built-in engine events.

Profile-facing observation events live in ``engine_messages``; state and
callback events live in ``profile_runtime``; node events are registered by
node kinds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..messages import DataMap, RuntimeEvent
from .decoding import map_value, non_empty_string_value, number_value, require_keys, string_value

if TYPE_CHECKING:
    from .dispatcher import Dispatcher

ACTION_FAILED = "action.failed"
APP_ACTIVATED = "app.activated"
DISPLAY_CONFIGURATION_CHANGED = "display.configuration_changed"
HOT_CORNER_TRIGGERED = "hot_corner.triggered"
POINTER_MOTION_OBSERVED = "pointer.motion_observed"
SECURE_INPUT_PANEL_PREPARED = "secure_input_panel.prepared"
SECURE_INPUT_PANEL_RELEASED = "secure_input_panel.released"
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
class NoEventArguments:
    pass


@dataclass(frozen=True, slots=True)
class HotCornerTriggeredArguments:
    corner: str


@dataclass(frozen=True, slots=True)
class PointerMotionObservedArguments:
    dx: float
    dy: float


@dataclass(frozen=True, slots=True)
class WindowEventArguments:
    window_id: str



def app_activated() -> RuntimeEvent:
    return RuntimeEvent(APP_ACTIVATED, {})


def display_configuration_changed() -> RuntimeEvent:
    return RuntimeEvent(DISPLAY_CONFIGURATION_CHANGED, {})


def hot_corner_triggered(corner: str) -> RuntimeEvent:
    return RuntimeEvent(HOT_CORNER_TRIGGERED, {"corner": corner})


def pointer_motion_observed(dx: float, dy: float) -> RuntimeEvent:
    return RuntimeEvent(POINTER_MOTION_OBSERVED, {"dx": dx, "dy": dy})


def secure_input_panel_prepared() -> RuntimeEvent:
    return RuntimeEvent(SECURE_INPUT_PANEL_PREPARED, {})


def secure_input_panel_released() -> RuntimeEvent:
    return RuntimeEvent(SECURE_INPUT_PANEL_RELEASED, {})


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


def decode_no_event_arguments(arguments: DataMap) -> NoEventArguments:
    require_keys(arguments, ())
    return NoEventArguments()


def decode_hot_corner_triggered(arguments: DataMap) -> HotCornerTriggeredArguments:
    require_keys(arguments, ("corner",))
    return HotCornerTriggeredArguments(corner=string_value(arguments, "corner"))


def decode_pointer_motion_observed(arguments: DataMap) -> PointerMotionObservedArguments:
    require_keys(arguments, ("dx", "dy"))
    return PointerMotionObservedArguments(dx=number_value(arguments, "dx"), dy=number_value(arguments, "dy"))


def decode_window_event(arguments: DataMap) -> WindowEventArguments:
    require_keys(arguments, ("window",))
    return WindowEventArguments(window_id=non_empty_string_value(arguments, "window"))


def register_builtin_events(dispatcher: "Dispatcher") -> None:
    """Register every built-in engine event decoder."""

    dispatcher.register_event(ACTION_FAILED, decode_action_failed)
    dispatcher.register_event(APP_ACTIVATED, decode_no_event_arguments)
    dispatcher.register_event(DISPLAY_CONFIGURATION_CHANGED, decode_no_event_arguments)
    dispatcher.register_event(HOT_CORNER_TRIGGERED, decode_hot_corner_triggered)
    dispatcher.register_event(POINTER_MOTION_OBSERVED, decode_pointer_motion_observed)
    dispatcher.register_event(SECURE_INPUT_PANEL_PREPARED, decode_no_event_arguments)
    dispatcher.register_event(SECURE_INPUT_PANEL_RELEASED, decode_no_event_arguments)
    dispatcher.register_event(WINDOW_CLOSE_REQUESTED, decode_window_event)
    dispatcher.register_event(WINDOW_DRAG_ENDED, decode_window_event)
    dispatcher.register_event(WINDOW_DRAG_STARTED, decode_window_event)
