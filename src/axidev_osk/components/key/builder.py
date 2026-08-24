"""Builders for keyboard key and spacer components."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...config.models import ComponentConfig, KeyboardMetrics, KeyConfig, SpacerConfig
from ...runtime.context import Context
from ...runtime.registries import ComponentRegistry
from ...runtime.source import SourcePath


@runtime_checkable
class KeyboardGridHost(Protocol):
    """Host interface required by key and spacer component builders."""

    @property
    def key_metrics(self) -> KeyboardMetrics:
        """Pixel metrics inherited by child key/spacer components."""
        ...

    def build_key_from_config(
        self,
        config: KeyConfig,
        context: Context,
        source_path: SourcePath,
    ) -> QWidget:
        """Build a key child using the owning grid's runtime wiring."""
        ...


def register(registry: ComponentRegistry) -> None:
    """Register key-related component builders.

    Args:
        registry: Component registry owned by the runtime context.

    Returns:
        None.

    Side effects:
        Mutates the registry.
    """

    registry.register("key", build_key_component)
    registry.register("spacer", build_spacer_component)


def build_key_component(
    config: ComponentConfig,
    context: Context,
    *,
    source_path: SourcePath,
    host: QWidget | None = None,
) -> QWidget:
    """Build a key button component.

    Args:
        config: Key component config.
        context: Runtime context.
        source_path: Exact runtime identity used for interactions and state.
        host: Containing keyboard grid that owns placement and rendering.

    Returns:
        Constructed key button widget.

    Side effects:
        Registers the key with its host for runtime snapshot rendering.
    """

    if not isinstance(config, KeyConfig):
        raise TypeError(f"Expected KeyConfig, got {type(config).__name__}")
    if not isinstance(host, KeyboardGridHost):
        raise RuntimeError(
            "Key components must be built with a keyboard grid host; "
            "the parent grid is responsible for forwarding host=self."
        )
    return host.build_key_from_config(config, context, source_path)


def build_spacer_component(
    config: ComponentConfig,
    context: Context,
    *,
    source_path: SourcePath,
    host: QWidget | None = None,
) -> QWidget:
    """Build a spacer component.

    Args:
        config: Spacer component config.
        context: Runtime context.
        host: Optional containing grid; used to inherit pixel metrics so
            the spacer aligns with neighboring keys. Falls back to default
            metrics when the host is not a ``KeyboardWidget``.

    Returns:
        Transparent spacer widget.

    Side effects:
        None beyond widget construction.
    """

    del context, source_path
    if not isinstance(config, SpacerConfig):
        raise TypeError(f"Expected SpacerConfig, got {type(config).__name__}")
    metrics = host.key_metrics if isinstance(host, KeyboardGridHost) else KeyboardMetrics()
    spacer = QWidget()
    spacer.setProperty("componentType", "spacer")
    spacer.setProperty("componentId", config.id)
    spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    spacer.setMinimumWidth(metrics.span_width(config.visual.width))
    spacer.setMinimumHeight(metrics.span_height(config.visual.height))
    spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return spacer
