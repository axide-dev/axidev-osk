"""Runtime context shared by builders, services, and controllers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..services.keyboard import KeyboardService
    from .dispatcher import Dispatcher
    from .engine import Engine


@dataclass(slots=True)
class Context:
    """Main-owned object exposing runtime boundaries to subsystems.

    Attributes:
        dispatcher: Queue that carries every event and action.
        keyboard: Keyboard service wrapping backend access.
        engine: Profile state, functions, node kinds, and bindings.
    """

    dispatcher: "Dispatcher"
    keyboard: "KeyboardService"
    engine: "Engine"
