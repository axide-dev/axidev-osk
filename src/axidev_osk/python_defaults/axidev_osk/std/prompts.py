"""Prompt windows built only from ``axidev_osk`` primitives.

A prompt is an ordinary window that starts hidden. Profiles show it with
``axidev_osk.window.show`` and give each button its own ``on_release`` callback.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ... import axidev_osk

ACCEPT_QSS = """
QPushButton#confirmAcceptButton {
    background-color: rgba(38, 132, 70, 0.25);
    border: 1px solid rgba(80, 200, 120, 0.85);
    color: #d8ffe3;
}
QPushButton#confirmAcceptButton:hover {
    background-color: rgba(56, 168, 90, 0.45);
    border-color: rgba(120, 230, 150, 1.0);
}
QPushButton#confirmAcceptButton:pressed {
    background-color: rgba(30, 110, 58, 0.85);
}
"""

REJECT_QSS = """
QPushButton#confirmRejectButton {
    background-color: rgba(160, 40, 50, 0.25);
    border: 1px solid rgba(220, 90, 100, 0.85);
    color: #ffe1e3;
}
QPushButton#confirmRejectButton:hover {
    background-color: rgba(190, 60, 70, 0.45);
    border-color: rgba(240, 130, 140, 1.0);
}
QPushButton#confirmRejectButton:pressed {
    background-color: rgba(140, 30, 40, 0.85);
}
"""

_SPACING = 14

_HINT_QSS = (
    "QLabel {"
    "  color: rgba(220, 220, 220, 0.65);"
    "  font-size: 14px;"
    "  font-style: italic;"
    "  margin: 0px;"
    "  padding: 2px 2px;"
    "  border-left: 2px solid rgba(180, 180, 180, 0.35);"
    "}"
)


def prompt_button(
    id: str,  # noqa: A002
    label: str,
    on_release: axidev_osk.Callback,
    *,
    accept: bool,
    opts: Mapping[str, Any] | None = None,
) -> axidev_osk.Map:
    """A prompt action button styled as accepting or rejecting."""

    glyph = "✔" if accept else "✖"
    defaults = {
        "id": id,
        "label": f"{glyph}  {label}",
        "on_release": on_release,
        "style": {
            "object_name": "confirmAcceptButton" if accept else "confirmRejectButton",
            "qss": ACCEPT_QSS if accept else REJECT_QSS,
        },
    }
    return axidev_osk.button(**axidev_osk.merge(defaults, opts))


def prompt_window(
    id: str,  # noqa: A002
    *,
    title: str,
    message: str | axidev_osk.Binding,
    buttons: Sequence[axidev_osk.Map],
    glyph: str = "!",
    hint: str | axidev_osk.Binding | None = None,
    danger: bool = False,
    opts: Mapping[str, Any] | None = None,
) -> axidev_osk.Map:
    """A hidden, fully opaque window with a glyph, a message, an optional hint, and buttons.

    ``opts`` replaces any window field, such as ``overlay``, ``minimum_size``,
    or the whole ``content``.
    """

    badge_background = "#d83a3a" if danger else "#ffd866"
    badge_foreground = "#fff5f5" if danger else "#1a1a1a"
    rows: list[axidev_osk.Map] = [
        axidev_osk.box(
            id=f"{id}:message-row",
            direction="horizontal",
            spacing=_SPACING,
            children=[
                axidev_osk.label(
                    id=f"{id}:glyph",
                    text=glyph,
                    align="center",
                    min_width=40,
                    min_height=40,
                    max_width=40,
                    max_height=40,
                    style={
                        "qss": (
                            "QLabel {"
                            f"  background-color: {badge_background};"
                            f"  color: {badge_foreground};"
                            "  border-radius: 20px;"
                            "  font-size: 22px;"
                            "  font-weight: 900;"
                            "}"
                        )
                    },
                ),
                axidev_osk.label(
                    id=f"{id}:message",
                    text=message,
                    word_wrap=True,
                    stretch=1,
                    style={"qss": "QLabel { margin: 0px; padding: 0px; }"},
                ),
            ],
        )
    ]
    if hint is not None:
        rows.append(
            axidev_osk.label(id=f"{id}:hint", text=hint, word_wrap=True, align="top_left", style={"qss": _HINT_QSS})
        )
    rows.append(axidev_osk.box(id=f"{id}:buttons", direction="horizontal", spacing=8, children=list(buttons)))
    defaults = {
        "id": id,
        "title": title,
        "opacity": 1.0,
        "show_on_start": False,
        "chrome": {"enabled": False},
        "minimum_size": [460, 120],
        "content": axidev_osk.box(id=f"{id}:content", margins=[18, 18, 18, 16], spacing=_SPACING, children=rows),
    }
    return axidev_osk.window(**axidev_osk.merge(defaults, opts))
