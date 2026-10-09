"""Window helpers built only from ``osk`` primitives.

Library state lives under ``std.ghosted.<window id>``. Ghosting fades a window
and lets clicks pass through it except on the allowed nodes; unghosting
restores the window's configured opacity (``windows.<id>.configured_opacity``).
Profiles route ``window.state_changed`` to ``on_window_state`` (``std.with_handlers``
does it) so the flag clears when the engine reports the window unblocked, for
example after the window was closed and rebuilt.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ... import osk

GHOST_OPACITY = 0.01


def visible(state: Any, window: str) -> bool:
    return bool(osk.read(state, ["windows", window, "visible"]))


def minimized(state: Any, window: str) -> bool:
    return bool(osk.read(state, ["windows", window, "minimized"]))


def ghosted(state: Any, window: str) -> bool:
    return bool(osk.read(state, ["std", "ghosted", window]))


def ghost(window: str, allowed: list[str]) -> list[osk.Map]:
    return [
        osk.window.block_input(window, allowed),
        osk.window.set_opacity(window, GHOST_OPACITY),
        osk.state.set(["std", "ghosted", window], True),
    ]


def unghost(state: Any, window: str) -> list[osk.Map]:
    actions = [osk.window.unblock_input(window), osk.state.set(["std", "ghosted", window], None)]
    opacity = osk.read(state, ["windows", window, "configured_opacity"])
    if opacity is not None:
        actions.insert(0, osk.window.set_opacity(window, opacity))
    return actions


def on_window_state(ctx: Any, event: Any) -> list[osk.Map]:
    """Clear the ghost flag of a window the engine reports as no longer blocking input."""

    window = event["window"]
    if not event["input_blocked"] and ghosted(ctx.state, window):
        return [osk.state.set(["std", "ghosted", window], None)]
    return []


def reveal(state: Any, window: str) -> list[osk.Map]:
    """Show a window, bringing it back from ghost first."""

    if ghosted(state, window):
        return [*unghost(state, window), osk.window.show(window)]
    return [osk.window.show(window)]


def toggle(state: Any, window: str) -> list[osk.Map]:
    """Hide a window on screen, or reveal a hidden or minimized one."""

    if visible(state, window) and not minimized(state, window):
        return [osk.window.hide(window)]
    return reveal(state, window)


def ghost_button(window: str, opts: Mapping[str, Any] | None = None) -> osk.Map:
    """A button that ghosts ``window`` except for itself, and unghosts it when pressed again."""

    node_id = (opts or {}).get("id", f"ghost:{window}")

    def on_press(ctx: Any, event: Any) -> list[osk.Map]:
        del event
        if ghosted(ctx.state, window):
            return unghost(ctx.state, window)
        return ghost(window, [node_id])

    defaults = {"id": node_id, "label": "Ghost", "on_press": on_press}
    return osk.button(**osk.merge(defaults, opts))


def corner_toggle(state: Any, window: str) -> list[osk.Map]:
    """Bring a ghosted window back, otherwise toggle it."""

    if ghosted(state, window):
        return reveal(state, window)
    return toggle(state, window)
