"""Test helpers for constructing minimal runtime contexts.

These helpers exist so unit tests can build a real ``Context`` with a
caller-supplied keyboard backend stub instead of constructing widgets
with ``context=None``. Keeping a single sanctioned construction path
means the production ``KeyboardWidget`` can require ``context`` and
never fall back to legacy behavior.

This module is intentionally lightweight and dependency-free beyond
the runtime package itself: tests should be able to import it without
pulling Qt or the full application stack.
"""

from __future__ import annotations

from typing import Any, cast

from ..config.defaults import build_default_app_config
from ..config.models import AppConfig
from ..services import register_services
from ..services.keyboard import KeyboardService
from ..messages import MessageResult
from .actions import app_quit
from .behaviors import BehaviorRegistry, register_builtin_behaviors
from .context import Context
from .dispatcher import Dispatcher
from .event_handlers import (
    register_context_action_handlers,
    register_event_handlers,
    route_hot_corner_triggered,
)
from .events import (
    HotCornerTriggeredArguments,
    WindowCloseRequestedArguments,
    register_builtin_events,
)
from .registries import ComponentRegistry, EventHandlerRegistry, ServiceRegistry, SurfaceRegistry
from .state_store import StateStore
from .window_manager import WindowManager


class _TestApplication:
    """Minimal QApplication-shaped adapter for default action handlers."""

    def __init__(self) -> None:
        """Create an adapter that records requested exit codes."""

        self.exit_code: int | None = None

    def exit(self, exit_code: int) -> None:
        """Record the requested application exit code."""

        self.exit_code = exit_code


class _TestRuntime:
    """Runtime-shaped adapter used to install default handlers in tests."""

    def __init__(self, context: Context) -> None:
        """Bind context, window manager, and app adapter for handlers."""

        self._config = context.config
        self._dispatcher = context.dispatcher
        self._window_manager = WindowManager(context)
        self._app = _TestApplication()

    def _handle_window_close_requested(self, event: WindowCloseRequestedArguments) -> MessageResult:
        """Map close requests to a direct test quit action."""

        del event
        return [app_quit()]

    def _handle_hot_corner_triggered(self, event: HotCornerTriggeredArguments) -> MessageResult:
        """Route hot-corner visibility actions through production helper."""

        return route_hot_corner_triggered(event, self)


def make_test_context(
    keyboard_backend: Any,
    *,
    config: AppConfig | None = None,
    components: ComponentRegistry | None = None,
    surfaces: SurfaceRegistry | None = None,
    behavior_registry: BehaviorRegistry | None = None,
    services: set[str] | None = None,
    event_handlers: bool = False,
    activate_behaviors: bool = True,
) -> Context:
    """Build a runtime ``Context`` wrapping a test keyboard backend.

    The returned context is fully functional: it owns its own
    ``Dispatcher`` (with default action handlers bound), ``StateStore``,
    and registries. Tests can therefore exercise the same dispatch and
    state paths the production runtime uses.

    Args:
        keyboard_backend: Duck-typed keyboard backend exposing the same
            surface as ``AxidevIoKeyboardBackend``. Wrapped in a
            ``KeyboardService`` so components see the production
            service boundary.
        config: Optional declarative app config. Defaults to the bundled
            default config so dependent code (window IDs, layout names)
            sees realistic values.
        components: Optional pre-populated component registry. When
            omitted, a fresh registry is created and the bundled
            component builders are registered into it.
        surfaces: Optional pre-populated surface registry. Defaults to
            an empty registry.
        behavior_registry: Optional pre-populated behavior registry. Defaults
            to a fresh registry containing the built-in behavior kinds.
        services: Optional explicit service names to register and start.
            When omitted, only the supplied keyboard backend is bound.
        event_handlers: Whether to install bundled application-level event
            handler factories against a lightweight runtime adapter.
        activate_behaviors: Whether to register configured outputs and publish
            initial state snapshots. Focused service tests can disable this.

    Returns:
        A bound ``Context`` ready to pass into widgets and builders.

    Side effects:
        Constructs and binds a fresh ``Dispatcher``.
    """

    dispatcher = Dispatcher()
    register_builtin_events(dispatcher)
    keyboard = KeyboardService(cast(Any, keyboard_backend))
    resolved_config = config or build_default_app_config()
    behaviors = behavior_registry or BehaviorRegistry()
    if behavior_registry is None:
        register_builtin_behaviors(behaviors)
    behaviors.load(resolved_config)
    if components is None:
        # Lazy import: avoids pulling Qt-bound builders into modules
        # that import this helper purely for the Context type.
        from ..components import register_components

        components = ComponentRegistry()
        register_components(components)
    context = Context(
        config=resolved_config,
        dispatcher=dispatcher,
        keyboard=keyboard,
        state=StateStore(),
        components=components,
        surfaces=surfaces or SurfaceRegistry(),
        behaviors=behaviors,
    )
    context_handlers = EventHandlerRegistry()
    register_context_action_handlers(context_handlers)
    context_handlers.install(dispatcher, context)
    behaviors.bind_context(context)
    if services is None:
        keyboard.bind_context(context)
    else:
        service_registry = ServiceRegistry()
        register_services(service_registry, include=services, keyboard=keyboard)
        for service in service_registry.services():
            service.start(context)
    if activate_behaviors:
        behaviors.activate()
    if event_handlers:
        handler_registry = EventHandlerRegistry()
        register_event_handlers(handler_registry)
        handler_registry.install(dispatcher, _TestRuntime(context))
    return context
