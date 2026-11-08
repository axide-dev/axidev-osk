"""A notice window that tells the user when a callback, binding, or action failed.

The engine reports every failure as ``callback.failed`` or ``action.failed``
and keeps running. ``notice_window`` builds a hidden prompt window, and
``on_callback_failed`` and ``on_action_failed`` store each different failure
once, oldest first, and count how often it happened with ``state.add``, so
failures queued together all count and a binding that keeps failing adds one
line, not hundreds. OK hides the notice and clears what it stored.

A failure the notice causes is not shown, so it cannot report itself in a
loop: a failure of these two handlers, of an action the notice sends, or of a
callback or binding handling a change to ``std.failure`` or to the notice
window's observed state.
``std.with_handlers(failure_notice=True)`` adds both handlers; the profile adds
the window to its ``windows``.

Library state lives under ``std.failure``: ``entries`` lists every different
failure since the last OK, and ``counts`` maps each to how often it happened.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ... import axidev_osk
from . import prompts

NOTICE = "std:failure-notice"

HINT = "Run `axidev-osk check` to find configuration problems before they happen."
"""The notice's default advice under the failures; ``notice_window(hint=...)`` replaces it."""

STATE = {
    "failure": axidev_osk.var(
        axidev_osk.record(
            {"entries": axidev_osk.var(axidev_osk.list_of("string")), "counts": axidev_osk.var(axidev_osk.map_of("integer"))}
        )
    )
}
"""The library's failure variables, merged under ``std`` by ``std.with_state``."""


def notice_window(opts: Mapping[str, Any] | None = None, *, hint: str | None = HINT) -> axidev_osk.Map:
    """The hidden notice window; ``opts`` replaces any window field, and ``hint`` is the advice under the failures."""

    return prompts.prompt_window(
        NOTICE,
        title="Something failed",
        message=lambda state: _lines(axidev_osk.read(state, "std.failure")),
        hint=hint,
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
    if event["source"] in _OWN_EVENTS or _from_notice_change(event.get("during")):
        # A failing failure handler, or a function that fails on the notice's own change, would report itself forever.
        return []
    what = "A binding" if event["kind"] == "binding" else "A callback"
    return _show(ctx, f"{what} of {event['source']} failed: {event['exception_type']}: {event['message']}")


def on_action_failed(ctx: Any, event: Any) -> list[axidev_osk.Map]:
    if _from_notice(event["arguments"]):
        # Showing the notice failed; showing it again would fail the same way, forever.
        return []
    return _show(
        ctx,
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


def _from_notice_change(during: Any) -> bool:
    """Whether a function failed while handling a change to the notice's state or to its window."""

    if not during or during["event"] != "state.changed":
        return False
    path = during["arguments"]["path"]
    return path[:2] == ["std", "failure"] or path[:2] == ["windows", NOTICE]


def _show(ctx: Any, text: str) -> list[axidev_osk.Map]:
    actions: list[axidev_osk.Map] = []
    if axidev_osk.read(ctx.state, ["std", "failure", "counts", text]) is None:
        # Two reports of a new failure queued together both land here; the list shows the text once.
        actions.append(axidev_osk.state.append("std.failure.entries", text))
    actions.append(axidev_osk.state.add(["std", "failure", "counts", text], 1))
    if not axidev_osk.read(ctx.state, ["windows", NOTICE, "visible"]):
        actions.append(axidev_osk.window.show(NOTICE))
    return actions


def _lines(failure: Any) -> str:
    counts = failure["counts"]
    lines: list[str] = []
    for entry in failure["entries"]:
        line = entry + (f" \u00d7{counts[entry]}" if (counts[entry] or 0) > 1 else "")
        if line not in lines:
            lines.append(line)
    return "\n".join(lines)
