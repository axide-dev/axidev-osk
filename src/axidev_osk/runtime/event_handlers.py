"""Runtime-owned action and event handlers.

These adapt queue messages into calls on objects the main runtime owns: the
window manager, services, and process lifecycle. They contain no profile
policy; profiles decide when to send these actions.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from PySide6.QtWidgets import QWidget

from ..messages import MessageResult
from .actions import (
    APP_QUIT,
    LINUX_OPEN_PERMISSION_SETUP,
    SECURE_INPUT_PANEL_PREPARE,
    SECURE_INPUT_PANEL_RELEASE,
    WINDOW_BLOCK_INPUT,
    WINDOW_CLOSE,
    WINDOW_HIDE,
    WINDOW_MOVE_BY,
    WINDOW_SET_OPACITY,
    WINDOW_SHOW,
    WINDOW_UNBLOCK_INPUT,
    AppQuitArguments,
    NoArguments,
    WindowArguments,
    WindowBlockInputArguments,
    WindowMoveByArguments,
    WindowOpacityArguments,
    decode_app_quit,
    decode_no_arguments,
    decode_window,
    decode_window_block_input,
    decode_window_move_by,
    decode_window_set_opacity,
    window_move_by,
)
from .events import (
    DISPLAY_CONFIGURATION_CHANGED,
    POINTER_MOTION_OBSERVED,
    WINDOW_DRAG_ENDED,
    WINDOW_DRAG_STARTED,
    NoEventArguments,
    PointerMotionObservedArguments,
    WindowEventArguments,
)
from .registries import EventHandlerRegistry, ServiceRegistry

if TYPE_CHECKING:
    from .window_manager import WindowManager


class _WindowRuntime(Protocol):
    @property
    def _window_manager(self) -> "WindowManager": ...


class _DisplayRuntime(Protocol):
    @property
    def _window_manager(self) -> "WindowManager": ...

    @property
    def _services(self) -> ServiceRegistry: ...


class _LifecycleRuntime(Protocol):
    def _quit(self, exit_code: int) -> MessageResult: ...

    def _prepare_secure_input_panel(self) -> MessageResult: ...

    def _release_secure_input_panel(self) -> MessageResult: ...

    def _open_permission_setup(self) -> MessageResult: ...


class _PointerDragRuntime(Protocol):
    _active_pointer_drag_window_id: str | None
    _pointer_drag_remainder: tuple[float, float]

    @property
    def _window_manager(self) -> "WindowManager": ...

    def _set_pointer_drag_active(self, enabled: bool) -> None: ...

    def _commit_window_surface(self, window: QWidget) -> None: ...


def register_event_handlers(registry: EventHandlerRegistry) -> None:
    """Register runtime-owned actions and event handlers."""

    registry.register_action_handler(WINDOW_SHOW, decode_window, _window_show)
    registry.register_action_handler(WINDOW_HIDE, decode_window, _window_hide)
    registry.register_action_handler(WINDOW_CLOSE, decode_window, _window_close)
    registry.register_action_handler(WINDOW_SET_OPACITY, decode_window_set_opacity, _window_set_opacity)
    registry.register_action_handler(WINDOW_BLOCK_INPUT, decode_window_block_input, _window_block_input)
    registry.register_action_handler(WINDOW_UNBLOCK_INPUT, decode_window, _window_unblock_input)
    registry.register_action_handler(WINDOW_MOVE_BY, decode_window_move_by, _window_move_by)
    registry.register_action_handler(APP_QUIT, decode_app_quit, _app_quit)
    registry.register_action_handler(SECURE_INPUT_PANEL_PREPARE, decode_no_arguments, _secure_input_panel_prepare)
    registry.register_action_handler(SECURE_INPUT_PANEL_RELEASE, decode_no_arguments, _secure_input_panel_release)
    registry.register_action_handler(LINUX_OPEN_PERMISSION_SETUP, decode_no_arguments, _open_permission_setup)
    registry.register_event_handler(DISPLAY_CONFIGURATION_CHANGED, _display_configuration_changed)
    registry.register_event_handler(WINDOW_DRAG_STARTED, _window_drag_started)
    registry.register_event_handler(WINDOW_DRAG_ENDED, _window_drag_ended)
    registry.register_event_handler(POINTER_MOTION_OBSERVED, _pointer_motion_observed)


def _window_show(runtime: _WindowRuntime) -> Callable[[WindowArguments], MessageResult]:
    def show(arguments: WindowArguments) -> MessageResult:
        runtime._window_manager.show(arguments.window_id)  # noqa: SLF001
        return []

    return show


def _window_hide(runtime: _WindowRuntime) -> Callable[[WindowArguments], MessageResult]:
    def hide(arguments: WindowArguments) -> MessageResult:
        runtime._window_manager.hide(arguments.window_id)  # noqa: SLF001
        return []

    return hide


def _window_close(runtime: _WindowRuntime) -> Callable[[WindowArguments], MessageResult]:
    def close(arguments: WindowArguments) -> MessageResult:
        runtime._window_manager.close(arguments.window_id)  # noqa: SLF001
        return []

    return close


def _window_set_opacity(runtime: _WindowRuntime) -> Callable[[WindowOpacityArguments], MessageResult]:
    def set_opacity(arguments: WindowOpacityArguments) -> MessageResult:
        runtime._window_manager.set_opacity(arguments.window_id, arguments.opacity)  # noqa: SLF001
        return []

    return set_opacity


def _window_block_input(runtime: _WindowRuntime) -> Callable[[WindowBlockInputArguments], MessageResult]:
    def block_input(arguments: WindowBlockInputArguments) -> MessageResult:
        runtime._window_manager.block_input(arguments.window_id, arguments.allowed_node_ids)  # noqa: SLF001
        return []

    return block_input


def _window_unblock_input(runtime: _WindowRuntime) -> Callable[[WindowArguments], MessageResult]:
    def unblock_input(arguments: WindowArguments) -> MessageResult:
        runtime._window_manager.unblock_input(arguments.window_id)  # noqa: SLF001
        return []

    return unblock_input


def _window_move_by(runtime: _PointerDragRuntime) -> Callable[[WindowMoveByArguments], MessageResult]:
    return lambda arguments: route_window_move_by(arguments, runtime)


def _app_quit(runtime: _LifecycleRuntime) -> Callable[[AppQuitArguments], MessageResult]:
    return lambda arguments: runtime._quit(arguments.exit_code)  # noqa: SLF001


def _secure_input_panel_prepare(runtime: _LifecycleRuntime) -> Callable[[NoArguments], MessageResult]:
    return lambda arguments: runtime._prepare_secure_input_panel()  # noqa: SLF001


def _secure_input_panel_release(runtime: _LifecycleRuntime) -> Callable[[NoArguments], MessageResult]:
    return lambda arguments: runtime._release_secure_input_panel()  # noqa: SLF001


def _open_permission_setup(runtime: _LifecycleRuntime) -> Callable[[NoArguments], MessageResult]:
    return lambda arguments: runtime._open_permission_setup()  # noqa: SLF001


def _display_configuration_changed(runtime: _DisplayRuntime) -> Callable[[NoEventArguments], MessageResult]:
    return lambda event: route_display_configuration_changed(event, runtime)


def _window_drag_started(runtime: _PointerDragRuntime) -> Callable[[WindowEventArguments], MessageResult]:
    return lambda event: route_window_drag_started(event, runtime)


def _window_drag_ended(runtime: _PointerDragRuntime) -> Callable[[WindowEventArguments], MessageResult]:
    return lambda event: route_window_drag_ended(event, runtime)


def _pointer_motion_observed(runtime: _PointerDragRuntime) -> Callable[[PointerMotionObservedArguments], MessageResult]:
    return lambda event: route_pointer_motion_observed(event, runtime)


def route_display_configuration_changed(event: NoEventArguments, runtime: _DisplayRuntime) -> MessageResult:
    """Recover windows and services after connected outputs change."""

    del event
    runtime._window_manager.refresh_screen_configuration()  # noqa: SLF001
    for service in runtime._services.services():  # noqa: SLF001
        refresh = getattr(service, "refresh_screen_configuration", None)
        if refresh is not None:
            refresh()
    return []


def route_window_drag_started(event: WindowEventArguments, runtime: _PointerDragRuntime) -> MessageResult:
    """Start routing raw pointer motion to one dragged layer-shell window."""

    if runtime._active_pointer_drag_window_id is not None:  # noqa: SLF001
        runtime._set_pointer_drag_active(False)  # noqa: SLF001
    runtime._active_pointer_drag_window_id = event.window_id  # noqa: SLF001
    runtime._pointer_drag_remainder = (0.0, 0.0)  # noqa: SLF001
    runtime._set_pointer_drag_active(True)  # noqa: SLF001
    return []


def route_window_drag_ended(event: WindowEventArguments, runtime: _PointerDragRuntime) -> MessageResult:
    """Stop routing raw pointer motion when the dragged window releases."""

    if runtime._active_pointer_drag_window_id == event.window_id:  # noqa: SLF001
        _stop_pointer_drag(runtime)
    return []


def route_pointer_motion_observed(
    event: PointerMotionObservedArguments,
    runtime: _PointerDragRuntime,
) -> MessageResult:
    """Turn accumulated raw pointer motion into whole-pixel window moves."""

    window_id = runtime._active_pointer_drag_window_id  # noqa: SLF001
    if window_id is None:
        return []
    window = runtime._window_manager.get(window_id)  # noqa: SLF001
    if window is None or not window.isVisible():
        _stop_pointer_drag(runtime)
        return []
    remainder_x, remainder_y = runtime._pointer_drag_remainder  # noqa: SLF001
    total_x = remainder_x + event.dx
    total_y = remainder_y + event.dy
    dx = int(total_x)
    dy = int(total_y)
    runtime._pointer_drag_remainder = (total_x - dx, total_y - dy)  # noqa: SLF001
    if not dx and not dy:
        return []
    return [window_move_by(window_id, dx, dy)]


def route_window_move_by(arguments: WindowMoveByArguments, runtime: _PointerDragRuntime) -> MessageResult:
    """Move one managed window, then commit its surface in the same step."""

    window = runtime._window_manager.get(arguments.window_id)  # noqa: SLF001
    if window is None:
        return []
    try:
        runtime._window_manager.move_by(arguments.window_id, arguments.dx, arguments.dy)  # noqa: SLF001
        runtime._commit_window_surface(window)  # noqa: SLF001
    except Exception:
        if runtime._active_pointer_drag_window_id == arguments.window_id:  # noqa: SLF001
            _stop_pointer_drag(runtime)
        raise
    return []


def _stop_pointer_drag(runtime: _PointerDragRuntime) -> None:
    runtime._set_pointer_drag_active(False)  # noqa: SLF001
    runtime._active_pointer_drag_window_id = None  # noqa: SLF001
    runtime._pointer_drag_remainder = (0.0, 0.0)  # noqa: SLF001
