"""Registry of runtime services in deterministic startup order."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol, TypeVar, cast

if TYPE_CHECKING:
    from .context import Context


RuntimeT = TypeVar("RuntimeT")


class RuntimeService(Protocol):
    """Runtime-managed service lifecycle contract."""

    def start(self, context: "Context") -> None:
        """Start the service using the bound runtime context."""

    def stop(self) -> None:
        """Stop the service and release owned resources."""


class ServiceRegistry:
    """Maintains named runtime services in deterministic startup order."""

    def __init__(self) -> None:
        """Create an empty service registry."""

        self._services: dict[str, RuntimeService] = {}
        self._deferred: set[str] = set()

    def register(self, name: str, service: RuntimeService, *, autostart: bool = True) -> None:
        """Register a runtime service under a stable name; a name can be registered once."""

        if name in self._services:
            raise ValueError(f"Service {name!r} is already registered")
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
