"""A wheel keyboard: board positions reached by picking slices of an ``axidev_osk.wheel``.

A map is a list with one item per slice, slice 0 on top and numbered
clockwise. An item is a board position (``std.board``), which sends that
position's key from the active layout, a nested list, which opens as a menu
of its own, or ``None`` for an empty slice. Picking a key returns to the top.
The center button goes back to the top from any menu.

The menu path a wheel has open lives in ``std.wheels.<wheel id>``, a list of
slice numbers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ... import axidev_osk
from . import keys

SLICES = 6
_ROW_ORDER = (4, 5, 0, 1, 2, 3)

STATE = {"wheels": axidev_osk.var(axidev_osk.map_of(axidev_osk.list_of("integer")))}
"""The library's wheel variables, merged under ``std`` by ``std.with_state``."""

Tree = list[Any]


def menu(items: Mapping[int, Any]) -> Tree:
    """A menu with ``items`` by slice number; other slices stay empty."""

    return [items.get(index) for index in range(SLICES)]


def row(*positions: str) -> Tree:
    """A menu holding a row of keys left to right, clockwise from the lower left (slice 4)."""

    return menu(dict(zip(_ROW_ORDER, positions)))


def column(upper: str, lower: str) -> Tree:
    """A menu holding an upper and a lower key: up (slice 0) and down (slice 3)."""

    return menu({0: upper, 3: lower})


TKL = menu(
    {
        # Up: the number row, with the function row above it one menu deeper.
        0: menu(
            {
                0: menu(
                    {
                        4: row("ESC", "CAPS", "MENU"),
                        5: row("FK01", "FK02", "FK03"),
                        0: row("FK04", "FK05", "FK06"),
                        1: row("FK07", "FK08", "FK09"),
                        2: row("FK10", "FK11", "FK12"),
                        3: row("PRSC", "SCLK", "PAUS"),
                    }
                ),
                4: row("TLDE", "AE01", "AE02", "AE03"),
                5: row("AE04", "AE05", "AE06", "AE07"),
                1: row("AE08", "AE09", "AE10", "AE11", "AE12"),
                2: row("AD11", "AD12", "AC10", "AC11", "LSGT"),
                3: row("AB08", "AB09", "AB10"),
            }
        ),
        # Upper left: the left letters, one column of the board per slice.
        5: menu(
            {
                4: "TAB",
                5: column("AD01", "AC01"),
                0: column("AD02", "AC02"),
                1: column("AD03", "AC03"),
                2: column("AD04", "AC04"),
                3: column("AD05", "AC05"),
            }
        ),
        # Upper right: the right letters and Backspace.
        1: menu(
            {
                4: column("AD06", "AC06"),
                5: column("AD07", "AC07"),
                0: column("AD08", "AC08"),
                1: column("AD09", "AC09"),
                2: "AD10",
                3: "BKSP",
            }
        ),
        # Lower left: the bottom letter row, Enter, and Space underneath.
        4: menu(
            {
                4: row("AB01", "AB02"),
                5: row("AB03", "AB04"),
                0: row("AB05", "AB06"),
                1: "AB07",
                2: "RTRN",
                3: "SPCE",
            }
        ),
        # Lower right: arrows point their own way; the two rows of the block above them.
        2: menu(
            {
                0: "UP",
                2: "RGHT",
                3: "DOWN",
                4: "LEFT",
                5: row("INS", "HOME", "PGUP"),
                1: row("DELE", "END", "PGDN"),
            }
        ),
        # Down: the modifiers, left ones on the left and right ones on the right.
        3: menu(
            {
                5: "LFSH",
                4: "LCTL",
                3: "LWIN",
                0: "LALT",
                1: "RTSH",
                2: row("RALT", "RWIN", "RCTL"),
            }
        ),
    }
)
"""The bundled map of the ``std.board.TKL`` positions on a 6-slice wheel."""


def wheel(
    wheel_id: str,
    tree: Tree,
    layouts: Mapping[str, Mapping[str, Mapping[str, Any]]],
    layout: axidev_osk.Binding,
    opts: Mapping[str, Any] | None = None,
) -> axidev_osk.Map:
    """An ``axidev_osk.wheel`` whose slices walk ``tree``; ``opts`` overrides any wheel field.

    ``layouts`` and the ``layout`` binding give each position its entry, as
    for ``keys.at``. A modifier waits for the next key as a one-shot modifier.
    """

    path_var = ["std", "wheels", wheel_id]

    def path(state: Any) -> list[int]:
        return list(axidev_osk.read(state, path_var) or [])

    def item(state: Any, index: int) -> Any:
        node: Any = tree
        for step in [*path(state), index]:
            node = node[step] if isinstance(node, list) else None
        return node

    def entry(state: Any, position: str) -> Mapping[str, Any]:
        return layouts[layout(state)][position]

    def slice_button(index: int) -> axidev_osk.Map:
        def label(state: Any) -> str:
            found = item(state, index)
            if isinstance(found, str):
                return keys.legend(state, entry(state, found))
            if isinstance(found, list):
                return _preview([keys.legend(state, entry(state, position)) for position in _positions(found)])
            return ""

        def latched(state: Any) -> bool:
            found = item(state, index)
            return isinstance(found, str) and keys.waiting(state, entry(state, found))

        def kind(state: Any) -> dict[str, str]:
            found = item(state, index)
            return {"wheelItem": "key" if isinstance(found, str) else "menu" if isinstance(found, list) else "empty"}

        def pick(ctx: Any, event: Any) -> list[axidev_osk.Map]:
            del event
            found = item(ctx.state, index)
            if isinstance(found, list):
                return [axidev_osk.state.set(path_var, [*path(ctx.state), index])]
            if isinstance(found, str):
                return [*keys.tap(ctx.state, entry(ctx.state, found)), axidev_osk.state.set(path_var, None)]
            return []

        return axidev_osk.button(
            id=f"{wheel_id}:slice:{index}",
            slice=index,
            label=label,
            latched=latched,
            on_release=pick,
            style={"properties": kind},
        )

    center = axidev_osk.button(
        id=f"{wheel_id}:center",
        center=True,
        label=lambda state: "×" if path(state) else "",
        on_release=lambda ctx, event: [axidev_osk.state.set(path_var, None)],
        style={"properties": {"wheelItem": "center"}},
    )
    defaults = {
        "id": wheel_id,
        "slices": len(tree),
        "children": [*(slice_button(index) for index in range(len(tree))), center],
    }
    return axidev_osk.wheel(**axidev_osk.merge(defaults, opts))


def _positions(tree: Tree) -> list[str]:
    """Every position under a menu, in the left-to-right order ``row`` places them."""

    found: list[str] = []
    for node in (tree[index] for index in [*_ROW_ORDER, *range(SLICES, len(tree))] if index < len(tree)):
        if isinstance(node, str):
            found.append(node)
        elif isinstance(node, list):
            found.extend(_positions(node))
    return found


def _preview(legends: list[str]) -> str:
    """A menu's legend: up to 6 of its keys, 3 per line."""

    shown = legends if len(legends) <= 6 else [*legends[:5], "…"]
    return "\n".join(" ".join(shown[start : start + 3]) for start in range(0, len(shown), 3))
