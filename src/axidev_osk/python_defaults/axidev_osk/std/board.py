"""Physical key positions, independent of what any layout puts on them.

A position is named the way XKB names keyboard positions: ``AE01`` is the
second key of the number row, ``AD01`` the first letter key of the row above
the home row, ``AC01`` the first home-row letter, ``AB01`` the first letter of
the bottom letter row, and named keys such as ``ESC``, ``LFSH`` or ``SPCE``
for the rest. A layout (``std.layouts``) says what each position is; a
profile places positions on screen however it likes.

``TKL`` is the 80% board the bundled keyboard draws: one entry per position
as (position, row, column in quarter key units, width in key units).
"""

from __future__ import annotations

TKL: list[tuple[str, int, int, float]] = [
    ("ESC", 0, 0, 1.0),
    *[(f"FK{number:02d}", 0, column, 1.0) for number, column in enumerate(
        (8, 12, 16, 20, 28, 32, 36, 40, 48, 52, 56, 60), start=1)],
    ("PRSC", 0, 68, 1.0),
    ("SCLK", 0, 72, 1.0),
    ("PAUS", 0, 76, 1.0),
    ("TLDE", 1, 0, 1.0),
    *[(f"AE{index:02d}", 1, 4 * index, 1.0) for index in range(1, 13)],
    ("BKSP", 1, 52, 2.0),
    ("INS", 1, 68, 1.0),
    ("HOME", 1, 72, 1.0),
    ("PGUP", 1, 76, 1.0),
    ("TAB", 2, 0, 1.5),
    *[(f"AD{index:02d}", 2, 2 + 4 * index, 1.0) for index in range(1, 13)],
    ("DELE", 2, 68, 1.0),
    ("END", 2, 72, 1.0),
    ("PGDN", 2, 76, 1.0),
    ("CAPS", 3, 0, 1.75),
    *[(f"AC{index:02d}", 3, 3 + 4 * index, 1.0) for index in range(1, 12)],
    ("RTRN", 3, 51, 2.25),
    ("LFSH", 4, 0, 1.25),
    ("LSGT", 4, 5, 1.0),
    *[(f"AB{index:02d}", 4, 5 + 4 * index, 1.0) for index in range(1, 11)],
    ("RTSH", 4, 49, 2.75),
    ("UP", 4, 72, 1.0),
    ("LCTL", 5, 0, 1.25),
    ("LWIN", 5, 5, 1.25),
    ("LALT", 5, 10, 1.25),
    ("SPCE", 5, 15, 6.25),
    ("RALT", 5, 40, 1.25),
    ("RWIN", 5, 45, 1.25),
    ("MENU", 5, 50, 1.25),
    ("RCTL", 5, 55, 1.25),
    ("LEFT", 5, 68, 1.0),
    ("DOWN", 5, 72, 1.0),
    ("RGHT", 5, 76, 1.0),
]
