"""Runtime-owned handlers for window actions, display recovery, and pointer drags.

These adapt queue messages into calls on objects the runtime owns: the window
manager and services. They contain no profile policy; profiles decide when to
send these actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from ..messages import MessageResult
from .app_messages import (
    DISPLAY_CONFIGURATION_CHANGED,
    POINTER_MOTION_OBSERVED,
    WINDOW_BLOCK_INPUT,
    WINDOW_CLOSE,
    WINDOW_DRAG_ENDED,
    WINDOW_DRAG_STARTED,
    WINDOW_HIDE,
    WINDOW_MOVE_BY,
    WINDOW_SET_OPACITY,
    WINDOW_SHOW,
    WINDOW_UNBLOCK_INPUT,
    PointerMotionObservedArguments,
    WindowArguments,
    WindowBlockInputArguments,
    WindowMoveByArguments,
    WindowOpacityArguments,
    decode_window,
    decode_window_block_input,
    decode_window_move_by,
    decode_window_set_opacity,
    window_move_by,
)
from .decoding import EmptyArguments
from .registries import ServiceRegistry

if TYPE_CHECKING:
    from .dispatcher import Dispatcher
    from .window_manager import WindowManager


def register_window_actions(dispatcher: "Dispatcher", windows: "WindowManager") -> None:
    """Register the window actions profiles send, routed to the window manager."""

    def show(arguments: WindowArguments) -> MessageResult:
        windows.show(arguments.window_id)
        return []

    def hide(arguments: WindowArguments) -> MessageResult:
        windows.hide(arguments.window_id)
        return []

    def close(arguments: WindowArguments) -> MessageResult:
        windows.close(arguments.window_id)
        return []

    def set_opacity(arguments: WindowOpacityArguments) -> MessageResult:
        windows.set_opacity(arguments.window_id, arguments.opacity)
        return []

    def block_input(arguments: WindowBlockInputArguments) -> MessageResult:
        windows.block_input(arguments.window_id, arguments.allowed_node_ids)
        return []

    def unblock_input(arguments: WindowArguments) -> MessageResult:
        windows.unblock_input(arguments.window_id)
        return []

    dispatcher.register_action(WINDOW_SHOW, decode_window, show)
    dispatcher.register_action(WINDOW_HIDE, decode_window, hide)
    dispatcher.register_action(WINDOW_CLOSE, decode_window, close)
    dispatcher.register_action(WINDOW_SET_OPACITY, decode_window_set_opacity, set_opacity)
    dispatcher.register_action(WINDOW_BLOCK_INPUT, decode_window_block_input, block_input)
    dispatcher.register_action(WINDOW_UNBLOCK_INPUT, decode_window, unblock_input)


def register_display_recovery(
    dispatcher: "Dispatcher",
    windows: "WindowManager",
    services: ServiceRegistry,
) -> None:
    """Recover windows and services after connected outputs change."""

    def recover(event: EmptyArguments) -> MessageResult:
        del event
        windows.refresh_screen_configuration()
        for service in services.services():
            refresh = getattr(service, "refresh_screen_configuration", None)
            if refresh is not None:
                refresh()
        return []

    dispatcher.add_event_handler(DISPLAY_CONFIGURATION_CHANGED, recover)


class PointerDragRouter:
    """Own one layer-shell title-bar drag and turn raw pointer motion into window moves."""

    def __init__(self, windows: "WindowManager", services: ServiceRegistry) -> None:
        self._windows = windows
        self._services = services
        self._window_id: str | None = None
        self._remainder = (0.0, 0.0)

    @property
    def window_id(self) -> str | None:
        """The window being dragged, if any."""

        return self._window_id

    def register(self, dispatcher: "Dispatcher") -> None:
        dispatcher.register_action(WINDOW_MOVE_BY, decode_window_move_by, self._move_by)
        dispatcher.add_event_handler(WINDOW_DRAG_STARTED, self._drag_started)
        dispatcher.add_event_handler(WINDOW_DRAG_ENDED, self._drag_ended)
        dispatcher.add_event_handler(POINTER_MOTION_OBSERVED, self._motion_observed)

    def _drag_started(self, event: WindowArguments) -> MessageResult:
        if self._window_id is not None:
            self._set_services_dragging(False)
        self._window_id = event.window_id
        self._remainder = (0.0, 0.0)
        self._set_services_dragging(True)
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
        return [window_move_by(window_id, dx, dy)]

    def _move_by(self, arguments: WindowMoveByArguments) -> MessageResult:
        """Move one managed window, then commit its surface in the same step."""

        window = self._windows.get(arguments.window_id)
        if window is None:
            return []
        try:
            self._windows.move_by(arguments.window_id, arguments.dx, arguments.dy)
            self._commit_surface(window)
        except Exception:
            if self._window_id == arguments.window_id:
                self._stop()
            raise
        return []

    def _stop(self) -> None:
        self._set_services_dragging(False)
        self._window_id = None
        self._remainder = (0.0, 0.0)

    def _set_services_dragging(self, enabled: bool) -> None:
        """Start or stop relative-pointer collection in interested services."""

        for service in self._services.services():
            toggle = getattr(service, "begin_drag" if enabled else "end_drag", None)
            if toggle is not None:
                toggle()

    def _commit_surface(self, window: QWidget) -> None:
        """Commit a moved layer-shell surface through interested services."""

        surface = int(window.winId())
        for service in self._services.services():
            commit_surface = getattr(service, "commit_surface", None)
            if commit_surface is not None:
                commit_surface(surface)
