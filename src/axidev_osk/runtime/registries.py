"""Runtime registries for components, surfaces, services, and handlers.

``EventHandlerRegistry`` follows the same self-registration pattern as the
component and surface registries instead of extending ``Dispatcher`` directly.
Application/window orchestration handlers need runtime-owned collaborators such
as ``WindowManager`` and ``QApplication``; keeping those factories in a registry
preserves ``Dispatcher`` as a generic command/event router rather than making it
aware of application policy.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Protocol, TypeVar, cast

from PySide6.QtWidgets import QWidget

from ..config.models import ComponentConfig, SurfaceConfig
from .commands import RuntimeCommand
from .events import RuntimeEvent

if TYPE_CHECKING:
    from .context import Context
    from .dispatcher import Dispatcher


ComponentBuilder = Callable[..., QWidget]
SurfaceBuilder = Callable[[SurfaceConfig, "Context"], QWidget]
RuntimeT = TypeVar("RuntimeT")


class RuntimeService(Protocol):
    """Runtime-managed service lifecycle contract."""

    def start(self, context: "Context") -> None:
        """Start the service using the bound runtime context."""

    def stop(self) -> None:
        """Stop the service and release owned resources."""


CommandHandlerFactory = Callable[[RuntimeT], Callable[[RuntimeCommand], object | None]]
EventHandlerFactory = Callable[[RuntimeT], Callable[[RuntimeEvent], object | None]]


class ComponentRegistry:
    """Maps component kinds to builders.

    Components self-register during runtime startup. Missing builders fail with a
    clear error so deleting a component directory exposes stale config references.

    Builders accept an optional ``host`` keyword that lets parent components pass
    explicit construction context (for example, a containing grid) without using
    module-level globals or class-level mutable state.
    """

    def __init__(self) -> None:
        """Create an empty component registry.

        Args:
            None.

        Returns:
            None.

        Side effects:
            None.
        """

        self._builders: dict[str, ComponentBuilder] = {}

    def register(self, kind: str, builder: ComponentBuilder) -> None:
        """Register a component builder.

        Args:
            kind: Component kind string from config.
            builder: Callable that creates a widget for the component. The
                callable receives ``(config, context)`` positional arguments and
                may opt into an additional ``host`` keyword argument naming the
                immediate parent component.

        Returns:
            None.

        Side effects:
            Mutates registry contents.
        """

        self._builders[kind] = builder

    def build(
        self,
        config: ComponentConfig,
        context: "Context",
        *,
        host: QWidget | None = None,
    ) -> QWidget:
        """Build a component widget from config.

        Args:
            config: Component DTO.
            context: Runtime context.
            host: Optional immediate parent component, forwarded to builders
                that opt in via a ``host`` keyword. Builders that do not accept
                ``host`` simply ignore it.

        Returns:
            Constructed widget.

        Side effects:
            Depends on the registered builder.
        """

        builder = self._builders.get(config.kind)
        if builder is None:
            raise ValueError(f"No component registered for kind {config.kind!r}")
        return builder(config, context, host=host)


class SurfaceRegistry:
    """Maps surface kinds to root content builders."""

    def __init__(self) -> None:
        """Create an empty surface registry.

        Args:
            None.

        Returns:
            None.

        Side effects:
            None.
        """

        self._builders: dict[str, SurfaceBuilder] = {}

    def register(self, kind: str, builder: SurfaceBuilder) -> None:
        """Register a surface builder.

        Args:
            kind: Surface kind string from config.
            builder: Callable that creates root window content.

        Returns:
            None.

        Side effects:
            Mutates registry contents.
        """

        self._builders[kind] = builder

    def build(self, config: SurfaceConfig, context: "Context") -> QWidget:
        """Build root window content from config.

        Args:
            config: Surface DTO.
            context: Runtime context.

        Returns:
            Constructed root widget.

        Side effects:
            Depends on the registered builder.
        """

        builder = self._builders.get(config.kind)
        if builder is None:
            raise ValueError(f"No surface registered for kind {config.kind!r}")
        return builder(config, context)


class ServiceRegistry:
    """Maintains named runtime services in deterministic startup order."""

    def __init__(self) -> None:
        """Create an empty service registry."""

        self._services: dict[str, RuntimeService] = {}

    def register(self, name: str, service: RuntimeService) -> None:
        """Register a runtime service under a stable name."""

        self._services[name] = service

    def get(self, name: str, service_type: type[RuntimeT]) -> RuntimeT:
        """Return a named service, validating its concrete type."""

        service = self._services.get(name)
        if service is None:
            raise ValueError(f"No service registered for name {name!r}")
        if not isinstance(service, service_type):
            raise TypeError(f"Service {name!r} is not a {service_type.__name__}")
        return cast(RuntimeT, service)

    def services(self) -> Iterable[RuntimeService]:
        """Yield services in registration order."""

        return tuple(self._services.values())


class EventHandlerRegistry:
    """Stores default command and event handler factories for installation."""

    def __init__(self) -> None:
        """Create an empty handler registry."""

        self._command_handlers: list[tuple[type[object], CommandHandlerFactory[object]]] = []
        self._event_handlers: list[EventHandlerFactory[object]] = []

    def register_command_handler(
        self,
        command_type: type[object],
        factory: CommandHandlerFactory[RuntimeT],
    ) -> None:
        """Register a command handler factory."""

        self._command_handlers.append((command_type, cast(CommandHandlerFactory[object], factory)))

    def register_event_handler(self, factory: EventHandlerFactory[RuntimeT]) -> None:
        """Register an event handler factory."""

        self._event_handlers.append(cast(EventHandlerFactory[object], factory))

    def install(self, dispatcher: "Dispatcher", runtime: object) -> None:
        """Install all registered handlers onto a dispatcher."""

        for command_type, factory in self._command_handlers:
            dispatcher.add_command_handler(command_type, factory(runtime))
        for factory in self._event_handlers:
            dispatcher.add_event_handler(factory(runtime))
