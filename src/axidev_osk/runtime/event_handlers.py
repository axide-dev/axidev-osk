"""Default built-in action and event handler registration."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from PySide6.QtWidgets import QWidget

from ..messages import MessageResult
from .actions import (
    APP_QUIT,
    KEYBOARD_KEY_DOWN,
    KEYBOARD_KEY_UP,
    KEYBOARD_REGISTER_OUTPUT,
    PROMPT_RESOLVE,
    SECURE_INPUT_PANEL_PREPARE,
    SECURE_INPUT_PANEL_RELEASE,
    STATE_REPLACE,
    STATE_SET,
    WINDOW_CLOSE,
    WINDOW_HIDE,
    WINDOW_MOVE_BY,
    WINDOW_SET_DWELL_ENABLED,
    WINDOW_SHOW,
    WINDOW_TOGGLE_OPACITY,
    AppQuitArguments,
    KeyboardKeyArguments,
    KeyboardRegisterOutputArguments,
    NoArguments,
    PromptResolveArguments,
    StateReplaceArguments,
    StateSetArguments,
    WindowArguments,
    WindowMoveByArguments,
    WindowSetDwellEnabledArguments,
    WindowToggleOpacityArguments,
    decode_app_quit,
    decode_keyboard_key,
    decode_keyboard_register_output,
    decode_no_arguments,
    decode_prompt_resolve,
    decode_state_replace,
    decode_state_set,
    decode_window,
    decode_window_move_by,
    decode_window_set_dwell_enabled,
    decode_window_toggle_opacity,
    state_set,
    window_hide,
    window_move_by,
    window_show,
)
from .events import (
    DISPLAY_CONFIGURATION_CHANGED,
    HOT_CORNER_TRIGGERED,
    POINTER_MOTION_OBSERVED,
    WINDOW_CLOSE_REQUESTED,
    WINDOW_DRAG_ENDED,
    WINDOW_DRAG_STARTED,
    DisplayConfigurationChangedArguments,
    HotCornerTriggeredArguments,
    PointerMotionObservedArguments,
    WindowCloseRequestedArguments,
    WindowDragArguments,
    keyboard_output_registered,
    prompt_resolved,
    state_changed,
)
from .config_paths import window_source_path
from .source import source_state_namespace
from .registries import EventHandlerRegistry

if TYPE_CHECKING:
    from .window_manager import WindowManager


class _WindowVisibilityManager(Protocol):
    def is_visible(self, window_id: str) -> bool: ...
    def is_minimized(self, window_id: str) -> bool: ...
    def is_opacity_reduced(self, window_id: str) -> bool: ...


class _ApplicationEventRuntime(Protocol):
    def _handle_window_close_requested(
        self,
        event: WindowCloseRequestedArguments,
    ) -> MessageResult: ...

    def _handle_hot_corner_triggered(
        self,
        event: HotCornerTriggeredArguments,
    ) -> MessageResult: ...


class _SecureInputPanelRuntime(Protocol):
    def _prepare_secure_input_panel(self) -> MessageResult: ...

    def _release_secure_input_panel(self) -> MessageResult: ...


class _PointerDragRuntime(Protocol):
    _active_pointer_drag_window_id: str | None
    _pointer_drag_remainder: tuple[float, float]

    @property
    def _window_manager(self) -> "WindowManager": ...

    def _set_pointer_drag_active(self, enabled: bool) -> None: ...

    def _commit_window_surface(self, window: QWidget) -> None: ...


def register_context_action_handlers(registry: EventHandlerRegistry) -> None:
    """Register context-owned built-in actions."""

    registry.register_action_handler(
        KEYBOARD_REGISTER_OUTPUT,
        decode_keyboard_register_output,
        lambda context: lambda arguments: _keyboard_register(context, arguments),
    )
    registry.register_action_handler(
        KEYBOARD_KEY_DOWN,
        decode_keyboard_key,
        lambda context: lambda arguments: _keyboard_down(context, arguments),
    )
    registry.register_action_handler(
        KEYBOARD_KEY_UP,
        decode_keyboard_key,
        lambda context: lambda arguments: _keyboard_up(context, arguments),
    )
    registry.register_action_handler(
        STATE_REPLACE,
        decode_state_replace,
        lambda context: lambda arguments: _state_replace(context, arguments),
    )
    registry.register_action_handler(
        STATE_SET,
        decode_state_set,
        lambda context: lambda arguments: _state_set(context, arguments),
    )
    registry.register_action_handler(
        PROMPT_RESOLVE,
        decode_prompt_resolve,
        lambda context: lambda arguments: _prompt_resolve(context, arguments),
    )


def register_event_handlers(registry: EventHandlerRegistry) -> None:
    """Register application-owned built-in actions and event handlers."""

    registry.register_action_handler(
        WINDOW_SHOW,
        decode_window,
        lambda runtime: lambda arguments: _window_show(runtime, arguments),
    )
    registry.register_action_handler(
        WINDOW_HIDE,
        decode_window,
        lambda runtime: lambda arguments: _window_hide(runtime, arguments),
    )
    registry.register_action_handler(
        WINDOW_CLOSE,
        decode_window,
        lambda runtime: lambda arguments: _window_close(runtime, arguments),
    )
    registry.register_action_handler(
        WINDOW_TOGGLE_OPACITY,
        decode_window_toggle_opacity,
        lambda runtime: lambda arguments: _window_toggle_opacity(runtime, arguments),
    )
    registry.register_action_handler(
        WINDOW_MOVE_BY,
        decode_window_move_by,
        _window_move_by_handler,
    )
    registry.register_action_handler(
        WINDOW_SET_DWELL_ENABLED,
        decode_window_set_dwell_enabled,
        lambda runtime: lambda arguments: route_window_set_dwell_enabled(arguments, runtime),
    )
    registry.register_action_handler(
        SECURE_INPUT_PANEL_PREPARE,
        decode_no_arguments,
        _secure_input_panel_prepare_handler,
    )
    registry.register_action_handler(
        SECURE_INPUT_PANEL_RELEASE,
        decode_no_arguments,
        _secure_input_panel_release_handler,
    )
    registry.register_action_handler(
        APP_QUIT,
        decode_app_quit,
        lambda runtime: lambda arguments: _app_quit(runtime, arguments),
    )
    registry.register_event_handler(
        WINDOW_CLOSE_REQUESTED,
        _window_close_requested_handler,
    )
    registry.register_event_handler(
        HOT_CORNER_TRIGGERED,
        _hot_corner_triggered_handler,
    )
    registry.register_event_handler(
        DISPLAY_CONFIGURATION_CHANGED,
        _display_configuration_changed_handler,
    )
    registry.register_event_handler(
        WINDOW_DRAG_STARTED,
        _window_drag_started_handler,
    )
    registry.register_event_handler(
        WINDOW_DRAG_ENDED,
        _window_drag_ended_handler,
    )
    registry.register_event_handler(
        POINTER_MOTION_OBSERVED,
        _pointer_motion_observed_handler,
    )


def route_hot_corner_triggered(
    event: HotCornerTriggeredArguments,
    runtime: object,
) -> MessageResult:
    """Map a hot-corner event to ordered window visibility actions."""

    config = runtime._config  # type: ignore[attr-defined]  # noqa: SLF001
    window_manager: _WindowVisibilityManager = runtime._window_manager  # type: ignore[attr-defined]  # noqa: SLF001
    actions: MessageResult = []
    for window_id in config.hot_corner.bindings.get(event.corner, []):
        if window_manager.is_minimized(window_id):
            actions.append(window_show(window_id))
        elif window_manager.is_opacity_reduced(window_id):
            actions.append(window_show(window_id))
        elif window_manager.is_visible(window_id):
            actions.append(window_hide(window_id))
        else:
            actions.append(window_show(window_id))
    return actions


def route_display_configuration_changed(
    event: DisplayConfigurationChangedArguments,
    runtime: object,
) -> MessageResult:
    """Recover windows and services after connected outputs change."""

    del event
    runtime._window_manager.refresh_screen_configuration()  # type: ignore[attr-defined]  # noqa: SLF001
    for service in runtime._services.services():  # type: ignore[attr-defined]  # noqa: SLF001
        refresh = getattr(service, "refresh_screen_configuration", None)
        if refresh is not None:
            refresh()
    return []


def route_window_set_dwell_enabled(
    arguments: WindowSetDwellEnabledArguments,
    runtime: object,
) -> MessageResult:
    """Apply one window's dwell state and keep it in the central store."""

    runtime._window_manager.set_dwell_enabled(arguments.window_id, arguments.enabled)  # type: ignore[attr-defined]  # noqa: SLF001
    window_path = window_source_path(runtime._config, arguments.window_id)  # type: ignore[attr-defined]  # noqa: SLF001
    return [state_set(source_state_namespace(window_path), "dwell_enabled", arguments.enabled)]


def route_window_drag_started(event: WindowDragArguments, runtime: _PointerDragRuntime) -> MessageResult:
    """Start routing raw pointer motion to one dragged layer-shell window."""

    if runtime._active_pointer_drag_window_id is not None:  # noqa: SLF001
        runtime._set_pointer_drag_active(False)  # noqa: SLF001
    runtime._active_pointer_drag_window_id = event.window_id  # noqa: SLF001
    runtime._pointer_drag_remainder = (0.0, 0.0)  # noqa: SLF001
    runtime._set_pointer_drag_active(True)  # noqa: SLF001
    return []


def route_window_drag_ended(event: WindowDragArguments, runtime: _PointerDragRuntime) -> MessageResult:
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


def _window_close_requested_handler(
    runtime: _ApplicationEventRuntime,
) -> Callable[[WindowCloseRequestedArguments], MessageResult]:
    return runtime._handle_window_close_requested


def _hot_corner_triggered_handler(
    runtime: _ApplicationEventRuntime,
) -> Callable[[HotCornerTriggeredArguments], MessageResult]:
    return runtime._handle_hot_corner_triggered


def _keyboard_register(context: object, arguments: KeyboardRegisterOutputArguments) -> MessageResult:
    output_key, state_tags = context.keyboard.register_output(  # type: ignore[attr-defined]
        arguments.source,
        arguments.output,
    )
    return [keyboard_output_registered(arguments.source, output_key, state_tags)]


def _keyboard_down(context: object, arguments: KeyboardKeyArguments) -> MessageResult:
    context.keyboard.key_down(arguments.source, arguments.active_state_tags)  # type: ignore[attr-defined]
    return []


def _keyboard_up(context: object, arguments: KeyboardKeyArguments) -> MessageResult:
    context.keyboard.key_up(arguments.source)  # type: ignore[attr-defined]
    return []


def _state_replace(context: object, arguments: StateReplaceArguments) -> MessageResult:
    context.state.set(  # type: ignore[attr-defined]
        source_state_namespace(arguments.source),
        "snapshot",
        arguments.state,
    )
    return [state_changed(arguments.source, arguments.state)]


def _state_set(context: object, arguments: StateSetArguments) -> MessageResult:
    context.state.set(arguments.namespace, arguments.key, arguments.value)  # type: ignore[attr-defined]
    return []


def _prompt_resolve(context: object, arguments: PromptResolveArguments) -> MessageResult:
    del context
    return [prompt_resolved(arguments.prompt_id, arguments.result)]


def _window_show(runtime: object, arguments: WindowArguments) -> MessageResult:
    runtime._window_manager.show(arguments.window_id)  # type: ignore[attr-defined]  # noqa: SLF001
    return []


def _window_hide(runtime: object, arguments: WindowArguments) -> MessageResult:
    runtime._window_manager.hide(arguments.window_id)  # type: ignore[attr-defined]  # noqa: SLF001
    return []


def _window_close(runtime: object, arguments: WindowArguments) -> MessageResult:
    runtime._window_manager.close(arguments.window_id)  # type: ignore[attr-defined]  # noqa: SLF001
    return []


def _window_toggle_opacity(runtime: object, arguments: WindowToggleOpacityArguments) -> MessageResult:
    runtime._window_manager.toggle_opacity(  # type: ignore[attr-defined]  # noqa: SLF001
        arguments.window_id,
        component_id=arguments.component_id,
        opacity=arguments.opacity,
    )
    return []


def _secure_input_panel_prepare_handler(
    runtime: _SecureInputPanelRuntime,
) -> Callable[[NoArguments], MessageResult]:
    return lambda arguments: runtime._prepare_secure_input_panel()  # noqa: SLF001


def _secure_input_panel_release_handler(
    runtime: _SecureInputPanelRuntime,
) -> Callable[[NoArguments], MessageResult]:
    return lambda arguments: runtime._release_secure_input_panel()  # noqa: SLF001


def _window_move_by_handler(
    runtime: _PointerDragRuntime,
) -> Callable[[WindowMoveByArguments], MessageResult]:
    return lambda arguments: route_window_move_by(arguments, runtime)


def _display_configuration_changed_handler(
    runtime: object,
) -> Callable[[DisplayConfigurationChangedArguments], MessageResult]:
    return lambda event: route_display_configuration_changed(event, runtime)


def _window_drag_started_handler(
    runtime: _PointerDragRuntime,
) -> Callable[[WindowDragArguments], MessageResult]:
    return lambda event: route_window_drag_started(event, runtime)


def _window_drag_ended_handler(
    runtime: _PointerDragRuntime,
) -> Callable[[WindowDragArguments], MessageResult]:
    return lambda event: route_window_drag_ended(event, runtime)


def _pointer_motion_observed_handler(
    runtime: _PointerDragRuntime,
) -> Callable[[PointerMotionObservedArguments], MessageResult]:
    return lambda event: route_pointer_motion_observed(event, runtime)


def _app_quit(runtime: object, arguments: AppQuitArguments) -> MessageResult:
    runtime._app.exit(arguments.exit_code)  # type: ignore[attr-defined]  # noqa: SLF001
    return []
