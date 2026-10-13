"""Standard library: keyboard conventions built only from ``axidev_osk`` primitives."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from . import controls, keys, locator, prompts, styles, windows
from .styles import lit

__all__ = ["controls", "keys", "lit", "locator", "prompts", "styles", "windows", "with_handlers", "with_state"]


def with_state(state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a profile ``state`` map with the library's variables declared under ``std``."""

    merged: dict[str, Any] = dict(state or {})
    if "std" in merged:
        raise ValueError("Profile state cannot declare std; the library declares it")
    merged["std"] = {**keys.STATE, **windows.STATE, **controls.STATE, **locator.STATE}
    return merged


def with_handlers(
    on: Mapping[str, Any] | None = None, also: Sequence[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """Return a profile ``on`` table with the event handlers the library needs added.

    The library clears its latches on ``keyboard.reset``, moves and resizes a
    window its title bar or resize grip drags with the left mouse button, and
    left-clicks where a dwell completes. ``also`` adds handler tables some
    helpers give, such as ``locator.on``. A profile handler for the same event
    runs after the library's.
    """

    library = [
        {
            "keyboard.reset": keys.on_reset,
            "window.dragged": windows.on_dragged,
            "window.resize_dragged": windows.on_resize_dragged,
            "dwell.completed": windows.on_dwell_completed,
        },
        *also,
    ]
    merged: dict[str, Any] = dict(on or {})
    for table in reversed(library):
        for event, handler in table.items():
            existing = merged.get(event)
            if existing is None:
                merged[event] = handler
            else:
                merged[event] = [handler, *(existing if isinstance(existing, list) else [existing])]
    return merged
