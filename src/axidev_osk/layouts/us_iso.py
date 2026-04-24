from __future__ import annotations

from ..models import KeyDisplay, KeySpec


UNIT = 4
MAIN_BLOCK_WIDTH = 60
NAV_START = 64


def key(
    label: str,
    *,
    row: int,
    column: int,
    width: float = 1.0,
    height: int = 1,
    is_spacer: bool = False,
    secondary_label: str | None = None,
    key_id: str | None = None,
    latchable: bool = False,
    io_key: str | None = None,
    latched_io_key: str | None = None,
    holds_when_latched: bool = False,
    honors_latched_modifiers: bool = True,
    repeats: bool = True,
    display_variants: tuple[KeyDisplay, ...] = (),
) -> KeySpec:
    return KeySpec(
        label=label,
        row=row,
        column=column,
        width=width,
        height=height,
        is_spacer=is_spacer,
        secondary_label=secondary_label,
        key_id=key_id,
        latchable=latchable,
        io_key=io_key,
        latched_io_key=latched_io_key,
        holds_when_latched=holds_when_latched,
        honors_latched_modifiers=honors_latched_modifiers,
        repeats=repeats,
        display_variants=display_variants,
    )


def held_modifier(
    label: str,
    *,
    row: int,
    column: int,
    width: float,
    key_id: str,
    io_key: str,
    latched_io_key: str | None = None,
) -> KeySpec:
    return key(
        label,
        row=row,
        column=column,
        width=width,
        key_id=key_id,
        latchable=True,
        io_key=io_key,
        latched_io_key=latched_io_key or io_key,
        holds_when_latched=True,
        honors_latched_modifiers=False,
        repeats=False,
    )


def spacer(*, row: int, column: int, width: float = 1.0, height: int = 1) -> KeySpec:
    return key("", row=row, column=column, width=width, height=height, is_spacer=True)


def u(value: int) -> int:
    return value * UNIT


def shifted_key(
    label: str,
    shifted_label: str,
    *,
    row: int,
    column: int,
    width: float = 1.0,
    height: int = 1,
    key_id: str | None = None,
    latchable: bool = False,
    io_key: str | None = None,
    latched_io_key: str | None = None,
    holds_when_latched: bool = False,
    honors_latched_modifiers: bool = True,
    repeats: bool = True,
) -> KeySpec:
    return key(
        label,
        row=row,
        column=column,
        width=width,
        height=height,
        key_id=key_id,
        latchable=latchable,
        io_key=io_key,
        latched_io_key=latched_io_key,
        holds_when_latched=holds_when_latched,
        honors_latched_modifiers=honors_latched_modifiers,
        repeats=repeats,
        display_variants=(
            KeyDisplay(
                label=shifted_label,
                requires_modifiers=frozenset({"shift"}),
            ),
        ),
    )


def letter_key(
    label: str,
    *,
    row: int,
    column: int,
    width: float = 1.0,
    height: int = 1,
    repeats: bool = True,
) -> KeySpec:
    lower_label = label.lower()
    upper_label = label.upper()
    return key(
        lower_label,
        row=row,
        column=column,
        width=width,
        height=height,
        io_key=upper_label,
        repeats=repeats,
        display_variants=(
            KeyDisplay(
                label=upper_label,
                requires_modifiers=frozenset({"shift"}),
                excludes_modifiers=frozenset({"caps"}),
            ),
            KeyDisplay(
                label=upper_label,
                requires_modifiers=frozenset({"caps"}),
                excludes_modifiers=frozenset({"shift"}),
            ),
        ),
    )


def build_us_iso_layout() -> list[KeySpec]:
    return [
        key("Esc", row=0, column=u(0), io_key="Escape"),
        key("F1", row=0, column=u(2)),
        key("F2", row=0, column=u(3)),
        key("F3", row=0, column=u(4)),
        key("F4", row=0, column=u(5)),
        key("F5", row=0, column=u(7)),
        key("F6", row=0, column=u(8)),
        key("F7", row=0, column=u(9)),
        key("F8", row=0, column=u(10)),
        key("F9", row=0, column=u(12)),
        key("F10", row=0, column=u(13)),
        key("F11", row=0, column=u(14)),
        key("F12", row=0, column=u(15)),
        key("PrtSc", row=0, column=NAV_START, io_key="PrintScreen"),
        key("ScrLk", row=0, column=NAV_START + u(1), io_key="ScrollLock"),
        key("Pause", row=0, column=NAV_START + u(2), io_key="Pause"),
        shifted_key("`", "~", row=1, column=u(0)),
        shifted_key("1", "!", row=1, column=u(1)),
        shifted_key("2", "@", row=1, column=u(2)),
        shifted_key("3", "#", row=1, column=u(3)),
        shifted_key("4", "$", row=1, column=u(4)),
        shifted_key("5", "%", row=1, column=u(5)),
        shifted_key("6", "^", row=1, column=u(6)),
        shifted_key("7", "&", row=1, column=u(7)),
        shifted_key("8", "*", row=1, column=u(8)),
        shifted_key("9", "(", row=1, column=u(9)),
        shifted_key("0", ")", row=1, column=u(10)),
        shifted_key("-", "_", row=1, column=u(11)),
        shifted_key("=", "+", row=1, column=u(12)),
        key("Backspace", row=1, column=u(13), width=2.0, io_key="Backspace"),
        key("Ins", row=1, column=NAV_START, io_key="Insert"),
        key("Home", row=1, column=NAV_START + u(1), io_key="Home"),
        key("PgUp", row=1, column=NAV_START + u(2), io_key="PageUp"),
        key("Tab", row=2, column=u(0), width=1.5, io_key="Tab"),
        letter_key("Q", row=2, column=6),
        letter_key("W", row=2, column=10),
        letter_key("E", row=2, column=14),
        letter_key("R", row=2, column=18),
        letter_key("T", row=2, column=22),
        letter_key("Y", row=2, column=26),
        letter_key("U", row=2, column=30),
        letter_key("I", row=2, column=34),
        letter_key("O", row=2, column=38),
        letter_key("P", row=2, column=42),
        shifted_key("[", "{", row=2, column=46),
        shifted_key("]", "}", row=2, column=50),
        key("Del", row=2, column=NAV_START, io_key="Delete"),
        key("End", row=2, column=NAV_START + u(1), io_key="End"),
        key("PgDn", row=2, column=NAV_START + u(2), io_key="PageDown"),
        key(
            "Caps",
            row=3,
            column=u(0),
            width=1.75,
            key_id="caps",
            latchable=True,
            io_key="CapsLock",
        ),
        letter_key("A", row=3, column=7),
        letter_key("S", row=3, column=11),
        letter_key("D", row=3, column=15),
        letter_key("F", row=3, column=19),
        letter_key("G", row=3, column=23),
        letter_key("H", row=3, column=27),
        letter_key("J", row=3, column=31),
        letter_key("K", row=3, column=35),
        letter_key("L", row=3, column=39),
        shifted_key(";", ":", row=3, column=43),
        shifted_key("'", '"', row=3, column=47),
        key("Enter", row=3, column=51, width=2.25, io_key="Enter"),
        held_modifier(
            "Shift", row=4, column=u(0), width=1.25, key_id="shift", io_key="ShiftLeft"
        ),
        shifted_key("\\", "|", row=4, column=5),
        letter_key("Z", row=4, column=9),
        letter_key("X", row=4, column=13),
        letter_key("C", row=4, column=17),
        letter_key("V", row=4, column=21),
        letter_key("B", row=4, column=25),
        letter_key("N", row=4, column=29),
        letter_key("M", row=4, column=33),
        shifted_key(",", "<", row=4, column=37),
        shifted_key(".", ">", row=4, column=41),
        shifted_key("/", "?", row=4, column=45),
        held_modifier(
            "Shift",
            row=4,
            column=49,
            width=2.75,
            key_id="shift",
            io_key="ShiftRight",
            latched_io_key="ShiftLeft",
        ),
        key("↑", row=4, column=NAV_START + u(1), io_key="Up"),
        held_modifier(
            "Ctrl", row=5, column=u(0), width=1.25, key_id="ctrl", io_key="CtrlLeft"
        ),
        held_modifier(
            "Super", row=5, column=5, width=1.25, key_id="super", io_key="SuperLeft"
        ),
        held_modifier(
            "Alt", row=5, column=10, width=1.25, key_id="alt", io_key="AltLeft"
        ),
        key("Space", row=5, column=15, width=6.25, io_key="Space"),
        held_modifier(
            "AltGr", row=5, column=40, width=1.25, key_id="altgr", io_key="AltRight"
        ),
        held_modifier(
            "Super",
            row=5,
            column=45,
            width=1.25,
            key_id="super",
            io_key="SuperRight",
            latched_io_key="SuperLeft",
        ),
        key("Menu", row=5, column=50, width=1.25, io_key="Menu"),
        held_modifier(
            "Ctrl",
            row=5,
            column=55,
            width=1.25,
            key_id="ctrl",
            io_key="CtrlRight",
            latched_io_key="CtrlLeft",
        ),
        key("←", row=5, column=NAV_START, io_key="Left"),
        key("↓", row=5, column=NAV_START + u(1), io_key="Down"),
        key("→", row=5, column=NAV_START + u(2), io_key="Right"),
    ]
