"""Layouts: what each physical position (``std.board``) is.

A layout is a plain table from position to entry. An entry is data, not a
widget: ``std.keys`` turns it into a key button, and ``std.wheel`` into a wheel
slice. Every entry holds its ``kind``, its ``label``, and the ``output`` it
sends, the literal key name the keyboard backend types whatever the system
layout is. Letters and symbols also hold the ``shifted`` legend shown while
Shift is active.

A profile keeps the active layout's name in a variable of its own choosing
and hands a binding that reads it to ``keys.at`` and ``wheel.wheel``, so
switching layouts is one ``state.set``.
"""

from __future__ import annotations

from typing import Any

Entry = dict[str, Any]


def key(label: str, output: str) -> Entry:
    """A key that sends ``output`` and always shows ``label``."""

    return {"kind": "key", "label": label, "output": output}


def letter(char: str) -> Entry:
    """A letter whose legend follows Shift and Caps Lock."""

    return {"kind": "letter", "label": char.lower(), "shifted": char.upper(), "output": char.upper()}


def shifted(label: str, shifted_label: str, output: str) -> Entry:
    """A symbol whose legend follows Shift only."""

    return {"kind": "shifted", "label": label, "shifted": shifted_label, "output": output}


def modifier(label: str, output: str) -> Entry:
    return {"kind": "modifier", "label": label, "output": output}


def lock(label: str, output: str) -> Entry:
    """A lock key such as Caps Lock, lit from the system's lock state."""

    return {"kind": "lock", "label": label, "output": output}


US: dict[str, Entry] = {
    "ESC": key("Esc", "Escape"),
    **{f"FK{number:02d}": key(f"F{number}", f"F{number}") for number in range(1, 13)},
    "PRSC": key("PrtSc", "PrintScreen"),
    "SCLK": key("ScrLk", "ScrollLock"),
    "PAUS": key("Pause", "Pause"),
    "TLDE": shifted("`", "~", "`"),
    **{f"AE{index:02d}": shifted(digit, symbol, digit) for index, (digit, symbol) in enumerate(
        zip("1234567890", "!@#$%^&*()"), start=1)},
    "AE11": shifted("-", "_", "-"),
    "AE12": shifted("=", "+", "="),
    "BKSP": key("Backspace", "Backspace"),
    "INS": key("Ins", "Insert"),
    "HOME": key("Home", "Home"),
    "PGUP": key("PgUp", "PageUp"),
    "TAB": key("Tab", "Tab"),
    **{f"AD{index:02d}": letter(char) for index, char in enumerate("qwertyuiop", start=1)},
    "AD11": shifted("[", "{", "["),
    "AD12": shifted("]", "}", "]"),
    "DELE": key("Del", "Delete"),
    "END": key("End", "End"),
    "PGDN": key("PgDn", "PageDown"),
    "CAPS": lock("Caps", "CapsLock"),
    **{f"AC{index:02d}": letter(char) for index, char in enumerate("asdfghjkl", start=1)},
    "AC10": shifted(";", ":", ";"),
    "AC11": shifted("'", '"', "'"),
    "RTRN": key("Enter", "Enter"),
    "LFSH": modifier("Shift", "ShiftLeft"),
    "LSGT": shifted("\\", "|", "\\"),
    **{f"AB{index:02d}": letter(char) for index, char in enumerate("zxcvbnm", start=1)},
    "AB08": shifted(",", "<", ","),
    "AB09": shifted(".", ">", "."),
    "AB10": shifted("/", "?", "/"),
    "RTSH": modifier("Shift", "ShiftRight"),
    "UP": key("↑", "Up"),
    "LCTL": modifier("Ctrl", "CtrlLeft"),
    "LWIN": modifier("Super", "SuperLeft"),
    "LALT": modifier("Alt", "AltLeft"),
    "SPCE": key("Space", "Space"),
    "RALT": modifier("AltGr", "AltRight"),
    "RWIN": modifier("Super", "SuperRight"),
    "MENU": key("Menu", "Menu"),
    "RCTL": modifier("Ctrl", "CtrlRight"),
    "LEFT": key("←", "Left"),
    "DOWN": key("↓", "Down"),
    "RGHT": key("→", "Right"),
}
"""The bundled US layout on the ``std.board.TKL`` positions."""

DVORAK: dict[str, Entry] = {
    **US,
    "AE11": shifted("[", "{", "["),
    "AE12": shifted("]", "}", "]"),
    "AD01": shifted("'", '"', "'"),
    "AD02": shifted(",", "<", ","),
    "AD03": shifted(".", ">", "."),
    **{f"AD{index:02d}": letter(char) for index, char in enumerate("pyfgcrl", start=4)},
    "AD11": shifted("/", "?", "/"),
    "AD12": shifted("=", "+", "="),
    **{f"AC{index:02d}": letter(char) for index, char in enumerate("aoeuidhtns", start=1)},
    "AC11": shifted("-", "_", "-"),
    "AB01": shifted(";", ":", ";"),
    **{f"AB{index:02d}": letter(char) for index, char in enumerate("qjkxbmwvz", start=2)},
}
"""The US Dvorak layout: the US table with the letters and the symbols around them moved."""

LAYOUTS: dict[str, dict[str, Entry]] = {"us": US, "dvorak": DVORAK}
"""Every bundled layout by name."""
