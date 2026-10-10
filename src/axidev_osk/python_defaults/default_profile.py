"""Default profile: the bundled US ISO keyboard, written like a Lua config.

Everything here is profile knowledge: the layout table, the grid math that
places keys, which keys latch, the prompts, and how corners and quit requests
behave. The engine knows none of it.
"""

from __future__ import annotations

from typing import Any

from . import osk
from .osk import std
from .osk.std import keys, prompts, windows
from .theme import DEFAULT_FONT, DEFAULT_PALETTE, DEFAULT_QSS, HOT_CORNER_INDICATOR, POINTER_LOCATOR

KEYBOARD = "keyboard"
KEYBOARD_OPACITY = 0.85
DWELL = "keyboard-dwell"
QUIT_PROMPT = "quit-prompt"
PERMISSION_PROMPT = "permission-prompt"
LOGOUT_NOTICE = "permission-logout"
TERMINAL_NOTICE = "permission-terminal-opened"
NO_TERMINAL_NOTICE = "permission-no-terminal"

UNIT = 4
NAV_START = 68
KEY_UNIT_PX = 48
GRID_GAP_PX = 4
OVERLAY = {"placement": "center", "screen_margin": 16}

# One entry per key: row, column in quarter units, width in key units, then
# what the key is. Kinds: key, letter, shifted, modifier, lock, ghost, dwell.
LAYOUT: list[tuple[Any, ...]] = [
    (0, 0, 1.0, "key", "Esc", "Escape"),
    *[(0, column, 1.0, "key", f"F{number}", f"F{number}") for number, column in enumerate(
        (8, 12, 16, 20, 28, 32, 36, 40, 48, 52, 56, 60), start=1)],
    (0, 64, 1.0, "dwell"),
    (0, 68, 1.0, "key", "PrtSc", "PrintScreen"),
    (0, 72, 1.0, "key", "ScrLk", "ScrollLock"),
    (0, 76, 1.0, "key", "Pause", "Pause"),
    (1, 0, 1.0, "shifted", "`", "~", "`"),
    (1, 4, 1.0, "shifted", "1", "!", "1"),
    (1, 8, 1.0, "shifted", "2", "@", "2"),
    (1, 12, 1.0, "shifted", "3", "#", "3"),
    (1, 16, 1.0, "shifted", "4", "$", "4"),
    (1, 20, 1.0, "shifted", "5", "%", "5"),
    (1, 24, 1.0, "shifted", "6", "^", "6"),
    (1, 28, 1.0, "shifted", "7", "&", "7"),
    (1, 32, 1.0, "shifted", "8", "*", "8"),
    (1, 36, 1.0, "shifted", "9", "(", "9"),
    (1, 40, 1.0, "shifted", "0", ")", "0"),
    (1, 44, 1.0, "shifted", "-", "_", "-"),
    (1, 48, 1.0, "shifted", "=", "+", "="),
    (1, 52, 2.0, "key", "Backspace", "Backspace"),
    (1, 68, 1.0, "key", "Ins", "Insert"),
    (1, 72, 1.0, "key", "Home", "Home"),
    (1, 76, 1.0, "key", "PgUp", "PageUp"),
    (2, 0, 1.5, "key", "Tab", "Tab"),
    *[(2, 6 + 4 * index, 1.0, "letter", char) for index, char in enumerate("qwertyuiop")],
    (2, 46, 1.0, "shifted", "[", "{", "["),
    (2, 50, 1.0, "shifted", "]", "}", "]"),
    (2, 54, 1.0, "ghost"),
    (2, 68, 1.0, "key", "Del", "Delete"),
    (2, 72, 1.0, "key", "End", "End"),
    (2, 76, 1.0, "key", "PgDn", "PageDown"),
    (3, 0, 1.75, "lock", "Caps", "CapsLock"),
    *[(3, 7 + 4 * index, 1.0, "letter", char) for index, char in enumerate("asdfghjkl")],
    (3, 43, 1.0, "shifted", ";", ":", ";"),
    (3, 47, 1.0, "shifted", "'", '"', "'"),
    (3, 51, 2.25, "key", "Enter", "Enter"),
    (4, 0, 1.25, "modifier", "Shift", "ShiftLeft"),
    (4, 5, 1.0, "shifted", "\\", "|", "\\"),
    *[(4, 9 + 4 * index, 1.0, "letter", char) for index, char in enumerate("zxcvbnm")],
    (4, 37, 1.0, "shifted", ",", "<", ","),
    (4, 41, 1.0, "shifted", ".", ">", "."),
    (4, 45, 1.0, "shifted", "/", "?", "/"),
    (4, 49, 2.75, "modifier", "Shift", "ShiftRight"),
    (4, 72, 1.0, "key", "↑", "Up"),
    (5, 0, 1.25, "modifier", "Ctrl", "CtrlLeft"),
    (5, 5, 1.25, "modifier", "Super", "SuperLeft"),
    (5, 10, 1.25, "modifier", "Alt", "AltLeft"),
    (5, 15, 6.25, "key", "Space", "Space"),
    (5, 40, 1.25, "modifier", "AltGr", "AltRight"),
    (5, 45, 1.25, "modifier", "Super", "SuperRight"),
    (5, 50, 1.25, "key", "Menu", "Menu"),
    (5, 55, 1.25, "modifier", "Ctrl", "CtrlRight"),
    (5, 68, 1.0, "key", "←", "Left"),
    (5, 72, 1.0, "key", "↓", "Down"),
    (5, 76, 1.0, "key", "→", "Right"),
]


def _dense_columns(entries: list[tuple[Any, ...]]) -> dict[int, int]:
    """Map sparse quarter-unit columns to grid columns, dropping empty ones."""

    occupied = sorted({column + offset for _row, column, width, *_ in entries for offset in range(int(width * UNIT))})
    return {column: index for index, column in enumerate(occupied)}


def _cells() -> list[dict[str, int]]:
    body = [entry for entry in LAYOUT if entry[0] > 0]
    function_left = [entry for entry in LAYOUT if entry[0] == 0 and entry[1] < NAV_START]
    body_columns = _dense_columns(body)
    left_columns = _dense_columns(function_left)
    cells = []
    for row, column, width, *_ in LAYOUT:
        columns = left_columns if row == 0 and column < NAV_START else body_columns
        cells.append({"row": row, "column": columns[column], "row_span": 1, "column_span": int(width * UNIT)})
    return cells


def _key_node(entry: tuple[Any, ...], cell: dict[str, int]) -> osk.Map:
    _row, _column, width, kind, *arguments = entry
    placement = {
        "cell": cell,
        "min_width": max(KEY_UNIT_PX, round(KEY_UNIT_PX * width)),
        "min_height": KEY_UNIT_PX,
    }
    if kind == "key":
        label, output = arguments
        return keys.key(label, output, placement)
    if kind == "letter":
        return keys.letter(arguments[0], placement)
    if kind == "shifted":
        label, shifted_label, output = arguments
        return keys.shifted(label, shifted_label, output, placement)
    if kind == "modifier":
        label, output = arguments
        return keys.modifier(label, output, placement)
    if kind == "lock":
        label, output = arguments
        return keys.lock(label, output, placement)
    if kind == "ghost":
        return windows.ghost_button(KEYBOARD, {"id": "ghost", **placement})
    if kind == "dwell":
        return _dwell_button(placement)
    raise ValueError(f"Unknown layout entry kind {kind!r}")


def _dwell_button(placement: osk.Map) -> osk.Map:
    def dwell_enabled(state: Any) -> bool:
        return bool(osk.read(state, ["dwell", DWELL, "enabled"]))

    def toggle(ctx: Any, event: Any) -> list[osk.Map]:
        del event
        return [osk.dwell.set_enabled(DWELL, not dwell_enabled(ctx.state))]

    return osk.button(id="dwell", label="Dwell", latched=dwell_enabled, on_release=toggle, **placement)


def keyboard_window() -> osk.Map:
    return osk.window(
        id=KEYBOARD,
        title="axidev OSK",
        opacity=KEYBOARD_OPACITY,
        show_on_start=True,
        default_close=False,
        overlay=OVERLAY,
        chrome={"enabled": True},
        content=osk.box(
            id="keyboard-surface",
            margins=[10, 10, 10, 10],
            spacing=8,
            children=[
                osk.grid(
                    id="keyboard-grid",
                    spacing=GRID_GAP_PX,
                    style={"object_name": "keyboard"},
                    children=[_key_node(entry, cell) for entry, cell in zip(LAYOUT, _cells(), strict=True)],
                ),
                osk.label(
                    id="keyboard-status",
                    text=lambda state: osk.read(state, "keyboard.status") or "",
                    visible=lambda state: not osk.read(state, "keyboard.ready"),
                    word_wrap=True,
                    style={"object_name": "statusLabel"},
                ),
            ],
        ),
    )


def _hide(window: str) -> osk.Callback:
    return lambda ctx, event: [osk.window.hide(window)]


def _notice(window: str, title: str, message: str | osk.Binding) -> osk.Map:
    return prompts.prompt_window(
        window,
        title=title,
        message=message,
        glyph="i",
        buttons=[prompts.prompt_button(f"{window}:ok", "OK", _hide(window), accept=True)],
        opts={"overlay": OVERLAY},
    )


def prompt_windows() -> list[osk.Map]:
    return [
        prompts.prompt_window(
            QUIT_PROMPT,
            title="Close axidev-osk?",
            message="Do you want to close axidev-osk? This will stop OSK input.",
            danger=True,
            hint=(
                "Tip: if you only want to hide OSK, move your cursor into "
                "the screen corner; the hot-corner sensor will hide it without "
                "shutting the app down."
            ),
            opts={"overlay": OVERLAY},
            buttons=[
                prompts.prompt_button(f"{QUIT_PROMPT}:yes", "Yes", lambda ctx, event: [osk.app.quit()], accept=True),
                prompts.prompt_button(f"{QUIT_PROMPT}:no", "No", _hide(QUIT_PROMPT), accept=False),
            ],
        ),
        prompts.prompt_window(
            PERMISSION_PROMPT,
            title="Linux Input Permission",
            message="Keyboard output is blocked by Linux permissions.",
            glyph="?",
            hint=(
                "Choose Open In Terminal to run permission setup where sudo can prompt. "
                "If you already ran setup, this session may just need a log out and back in."
            ),
            opts={"overlay": OVERLAY, "minimum_size": [560, 150]},
            buttons=[
                osk.button(
                    id=f"{PERMISSION_PROMPT}:open_terminal",
                    label="Open In Terminal",
                    on_release=lambda ctx, event: [
                        osk.window.hide(PERMISSION_PROMPT),
                        osk.linux.open_permission_setup(),
                    ],
                ),
                osk.button(
                    id=f"{PERMISSION_PROMPT}:already_configured",
                    label="Already Configured",
                    on_release=lambda ctx, event: [
                        osk.window.hide(PERMISSION_PROMPT),
                        osk.window.show(LOGOUT_NOTICE),
                    ],
                ),
                osk.button(
                    id=f"{PERMISSION_PROMPT}:cancel",
                    label="Cancel",
                    on_release=_hide(PERMISSION_PROMPT),
                ),
            ],
        ),
        _notice(
            LOGOUT_NOTICE,
            "Log Out Required",
            "The Linux permission setup may already be applied, but this desktop session "
            "does not have the updated group membership yet.\n\n"
            "Log out and back in, then relaunch axidev-osk and test keyboard output again.",
        ),
        _notice(
            TERMINAL_NOTICE,
            "Terminal Opened",
            "A terminal window was opened for Linux permission setup.\n\n"
            "Complete the sudo prompt there. When setup finishes, log out and back in, "
            "then relaunch axidev-osk and test keyboard output again.",
        ),
        _notice(
            NO_TERMINAL_NOTICE,
            "No Terminal Launcher Found",
            lambda state: osk.read(state, "keyboard.permission_setup_text") or "",
        ),
    ]


def _on_close_requested(ctx: Any, event: Any) -> list[osk.Map]:
    """Closing the keyboard asks first; every other window keeps the engine's close rule."""

    if event["window"] == KEYBOARD:
        return [osk.window.show(QUIT_PROMPT)]
    return []


def _on_permission_setup_opened(ctx: Any, event: Any) -> list[osk.Map]:
    return [osk.window.show(TERMINAL_NOTICE if event["opened"] else NO_TERMINAL_NOTICE)]


def build_default_config() -> osk.Map:
    """Return the root config of the bundled keyboard, the profile the app runs."""

    return osk.config(
        active_profile="default",
        profiles={
            "default": osk.profile(
                theme={"qss": DEFAULT_QSS, "palette": DEFAULT_PALETTE, "font": DEFAULT_FONT},
                windows=[keyboard_window(), *prompt_windows()],
                attachments=[
                    osk.dwell(
                        id=DWELL,
                        window=KEYBOARD,
                        enabled=False,
                        delay_ms=200,
                        dead_zone_px=10,
                        full_speed_px_s=20,
                        stop_speed_px_s=240,
                        maximum_progress_rate=1.75,
                        indicator_start_progress=0.25,
                        direction_reversal_progress_factor=0.5,
                        movement_penalty_px=15,
                        distance_curve_full_px=200,
                        velocity_release_ms=100,
                    ),
                    osk.pointer_locator(
                        id="keyboard-locator",
                        window=KEYBOARD,
                        radius_percent=30,
                        maximum_opacity_percent=60,
                        radius_standard_deviations=3,
                        **POINTER_LOCATOR,
                    ),
                    osk.hot_corners(
                        id="hot-corners",
                        corners=["top_left", "top_right", "bottom_left", "bottom_right"],
                        **HOT_CORNER_INDICATOR,
                    ),
                    osk.secure_input_panel(id="lock-screen-panel", window=KEYBOARD),
                ],
                on=std.with_handlers(
                    {
                        "hot_corner.triggered": lambda ctx, event: windows.corner_toggle(ctx.state, KEYBOARD),
                        "window.close_requested": _on_close_requested,
                        "app.quit_requested": lambda ctx, event: [osk.window.show(QUIT_PROMPT)],
                        "app.activated": lambda ctx, event: windows.reveal(ctx.state, KEYBOARD),
                        "keyboard.permission_required": lambda ctx, event: [osk.window.show(PERMISSION_PROMPT)],
                        "linux.permission_setup_opened": _on_permission_setup_opened,
                    }
                ),
            )
        },
    )
