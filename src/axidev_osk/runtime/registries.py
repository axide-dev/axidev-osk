"""Runtime registries for services and runtime-owned handlers.

``EventHandlerRegistry`` collects handler factories instead of extending
``Dispatcher`` directly.
Application/window orchestration handlers need runtime-owned collaborators such
as ``WindowManager`` and ``QApplication``; keeping those factories in a registry
preserves ``Dispatcher`` as a generic action/event router rather than making it
aware of application policy.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Protocol, TypeVar, cast

from ..messages import DataMap, MessageResult

if TYPE_CHECKING:
    from .context import Context
    from .dispatcher import Dispatcher


RuntimeT = TypeVar("RuntimeT")


class RuntimeService(Protocol):
    """Runtime-managed service lifecycle contract."""

    def start(self, context: "Context") -> None:
        """Start the service using the bound runtime context."""

    def stop(self) -> None:
        """Stop the service and release owned resources."""


DecodedT = TypeVar("DecodedT")
Decoder = Callable[[DataMap], DecodedT]
MessageHandler = Callable[[DecodedT], MessageResult]
MessageHandlerFactory = Callable[[RuntimeT], MessageHandler[DecodedT]]


class ServiceRegistry:
    """Maintains named runtime services in deterministic startup order."""

    def __init__(self) -> None:
        """Create an empty service registry."""

        self._services: dict[str, RuntimeService] = {}
        self._deferred: set[str] = set()

    def register(self, name: str, service: RuntimeService, *, autostart: bool = True) -> None:
        """Register a runtime service under a stable name."""

        self._services[name] = service
        if autostart:
            self._deferred.discard(name)
        else:
            self._deferred.add(name)

    def get(self, name: str, service_type: type[RuntimeT]) -> RuntimeT:
        """Return a named service, validating its concrete type."""

        service = self._services.get(name)
        if service is None:
            raise ValueError(f"No service registered for name {name!r}")
        if not isinstance(service, service_type):
            raise TypeError(f"Service {name!r} is not a {service_type.__name__}")
        return cast(RuntimeT, service)

    def find(self, name: str) -> RuntimeService | None:
        """Return a named service, or ``None`` when it is not registered."""

        return self._services.get(name)

    def services(self) -> Iterable[RuntimeService]:
        """Yield services in registration order."""

        return tuple(self._services.values())

    def autostart_services(self) -> Iterable[RuntimeService]:
        """Yield services that should start with the application runtime."""

        return tuple(service for name, service in self._services.items() if name not in self._deferred)


class EventHandlerRegistry:
    """Stores default action and event handler factories for installation."""

    def __init__(self) -> None:
        """Create an empty handler registry."""

        self._action_handlers: list[
            tuple[str, Decoder[object], MessageHandlerFactory[object, object]]
        ] = []
        self._event_handlers: list[tuple[str, MessageHandlerFactory[object, object]]] = []

    def register_action_handler(
        self,
        name: str,
        decoder: Decoder[DecodedT],
        factory: MessageHandlerFactory[RuntimeT, DecodedT],
    ) -> None:
        """Register an action decoder and typed handler factory."""

        self._action_handlers.append(
            (
                name,
                cast(Decoder[object], decoder),
                cast(MessageHandlerFactory[object, object], factory),
            )
        )

    def register_event_handler(
        self,
        name: str,
        factory: MessageHandlerFactory[RuntimeT, DecodedT],
    ) -> None:
        """Register a typed event handler factory."""

        self._event_handlers.append(
            (name, cast(MessageHandlerFactory[object, object], factory))
        )

    def install(self, dispatcher: "Dispatcher", runtime: object) -> None:
        """Install all registered handlers onto a dispatcher."""

        for name, decoder, factory in self._action_handlers:
            dispatcher.register_action(name, decoder, factory(runtime))
        for name, factory in self._event_handlers:
            dispatcher.add_event_handler(name, factory(runtime))
