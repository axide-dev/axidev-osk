"""Window helpers built only from ``osk`` primitives.

Library state lives under ``std.ghosted.<window id>``. Ghosting fades a window
and lets clicks pass through it except on the Ghost button. The flag is the
only source: a ghostable window binds its ``opacity`` with ``ghost_opacity``
and its ``input_blocked`` with ``ghost_blocked``, so a rebuilt window comes
back in the right state on its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ... import osk

GHOST_OPACITY = 0.01

STATE = {"ghosted": osk.var(osk.map_of("boolean"))}
"""The library's window variables, merged under ``std`` by ``std.with_state``."""


def visible(state: Any, window: str) -> bool:
    return bool(osk.read(state, ["windows", window, "visible"]))


def minimized(state: Any, window: str) -> bool:
    return bool(osk.read(state, ["windows", window, "minimized"]))


def ghosted(state: Any, window: str) -> bool:
    return bool(osk.read(state, ["std", "ghosted", window]))


def ghost_opacity(window: str, opacity: float | osk.Binding) -> osk.Binding:
    """A window ``opacity`` binding: almost transparent while ghosted, otherwise ``opacity``."""

    def bound(state: Any) -> float:
        if ghosted(state, window):
            return GHOST_OPACITY
        return opacity(state) if callable(opacity) else opacity

    return bound


def ghost_blocked(window: str) -> osk.Binding:
    """A window ``input_blocked`` binding: clicks pass through while ghosted."""

    return lambda state: ghosted(state, window)


def ghost(window: str) -> list[osk.Map]:
    return [osk.state.set(["std", "ghosted", window], True)]


def unghost(window: str) -> list[osk.Map]:
    return [osk.state.set(["std", "ghosted", window], None)]


def reveal(state: Any, window: str) -> list[osk.Map]:
    """Show a window, bringing it back from ghost first."""

    if ghosted(state, window):
        return [*unghost(window), osk.window.show(window)]
    return [osk.window.show(window)]


def toggle(state: Any, window: str) -> list[osk.Map]:
    """Hide a window on screen, or reveal a hidden or minimized one."""

    if visible(state, window) and not minimized(state, window):
        return [osk.window.hide(window)]
    return reveal(state, window)


def ghost_button(window: str, opts: Mapping[str, Any] | None = None) -> osk.Map:
    """A button that ghosts ``window`` and unghosts it when pressed again; it takes clicks while ghosted."""

    def on_press(ctx: Any, event: Any) -> list[osk.Map]:
        del event
        if ghosted(ctx.state, window):
            return unghost(window)
        return ghost(window)

    defaults = {
        "id": f"ghost:{window}",
        "label": "Ghost",
        "passes_input_block": True,
        "on_press": on_press,
    }
    return osk.button(**osk.merge(defaults, opts))


def corner_toggle(state: Any, window: str) -> list[osk.Map]:
    """Bring a ghosted window back, otherwise toggle it."""

    if ghosted(state, window):
        return reveal(state, window)
    return toggle(state, window)
