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
from ..services.keyboard import KeyboardService
from .context import Context
from .dispatcher import Dispatcher
from .registries import ComponentRegistry, SurfaceRegistry
from .state_store import StateStore


def make_test_context(
    keyboard_backend: Any,
    *,
    config: AppConfig | None = None,
    components: ComponentRegistry | None = None,
    surfaces: SurfaceRegistry | None = None,
) -> Context:
    """Build a runtime ``Context`` wrapping a test keyboard backend.

    The returned context is fully functional: it owns its own
    ``Dispatcher`` (with default command handlers bound), ``StateStore``,
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

    Returns:
        A bound ``Context`` ready to pass into widgets and builders.

    Side effects:
        Constructs and binds a fresh ``Dispatcher``.
    """

    dispatcher = Dispatcher()
    keyboard = KeyboardService(cast(Any, keyboard_backend))
    if components is None:
        # Lazy import: avoids pulling Qt-bound builders into modules
        # that import this helper purely for the Context type.
        from ..components import register_components

        components = ComponentRegistry()
        register_components(components)
    context = Context(
        config=config or build_default_app_config(),
        dispatcher=dispatcher,
        keyboard=keyboard,
        state=StateStore(),
        components=components,
        surfaces=surfaces or SurfaceRegistry(),
    )
    dispatcher.bind_context(context)
    return context
