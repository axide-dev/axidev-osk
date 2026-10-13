"""Window helpers built only from ``axidev_osk`` primitives.

Library state lives under ``std.ghosted.<window id>``. Ghosting fades a window
and lets clicks pass through it except on the Ghost button. The flag is the
only source: a ghostable window binds its ``opacity`` with ``ghost_opacity``
and its ``input_blocked`` with ``ghost_blocked``, so a rebuilt window comes
back in the right state on its own.

The engine reports title-bar drags, resize-grip drags, and finished dwells
without acting on them; ``on_dragged``, ``on_resize_dragged``, and
``on_dwell_completed`` give them their usual meaning, and ``std.with_handlers``
installs them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ... import axidev_osk

GHOST_OPACITY = 0.01

STATE = {"ghosted": axidev_osk.var(axidev_osk.map_of("boolean"))}
"""The library's window variables, merged under ``std`` by ``std.with_state``."""


def visible(state: Any, window: str) -> bool:
    return bool(axidev_osk.read(state, ["windows", window, "visible"]))


def minimized(state: Any, window: str) -> bool:
    return bool(axidev_osk.read(state, ["windows", window, "minimized"]))


def ghosted(state: Any, window: str) -> bool:
    return bool(axidev_osk.read(state, ["std", "ghosted", window]))


def ghost_opacity(window: str, opacity: float | axidev_osk.Binding) -> axidev_osk.Binding:
    """A window ``opacity`` binding: almost transparent while ghosted, otherwise ``opacity``."""

    def bound(state: Any) -> float:
        if ghosted(state, window):
            return GHOST_OPACITY
        return opacity(state) if callable(opacity) else opacity

    return bound


def ghost_blocked(window: str) -> axidev_osk.Binding:
    """A window ``input_blocked`` binding: clicks pass through while ghosted."""

    return lambda state: ghosted(state, window)


def ghost(window: str) -> list[axidev_osk.Map]:
    return [axidev_osk.state.set(["std", "ghosted", window], True)]


def unghost(window: str) -> list[axidev_osk.Map]:
    return [axidev_osk.state.set(["std", "ghosted", window], None)]


def reveal(state: Any, window: str) -> list[axidev_osk.Map]:
    """Show a window, bringing it back from ghost first."""

    if ghosted(state, window):
        return [*unghost(window), axidev_osk.window.show(window)]
    return [axidev_osk.window.show(window)]


def toggle(state: Any, window: str) -> list[axidev_osk.Map]:
    """Hide a window on screen, or reveal a hidden or minimized one."""

    if visible(state, window) and not minimized(state, window):
        return [axidev_osk.window.hide(window)]
    return reveal(state, window)


def ghost_button(window: str, opts: Mapping[str, Any] | None = None) -> axidev_osk.Map:
    """A button that ghosts ``window`` and unghosts it when pressed again; it takes clicks while ghosted."""

    def on_press(ctx: Any, event: Any) -> list[axidev_osk.Map]:
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
    return axidev_osk.button(**axidev_osk.merge(defaults, opts))


def corner_toggle(state: Any, window: str) -> list[axidev_osk.Map]:
    """Bring a ghosted window back, otherwise toggle it."""

    if ghosted(state, window):
        return reveal(state, window)
    return toggle(state, window)


def on_dragged(ctx: Any, event: Any) -> list[axidev_osk.Map]:
    """Move a window by as much as its title bar was dragged."""

    del ctx
    return [axidev_osk.window.move_by(event["window"], event["dx"], event["dy"])]


def on_resize_dragged(ctx: Any, event: Any) -> list[axidev_osk.Map]:
    """Resize a window by as much as its resize grip was dragged."""

    del ctx
    return [axidev_osk.window.resize_by(event["window"], event["dx"], event["dy"])]


def on_dwell_completed(ctx: Any, event: Any) -> list[axidev_osk.Map]:
    """Left-click where the pointer came to rest."""

    del ctx
    return [axidev_osk.window.click(event["window"], event["x"], event["y"])]
