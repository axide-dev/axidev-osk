"""Runtime registries for component and surface builders."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from ..config.models import ComponentConfig, SurfaceConfig

if TYPE_CHECKING:
    from .context import Context


ComponentBuilder = Callable[..., QWidget]
SurfaceBuilder = Callable[[SurfaceConfig, "Context"], QWidget]


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
