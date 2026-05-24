"""Runtime service wrappers around backend integrations."""

from __future__ import annotations

from collections.abc import Set

from PySide6.QtCore import QObject

from ..hot_corner.service import HotCornerService
from ..runtime.registries import ServiceRegistry
from .keyboard import KeyboardService
from .windows_topmost import WindowsTopmostService


def register_services(
    registry: ServiceRegistry,
    *,
    include: Set[str] | None = None,
    keyboard: KeyboardService | None = None,
    parent: QObject | None = None,
) -> None:
    """Register bundled runtime services.

    Args:
        registry: Mutable service registry populated in deterministic order.
        include: Optional set limiting registered service names.
        keyboard: Optional keyboard service, primarily for tests.
        parent: Optional Qt parent for controller-backed services.

    Returns:
        None.

    Side effects:
        Mutates ``registry``.
    """

    if include is None or "keyboard" in include:
        registry.register("keyboard", keyboard or KeyboardService())
    if include is None or "hot_corner" in include:
        registry.register("hot_corner", HotCornerService(parent=parent))
    if include is None or "windows_topmost" in include:
        registry.register("windows_topmost", WindowsTopmostService(parent=parent))

__all__ = ["KeyboardService", "WindowsTopmostService", "register_services"]
