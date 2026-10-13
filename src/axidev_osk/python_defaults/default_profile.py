"""Default config: the bundled US ISO keyboard and a small social profile, written like a Lua config.

Everything here is profile knowledge: the layout table, the grid math that
places keys, which keys latch, the settings strip, the prompts, and how
corners and quit requests behave. The engine knows none of it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import axidev_osk
from .axidev_osk import std
from .axidev_osk.std import controls, keys, prompts, windows
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
# Closing a prompt cancels it, so the profile hides it instead of the engine asking to quit.
PROMPT_OPTS = {"overlay": OVERLAY, "default_close": False}

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


def _key_node(entry: tuple[Any, ...], cell: dict[str, int]) -> axidev_osk.Map:
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


# Settings every profile shares, so they survive a profile switch.
DWELL_SETTINGS: dict[str, tuple[str, Any]] = {
    "enabled": ("boolean", False),
    "delay_ms": ("integer", 200),
    "dead_zone_px": ("integer", 10),
    "full_speed_px_s": ("number", 20),
    "stop_speed_px_s": ("number", 240),
    "maximum_progress_rate": ("number", 1.75),
    "indicator_start_progress": ("number", 0.25),
    "direction_reversal_progress_factor": ("number", 0.5),
    "movement_penalty_px": ("number", 15),
    "distance_curve_full_px": ("number", 200),
    "velocity_release_ms": ("integer", 100),
}
SHARED_STATE = {
    "settings": {
        "opacity": axidev_osk.var("number", KEYBOARD_OPACITY),
        "dwell": {name: axidev_osk.var(var_type, default) for name, (var_type, default) in DWELL_SETTINGS.items()},
    }
}


def _setting(*path: str) -> axidev_osk.Binding:
    return lambda state: axidev_osk.read(state, ["settings", *path])


def _dwell_button(placement: axidev_osk.Map) -> axidev_osk.Map:
    enabled = _setting("dwell", "enabled")

    def toggle(ctx: Any, event: Any) -> list[axidev_osk.Map]:
        del event
        return [axidev_osk.state.set("settings.dwell.enabled", not enabled(ctx.state))]

    return axidev_osk.button(id="dwell", label="Dwell", style=std.lit(latched=enabled), on_release=toggle, **placement)


STRIP_STYLE = {"object_name": "settingsStrip"}

# Dwell option, caption, minimum, maximum, step, unit. Each range holds the
# default and stays inside the dwell validation; the full speed and stop speed
# bounds follow each other so the two never cross.
DWELL_STEPPERS: list[tuple[str, str, Any, Any, Any, str]] = [
    ("delay_ms", "Delay", 50, 2000, 50, " ms"),
    ("dead_zone_px", "Dead zone", 0, 50, 2, " px"),
    (
        "full_speed_px_s",
        "Full speed",
        0,
        lambda state: min(200, axidev_osk.read(state, "settings.dwell.stop_speed_px_s") - 5),
        5,
        " px/s",
    ),
    (
        "stop_speed_px_s",
        "Stop speed",
        lambda state: axidev_osk.read(state, "settings.dwell.full_speed_px_s") + 5,
        1000,
        20,
        " px/s",
    ),
    ("maximum_progress_rate", "Max progress rate", 1.0, 4.0, 0.25, ""),
    ("indicator_start_progress", "Indicator start", 0.0, 1.0, 0.05, ""),
    ("direction_reversal_progress_factor", "Reversal factor", 0.0, 1.0, 0.05, ""),
    ("movement_penalty_px", "Movement penalty", 1, 100, 1, " px"),
    ("distance_curve_full_px", "Distance curve", 10, 1000, 10, " px"),
    ("velocity_release_ms", "Velocity release", 10, 1000, 10, " ms"),
]


def _with_unit(unit: str) -> Any:
    def show(value: float) -> str:
        text = f"{value:.2f}" if isinstance(value, float) and not value.is_integer() else f"{value:g}"
        return f"{text}{unit}"

    return show


def _profile_dropdown(window: str, group: str) -> tuple[axidev_osk.Map, axidev_osk.Map]:
    return controls.dropdown(
        f"{window}:profile-menu",
        [(name, caption) for name, caption, _build in PROFILES],
        value=lambda state: axidev_osk.read(state, "app.profile"),
        on_select=lambda ctx, profile: [axidev_osk.profile.switch(profile)],
        label="Profile",
        group=group,
        panel_opts={"direction": "horizontal"},
    )


def _dwell_menu(window: str, group: str) -> tuple[axidev_osk.Map, axidev_osk.Map]:
    items: list[axidev_osk.Map] = [
        controls.checkbox(
            f"{window}:dwell-enabled",
            "Dwell enabled",
            "settings.dwell.enabled",
            {"cell": {"row": 0, "column": 0}},
        )
    ]
    for index, (name, caption, minimum, maximum, step, unit) in enumerate(DWELL_STEPPERS, start=1):
        items.append(
            controls.stepper(
                f"{window}:dwell-{name}",
                f"settings.dwell.{name}",
                minimum=minimum,
                maximum=maximum,
                step=step,
                label=caption,
                format=_with_unit(unit),
                opts={"cell": {"row": index // 2, "column": index % 2}},
            )
        )
    # The panel is a two-column grid rather than the default column of controls.
    return controls.menu(
        f"{window}:dwell-menu",
        "Dwell settings",
        items,
        group=group,
        panel_opts={"kind": "grid", "spacing": 6},
    )


def settings_strip(window: str) -> axidev_osk.Map:
    """The collapsed settings strip every window carries: profile, keyboard opacity, and dwell settings."""

    strip_id = f"{window}:strip"
    group = controls.strip_group(strip_id)
    profile_button, profile_panel = _profile_dropdown(window, group)
    dwell_button, dwell_panel = _dwell_menu(window, group)
    return controls.strip(
        strip_id,
        [
            profile_button,
            controls.stepper(
                f"{window}:opacity",
                "settings.opacity",
                minimum=0.3,
                maximum=1.0,
                step=0.05,
                label="Opacity",
                format=lambda value: f"{value:.2f}",
            ),
            dwell_button,
        ],
        panels=[profile_panel, dwell_panel],
        opts={"margins": [10, 0, 10, 2], "style": STRIP_STYLE},
    )


def _with_settings(windows: list[axidev_osk.Map]) -> list[axidev_osk.Map]:
    """Give every window the settings strip, which takes the place of its content's bottom margin."""

    framed = []
    for window in windows:
        content = window["content"]
        left, top, right, _bottom = content.get("margins", [0, 0, 0, 0])
        window = axidev_osk.merge(window, {"content": axidev_osk.merge(content, {"margins": [left, top, right, 0]})})
        framed.append(controls.with_strip(window, settings_strip(window["id"])))
    return framed


def keyboard_window() -> axidev_osk.Map:
    return axidev_osk.window(
        id=KEYBOARD,
        title="axidev OSK",
        opacity=windows.ghost_opacity(KEYBOARD, _setting("opacity")),
        input_blocked=windows.ghost_blocked(KEYBOARD),
        show_on_start=True,
        default_close=False,
        overlay=OVERLAY,
        chrome={"enabled": True},
        content=axidev_osk.box(
            id="keyboard-surface",
            margins=[10, 10, 10, 10],
            spacing=8,
            children=[
                axidev_osk.grid(
                    id="keyboard-grid",
                    spacing=GRID_GAP_PX,
                    style={"object_name": "keyboard"},
                    children=[_key_node(entry, cell) for entry, cell in zip(LAYOUT, _cells(), strict=True)],
                ),
                axidev_osk.label(
                    id="keyboard-status",
                    text=lambda state: axidev_osk.read(state, "keyboard.status") or "",
                    visible=lambda state: not axidev_osk.read(state, "keyboard.ready"),
                    word_wrap=True,
                    style={"object_name": "statusLabel"},
                ),
            ],
        ),
    )


def _hide(window: str) -> axidev_osk.Callback:
    return lambda ctx, event: [axidev_osk.window.hide(window)]


def _notice(window: str, title: str, message: str | axidev_osk.Binding) -> axidev_osk.Map:
    return prompts.prompt_window(
        window,
        title=title,
        message=message,
        glyph="i",
        buttons=[prompts.prompt_button(f"{window}:ok", "OK", _hide(window), accept=True)],
        opts=PROMPT_OPTS,
    )


def _quit_prompt(hint: str | None) -> axidev_osk.Map:
    return prompts.prompt_window(
        QUIT_PROMPT,
        title="Close axidev-osk?",
        message="Do you want to close axidev-osk? This will stop OSK input.",
        danger=True,
        hint=hint,
        opts=PROMPT_OPTS,
        buttons=[
            prompts.prompt_button(f"{QUIT_PROMPT}:yes", "Yes", lambda ctx, event: [axidev_osk.app.quit()], accept=True),
            prompts.prompt_button(f"{QUIT_PROMPT}:no", "No", _hide(QUIT_PROMPT), accept=False),
        ],
    )


def prompt_windows() -> list[axidev_osk.Map]:
    return [
        _quit_prompt(
            "Tip: if you only want to hide OSK, move your cursor into "
            "the screen corner; the hot-corner sensor will hide it without "
            "shutting the app down."
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
            opts={**PROMPT_OPTS, "minimum_size": [560, 150]},
            buttons=[
                axidev_osk.button(
                    id=f"{PERMISSION_PROMPT}:open_terminal",
                    label="Open In Terminal",
                    on_release=lambda ctx, event: [
                        axidev_osk.window.hide(PERMISSION_PROMPT),
                        axidev_osk.linux.open_permission_setup(),
                    ],
                ),
                axidev_osk.button(
                    id=f"{PERMISSION_PROMPT}:already_configured",
                    label="Already Configured",
                    on_release=lambda ctx, event: [
                        axidev_osk.window.hide(PERMISSION_PROMPT),
                        axidev_osk.window.show(LOGOUT_NOTICE),
                    ],
                ),
                axidev_osk.button(
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
            lambda state: axidev_osk.read(state, "keyboard.permission_setup_text") or "",
        ),
    ]


def _on_close_requested(ctx: Any, event: Any) -> list[axidev_osk.Map]:
    """Closing the keyboard asks first; closing a prompt or notice hides it, like its cancel button."""

    if event["window"] == KEYBOARD:
        return [axidev_osk.window.show(QUIT_PROMPT)]
    return [axidev_osk.window.hide(event["window"])]


def _on_permission_setup_opened(ctx: Any, event: Any) -> list[axidev_osk.Map]:
    return [axidev_osk.window.show(TERMINAL_NOTICE if event["opened"] else NO_TERMINAL_NOTICE)]


SOCIAL_KEYS = [("↑", "Up"), ("↓", "Down"), ("L", "L"), ("K", "K")]


def social_window() -> axidev_osk.Map:
    """A small keyboard for scrolling a feed, opening where the main keyboard was."""

    return axidev_osk.window(
        id=KEYBOARD,
        title="axidev OSK: social",
        opacity=_setting("opacity"),
        show_on_start=True,
        default_close=False,
        overlay=OVERLAY,
        chrome={"enabled": True},
        content=axidev_osk.box(
            id="social-surface",
            margins=[10, 10, 10, 10],
            spacing=8,
            children=[
                axidev_osk.box(
                    id="social-keys",
                    direction="horizontal",
                    spacing=GRID_GAP_PX,
                    children=[
                        keys.key(label, output, {"min_width": KEY_UNIT_PX * 2, "min_height": KEY_UNIT_PX * 2})
                        for label, output in SOCIAL_KEYS
                    ],
                ),
                axidev_osk.label(
                    id="keyboard-status",
                    text=lambda state: axidev_osk.read(state, "keyboard.status") or "",
                    visible=lambda state: not axidev_osk.read(state, "keyboard.ready"),
                    word_wrap=True,
                    style={"object_name": "statusLabel"},
                ),
            ],
        ),
    )


def social_profile() -> axidev_osk.Map:
    return axidev_osk.profile(
        state=std.with_state(),
        theme={"qss": DEFAULT_QSS, "palette": DEFAULT_PALETTE, "font": DEFAULT_FONT},
        windows=_with_settings([social_window(), _quit_prompt(None)]),
        attachments=[
            axidev_osk.pointer_locator(
                id="keyboard-locator",
                window=KEYBOARD,
                radius_percent=30,
                maximum_opacity_percent=60,
                radius_standard_deviations=3,
                **POINTER_LOCATOR,
            ),
        ],
        on=std.with_handlers(
            {
                "window.close_requested": _on_close_requested,
                "app.quit_requested": lambda ctx, event: [axidev_osk.window.show(QUIT_PROMPT)],
                "app.activated": lambda ctx, event: windows.reveal(ctx.state, KEYBOARD),
            }
        ),
    )


def keyboard_profile() -> axidev_osk.Map:
    """The keyboard the app starts with."""

    return axidev_osk.profile(
        state=std.with_state(),
        theme={"qss": DEFAULT_QSS, "palette": DEFAULT_PALETTE, "font": DEFAULT_FONT},
        windows=_with_settings([keyboard_window(), *prompt_windows()]),
        attachments=[
            axidev_osk.dwell(
                id=DWELL,
                window=KEYBOARD,
                **{name: _setting("dwell", name) for name in DWELL_SETTINGS},
            ),
            axidev_osk.pointer_locator(
                id="keyboard-locator",
                window=KEYBOARD,
                radius_percent=30,
                maximum_opacity_percent=60,
                radius_standard_deviations=3,
                **POINTER_LOCATOR,
            ),
            axidev_osk.hot_corners(
                id="hot-corners",
                corners=["top_left", "top_right", "bottom_left", "bottom_right"],
                **HOT_CORNER_INDICATOR,
            ),
            axidev_osk.secure_input_panel(id="lock-screen-panel", window=KEYBOARD),
        ],
        on=std.with_handlers(
            {
                "hot_corner.triggered": lambda ctx, event: windows.corner_toggle(ctx.state, KEYBOARD),
                "window.close_requested": _on_close_requested,
                "app.quit_requested": lambda ctx, event: [axidev_osk.window.show(QUIT_PROMPT)],
                "app.activated": lambda ctx, event: windows.reveal(ctx.state, KEYBOARD),
                "keyboard.permission_required": lambda ctx, event: [axidev_osk.window.show(PERMISSION_PROMPT)],
                "linux.permission_setup_opened": _on_permission_setup_opened,
            }
        ),
    )


PROFILES: list[tuple[str, str, Callable[[], axidev_osk.Map]]] = [
    ("default", "Default", keyboard_profile),
    ("social", "Social", social_profile),
]
"""Every bundled profile: its name, its caption in the profile menu, and how it is built."""


def build_default_config() -> axidev_osk.Map:
    """Return the bundled root config: the keyboard the app starts with, and the social profile."""

    return axidev_osk.config(
        active_profile="default",
        state=SHARED_STATE,
        profiles={name: build() for name, _caption, build in PROFILES},
    )
