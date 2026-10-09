"""Standard library: keyboard conventions built only from ``osk`` primitives."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import keys, prompts, windows

__all__ = ["keys", "prompts", "windows", "with_handlers"]


def with_handlers(on: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a profile ``on`` table with the event handlers the library needs added.

    The library clears its latches on ``keyboard.reset`` and its ghost flags on
    ``window.state_changed``. A profile handler for the same event runs after
    the library's.
    """

    library = {"keyboard.reset": keys.on_reset, "window.state_changed": windows.on_window_state}
    merged: dict[str, Any] = dict(on or {})
    for event, handler in library.items():
        existing = merged.get(event)
        if existing is None:
            merged[event] = handler
        else:
            merged[event] = [handler, *(existing if isinstance(existing, list) else [existing])]
    return merged
