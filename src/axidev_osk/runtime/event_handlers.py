"""Default built-in action and event handler registration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ..messages import MessageResult
from .actions import (
    APP_QUIT,
    KEYBOARD_KEY_DOWN,
    KEYBOARD_KEY_UP,
    KEYBOARD_REGISTER_KEY_SPEC,
    KEYBOARD_SYNC_LATCHED_KEY,
    STATE_SET,
    WINDOW_CLOSE,
    WINDOW_HIDE,
    WINDOW_SHOW,
    WINDOW_TOGGLE_OPACITY,
    AppQuitArguments,
    KeyboardKeyArguments,
    KeyboardRegisterKeySpecArguments,
    KeyboardSyncLatchedKeyArguments,
    StateSetArguments,
    WindowArguments,
    WindowToggleOpacityArguments,
    decode_app_quit,
    decode_keyboard_key,
    decode_keyboard_register_key_spec,
    decode_keyboard_sync_latched_key,
    decode_state_set,
    decode_window,
    decode_window_toggle_opacity,
    window_hide,
    window_show,
)
from .events import (
    COMPONENT_PRESSED,
    HOT_CORNER_TRIGGERED,
    WINDOW_CLOSE_REQUESTED,
    ComponentPressedArguments,
    HotCornerTriggeredArguments,
    WindowCloseRequestedArguments,
)
from .registries import EventHandlerRegistry


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

    def _handle_component_pressed(
        self,
        event: ComponentPressedArguments,
    ) -> MessageResult: ...


def register_context_action_handlers(registry: EventHandlerRegistry) -> None:
    """Register context-owned built-in actions."""

    registry.register_action_handler(
        KEYBOARD_REGISTER_KEY_SPEC,
        decode_keyboard_register_key_spec,
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
        KEYBOARD_SYNC_LATCHED_KEY,
        decode_keyboard_sync_latched_key,
        lambda context: lambda arguments: _keyboard_sync_latch(context, arguments),
    )
    registry.register_action_handler(
        STATE_SET,
        decode_state_set,
        lambda context: lambda arguments: _state_set(context, arguments),
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
        COMPONENT_PRESSED,
        _component_pressed_handler,
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


def route_component_pressed(
    event: ComponentPressedArguments,
    runtime: object,
) -> MessageResult:
    """Return the configured action attached to a pressed key."""

    del runtime
    if event.action is None:
        return []
    return [event.action]


def _window_close_requested_handler(
    runtime: _ApplicationEventRuntime,
) -> Callable[[WindowCloseRequestedArguments], MessageResult]:
    return runtime._handle_window_close_requested


def _hot_corner_triggered_handler(
    runtime: _ApplicationEventRuntime,
) -> Callable[[HotCornerTriggeredArguments], MessageResult]:
    return runtime._handle_hot_corner_triggered


def _component_pressed_handler(
    runtime: _ApplicationEventRuntime,
) -> Callable[[ComponentPressedArguments], MessageResult]:
    return runtime._handle_component_pressed


def _keyboard_register(context: object, arguments: KeyboardRegisterKeySpecArguments) -> MessageResult:
    context.keyboard.register_key_spec(  # type: ignore[attr-defined]
        arguments.layout_id,
        arguments.key_spec,
        component_id=arguments.component_id,
    )
    return []


def _keyboard_down(context: object, arguments: KeyboardKeyArguments) -> MessageResult:
    context.keyboard.key_down(arguments.layout_id, arguments.component_id)  # type: ignore[attr-defined]
    return []


def _keyboard_up(context: object, arguments: KeyboardKeyArguments) -> MessageResult:
    context.keyboard.key_up(arguments.layout_id, arguments.component_id)  # type: ignore[attr-defined]
    return []


def _keyboard_sync_latch(context: object, arguments: KeyboardSyncLatchedKeyArguments) -> MessageResult:
    context.keyboard.sync_latched_key(  # type: ignore[attr-defined]
        arguments.layout_id,
        arguments.component_id,
        arguments.latched,
    )
    return []


def _state_set(context: object, arguments: StateSetArguments) -> MessageResult:
    context.state.set(arguments.namespace, arguments.key, arguments.value)  # type: ignore[attr-defined]
    return []


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


def _app_quit(runtime: object, arguments: AppQuitArguments) -> MessageResult:
    runtime._app.exit(arguments.exit_code)  # type: ignore[attr-defined]  # noqa: SLF001
    return []
