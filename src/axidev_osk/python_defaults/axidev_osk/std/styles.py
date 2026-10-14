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


def merge_style(base: Any, extra: Any) -> axidev_osk.Map:
    """``base`` with ``extra`` added: a field of ``extra`` replaces the same field of ``base``, except ``properties``.

    The two ``properties`` merge, each a map or a binding, with ``extra``'s
    winning where both set a property, so a profile's style never drops the
    properties a helper lights its widget with.
    """

    merged = {**(base or {}), **(extra or {})}
    first: Any = (base or {}).get("properties")
    second: Any = (extra or {}).get("properties")
    if first is not None and second is not None:

        def properties(state: Any) -> dict[str, Any]:
            return {**_resolve(first, state), **_resolve(second, state)}

        merged["properties"] = properties
    return merged


def _resolve(value: Any, state: Any) -> Any:
    """A value, or what a binding returns for ``state``."""

    return value(state) if callable(value) else value
