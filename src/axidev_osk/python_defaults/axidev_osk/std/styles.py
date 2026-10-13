"""Style helpers built only from ``axidev_osk`` primitives."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ... import axidev_osk

Flag = bool | Callable[[Any], bool]
"""A fixed boolean, or a binding ``fn(state) -> bool``."""


def lit(active: Flag = False, latched: Flag = False) -> axidev_osk.Map:
    """A button style lit while ``active`` (its key is down) or ``latched`` (it holds) is true.

    It sets the properties the bundled theme targets: ``pressed``,
    ``latched``, and ``interactionState``, one of ``idle``, ``pressed``,
    ``latched``, or ``latched_pressed``.
    """

    def properties(state: Any) -> dict[str, Any]:
        is_active = bool(active(state) if callable(active) else active)
        is_latched = bool(latched(state) if callable(latched) else latched)
        if is_active and is_latched:
            interaction = "latched_pressed"
        elif is_active:
            interaction = "pressed"
        elif is_latched:
            interaction = "latched"
        else:
            interaction = "idle"
        return {"pressed": is_active, "latched": is_latched, "interactionState": interaction}

    return {"properties": properties}
