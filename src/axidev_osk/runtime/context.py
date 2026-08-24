"""Runtime context shared by builders, services, and controllers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..config.models import AppConfig
from .registries import ComponentRegistry, SurfaceRegistry
from .state_store import StateStore

if TYPE_CHECKING:
    from .dispatcher import Dispatcher
    from ..services.keyboard import KeyboardService


@dataclass(slots=True)
class Context:
    """Main-owned object exposing runtime boundaries to subsystems.

    Attributes:
        config: Loaded declarative app config.
        dispatcher: Synchronous dispatcher with queue-ready action/event shape.
        keyboard: Keyboard service wrapping backend access.
        state: Central state store.
        components: Component builder registry.
        surfaces: Surface builder registry.
    """

    config: AppConfig
    dispatcher: "Dispatcher"
    keyboard: "KeyboardService"
    state: StateStore
    components: ComponentRegistry
    surfaces: SurfaceRegistry
