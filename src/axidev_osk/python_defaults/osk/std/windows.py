"""Window helpers built only from ``osk`` primitives.

Library state lives under ``std.ghosted.<window id>``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ... import osk

GHOST_OPACITY = 0.01


def visible(state: Any, window: str) -> bool:
    return bool(osk.read(state, ["windows", window, "visible"]))


def ghosted(state: Any, window: str) -> bool:
    return bool(osk.read(state, ["std", "ghosted", window]))


def toggle(ctx: Any, window: str) -> osk.Map:
    """Show a hidden window or hide a visible one."""

    return osk.window.hide(window) if visible(ctx.state, window) else osk.window.show(window)


def unghost(window: str, opacity: float) -> list[osk.Map]:
    return [
        osk.window.set_opacity(window, opacity),
        osk.window.unblock_input(window),
        osk.state.set(["std", "ghosted", window], None),
    ]


def ghost(window: str, allowed: list[str]) -> list[osk.Map]:
    return [
        osk.window.set_opacity(window, GHOST_OPACITY),
        osk.window.block_input(window, allowed),
        osk.state.set(["std", "ghosted", window], True),
    ]


def ghost_button(window: str, opacity: float, opts: Mapping[str, Any] | None = None) -> osk.Map:
    """A button that fades ``window`` and lets clicks pass through it, except on itself.

    ``opacity`` is the window's normal opacity, restored when the button is
    pressed again.
    """

    node_id = (opts or {}).get("id", f"ghost:{window}")

    def on_press(ctx: Any, event: Any) -> list[osk.Map]:
        del event
        if ghosted(ctx.state, window):
            return unghost(window, opacity)
        return ghost(window, [node_id])

    defaults = {
        "id": node_id,
        "label": "Ghost",
        "latched": lambda state: ghosted(state, window),
        "on_press": on_press,
    }
    return osk.button(**osk.merge(defaults, opts))


def corner_toggle(ctx: Any, window: str, opacity: float) -> list[osk.Map]:
    """Bring a ghosted or minimized window back, otherwise toggle it."""

    state = ctx.state
    if ghosted(state, window):
        return [*unghost(window, opacity), osk.window.show(window)]
    if osk.read(state, ["windows", window, "minimized"]):
        return [osk.window.show(window)]
    return [toggle(ctx, window)]
