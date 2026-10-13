"""A notice window that tells the user when a callback, binding, or action failed.

The engine reports every failure as ``callback.failed`` or ``action.failed``
and keeps running. ``notice_window`` builds a hidden prompt window, and
``on_callback_failed`` and ``on_action_failed`` append each failure to a list
with ``state.append``, so failures queued together all land, and show the
notice with the hint the engine sends with them. The notice shows each
different failure once, oldest first, with a count when it repeated, so a
binding that keeps failing adds one line, not hundreds. OK hides the notice
and clears the list. A failure of the notice itself, or of these two handlers, is not shown, so it
cannot report itself in a loop.
``std.with_handlers(failure_notice=True)`` adds both handlers; the profile adds
the window to its ``windows``.

Library state lives under ``std.failure``: every failure since the last OK, and the hint.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ... import axidev_osk
from . import prompts

NOTICE = "std:failure-notice"

STATE = {
    "failure": axidev_osk.var(
        axidev_osk.record({"entries": axidev_osk.var(axidev_osk.list_of("string")), "hint": axidev_osk.var("string", "")})
    )
}
"""The library's failure variables, merged under ``std`` by ``std.with_state``."""


def notice_window(opts: Mapping[str, Any] | None = None) -> axidev_osk.Map:
    """The hidden notice window; ``opts`` replaces any window field."""

    return prompts.prompt_window(
        NOTICE,
        title="Something failed",
        message=lambda state: _lines(axidev_osk.read(state, "std.failure.entries")),
        hint=lambda state: axidev_osk.read(state, "std.failure.hint"),
        danger=True,
        buttons=[
            prompts.prompt_button(
                f"{NOTICE}:ok",
                "OK",
                lambda ctx, event: [axidev_osk.window.hide(NOTICE), axidev_osk.state.set("std.failure", None)],
                accept=True,
            )
        ],
        opts=opts,
    )


def on_callback_failed(ctx: Any, event: Any) -> list[axidev_osk.Map]:
    if event["source"] in _OWN_EVENTS:
        # A failing failure handler would otherwise report itself forever.
        return []
    what = "A binding" if event["kind"] == "binding" else "A callback"
    return _show(ctx, event, f"{what} of {event['source']} failed: {event['exception_type']}: {event['message']}")


def on_action_failed(ctx: Any, event: Any) -> list[axidev_osk.Map]:
    if _from_notice(event["arguments"]):
        # Showing the notice failed; showing it again would fail the same way, forever.
        return []
    return _show(
        ctx,
        event,
        f"The action {event['action']} failed while it was {_STAGES.get(event['stage'], event['stage'])}: "
        f"{event['exception_type']}: {event['message']}",
    )


_STAGES = {"lookup": "looked up", "decode": "read", "execute": "run"}
_OWN_EVENTS = ("callback.failed", "action.failed")


def _from_notice(arguments: Any) -> bool:
    """Whether a failed action was one the notice itself sends."""

    path = arguments.get("path")
    path = path.split(".") if isinstance(path, str) else path
    return arguments.get("window") == NOTICE or (isinstance(path, list) and path[:2] == ["std", "failure"])


def _show(ctx: Any, event: Any, text: str) -> list[axidev_osk.Map]:
    actions = [axidev_osk.state.append("std.failure.entries", text), axidev_osk.state.set("std.failure.hint", event["hint"])]
    if not axidev_osk.read(ctx.state, ["windows", NOTICE, "visible"]):
        actions.append(axidev_osk.window.show(NOTICE))
    return actions


def _lines(entries: list[str]) -> str:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry] = counts.get(entry, 0) + 1
    return "\n".join(entry + (f" \u00d7{count}" if count > 1 else "") for entry, count in counts.items())
