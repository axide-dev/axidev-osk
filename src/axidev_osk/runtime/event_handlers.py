"""Runtime-owned handlers for window actions, display recovery, and pointer drags.

These adapt queue messages into calls on objects the runtime owns: the window
manager and services. They contain no profile policy; profiles decide when to
send these actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ..messages import MessageResult
from .app_messages import (
    APP_ACTION_DECODERS,
    DISPLAY_CONFIGURATION_CHANGED,
    POINTER_MOTION_OBSERVED,
    WINDOW_CLICK,
    WINDOW_CLOSE,
    WINDOW_DRAG_ENDED,
    WINDOW_DRAG_STARTED,
    WINDOW_HIDE,
    WINDOW_MOVE_BY,
    WINDOW_RESIZE_BY,
    WINDOW_SHOW,
    PointerMotionObservedArguments,
    WindowArguments,
    WindowButtonArguments,
    WindowClickArguments,
    WindowDeltaArguments,
    window_dragged,
)
from .decoding import EmptyArguments
from .dispatcher import ACTION_FAILED, ActionFailedArguments

if TYPE_CHECKING:
    from .dispatcher import Dispatcher
    from .window_manager import WindowManager


def register_window_actions(
    dispatcher: "Dispatcher",
    windows: "WindowManager",
    relative_pointer: "RelativePointer | None",
) -> None:
    """Register the window actions profiles send, routed to the window manager.

    A moved layer-shell surface is committed through the relative-pointer
    service in the same step, so a move is visible at once.
    """

    def show(arguments: WindowArguments) -> MessageResult:
        windows.show(arguments.window_id)
        return []

    def hide(arguments: WindowArguments) -> MessageResult:
        windows.hide(arguments.window_id)
        return []

    def close(arguments: WindowArguments) -> MessageResult:
        windows.close(arguments.window_id)
        return []

    def move_by(arguments: WindowDeltaArguments) -> MessageResult:
        window = windows.get(arguments.window_id)
        if window is None:
            return []
        windows.move_by(arguments.window_id, arguments.dx, arguments.dy)
        if relative_pointer is not None:
            relative_pointer.commit_surface(int(window.winId()))
        return []

    def resize_by(arguments: WindowDeltaArguments) -> MessageResult:
        windows.resize_by(arguments.window_id, arguments.dx, arguments.dy)
        return []

    def click(arguments: WindowClickArguments) -> MessageResult:
        windows.click(arguments.window_id, arguments.x, arguments.y, arguments.button)
        return []

    dispatcher.register_action(WINDOW_SHOW, APP_ACTION_DECODERS[WINDOW_SHOW], show)
    dispatcher.register_action(WINDOW_HIDE, APP_ACTION_DECODERS[WINDOW_HIDE], hide)
    dispatcher.register_action(WINDOW_CLOSE, APP_ACTION_DECODERS[WINDOW_CLOSE], close)
    dispatcher.register_action(WINDOW_MOVE_BY, APP_ACTION_DECODERS[WINDOW_MOVE_BY], move_by)
    dispatcher.register_action(WINDOW_RESIZE_BY, APP_ACTION_DECODERS[WINDOW_RESIZE_BY], resize_by)
    dispatcher.register_action(WINDOW_CLICK, APP_ACTION_DECODERS[WINDOW_CLICK], click)


def register_display_recovery(dispatcher: "Dispatcher", windows: "WindowManager") -> None:
    """Recover windows after connected outputs change; services follow the same event themselves."""

    def recover(event: EmptyArguments) -> MessageResult:
        del event
        windows.refresh_screen_configuration()
        return []

    dispatcher.add_event_handler(DISPLAY_CONFIGURATION_CHANGED, recover)


class RelativePointer(Protocol):
    """The service that collects compositor pointer motion while a layer-shell window is dragged."""

    def begin_drag(self) -> None: ...

    def end_drag(self) -> None: ...

    def commit_surface(self, surface: int) -> None: ...


class PointerDragRouter:
    """Own one layer-shell title-bar drag and report raw pointer motion as ``window.dragged``.

    The profile decides what a drag does; the standard library moves the
    window with ``window.move_by``. A failing move of the dragged window ends
    the drag.
    """

    def __init__(self, windows: "WindowManager", relative_pointer: RelativePointer | None) -> None:
        self._windows = windows
        self._relative_pointer = relative_pointer
        self._window_id: str | None = None
        self._button = ""
        self._remainder = (0.0, 0.0)

    @property
    def window_id(self) -> str | None:
        """The window being dragged, if any."""

        return self._window_id

    def register(self, dispatcher: "Dispatcher") -> None:
        dispatcher.add_event_handler(WINDOW_DRAG_STARTED, self._drag_started)
        dispatcher.add_event_handler(WINDOW_DRAG_ENDED, self._drag_ended)
        dispatcher.add_event_handler(POINTER_MOTION_OBSERVED, self._motion_observed)
        dispatcher.add_event_handler(ACTION_FAILED, self._action_failed)

    def _drag_started(self, event: WindowButtonArguments) -> MessageResult:
        if self._window_id is not None:
            self._set_dragging(False)
        self._window_id = event.window_id
        self._button = event.button
        self._remainder = (0.0, 0.0)
        self._set_dragging(True)
        return []

    def _drag_ended(self, event: WindowArguments) -> MessageResult:
        if self._window_id == event.window_id:
            self._stop()
        return []

    def _motion_observed(self, event: PointerMotionObservedArguments) -> MessageResult:
        """Turn accumulated raw pointer motion into whole-pixel window moves."""

        window_id = self._window_id
        if window_id is None:
            return []
        window = self._windows.get(window_id)
        if window is None or not window.isVisible():
            self._stop()
            return []
        total_x = self._remainder[0] + event.dx
        total_y = self._remainder[1] + event.dy
        dx = int(total_x)
        dy = int(total_y)
        self._remainder = (total_x - dx, total_y - dy)
        if not dx and not dy:
            return []
        return [window_dragged(window_id, dx, dy, self._button)]

    def _action_failed(self, event: ActionFailedArguments) -> MessageResult:
        """Stop the drag when moving the dragged window fails."""

        if event.action == WINDOW_MOVE_BY and event.arguments.get("window") == self._window_id:
            self._stop()
        return []

    def _stop(self) -> None:
        self._set_dragging(False)
        self._window_id = None
        self._remainder = (0.0, 0.0)

    def _set_dragging(self, enabled: bool) -> None:
        """Start or stop relative-pointer collection."""

        if self._relative_pointer is None:
            return
        if enabled:
            self._relative_pointer.begin_drag()
        else:
            self._relative_pointer.end_drag()
