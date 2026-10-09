"""Test helpers for building a real runtime context around a fake keyboard backend.

Tests get the production dispatcher, engine, node kinds, and attachment kinds,
so they exercise the same queue and state paths the app uses. Only the
keyboard backend and spawned processes are replaced.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from ..config.profile import ProfileConfig
from ..services import register_services
from ..services.keyboard import KeyboardService
from .context import Context
from .dispatcher import Dispatcher
from .engine import build_engine
from .events import register_builtin_events
from .registries import ServiceRegistry


class RecordingProcesses:
    """Process effects that record spawn requests instead of starting programs."""

    def __init__(self) -> None:
        self.spawned: list[tuple[tuple[str, ...], str, bool]] = []

    def spawn(self, argv: tuple[str, ...], tag: str, detached: bool) -> None:
        self.spawned.append((argv, tag, detached))


def make_test_context(
    keyboard_backend: Any,
    *,
    services: set[str] | None = None,
) -> Context:
    """Build a runtime ``Context`` wrapping a test keyboard backend.

    Args:
        keyboard_backend: Duck-typed backend with the ``AxidevIoKeyboardBackend``
            surface, wrapped in a real ``KeyboardService``.
        services: Optional service names to register and start. When omitted,
            only the keyboard service is bound to the context.

    Returns:
        A context whose dispatcher has every built-in engine event, action,
        node kind, and attachment kind registered.
    """

    dispatcher = Dispatcher()
    register_builtin_events(dispatcher)
    keyboard = KeyboardService(cast(Any, keyboard_backend))
    engine = build_engine(dispatcher, keyboard=keyboard, processes=RecordingProcesses())
    context = Context(dispatcher=dispatcher, keyboard=keyboard, engine=engine)
    if services is None:
        keyboard.bind_context(context)
    else:
        registry = ServiceRegistry()
        register_services(registry, include=services, keyboard=keyboard)
        for service in registry.services():
            service.start(context)
    return context


def start_test_profile(context: Context, root_config: Mapping[str, Any]) -> ProfileConfig:
    """Decode ``root_config`` with the context's engine and start its active profile."""

    profile = context.engine.decoder().decode_root(root_config).profile
    context.engine.profile.start(profile)
    return profile
