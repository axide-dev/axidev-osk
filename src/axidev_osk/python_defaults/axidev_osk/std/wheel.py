"""A wheel keyboard: board positions reached by picking slices of an ellipse.

The wheel is an ``axidev_osk.canvas`` that reports its size; every slice is a button
whose ``shape`` binding draws its wedge of the ellipse filling that size, so
the wheel stretches with its window. A map is a list with one item per slice,
slice 0 on top and numbered clockwise. An item is a board position (``std.board``), which sends that
position's key from the active layout, a nested list, which opens as a menu
of its own, or ``None`` for an empty slice. Picking a key returns to the top.
The center button goes back to the top from any menu.

The menu path a wheel has open lives in ``std.wheels.<wheel id>``, a list of
slice numbers.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ... import axidev_osk
from . import keys

SLICES = 10

STATE = {"wheels": axidev_osk.var(axidev_osk.map_of(axidev_osk.list_of("integer")))}
"""The library's wheel variables, merged under ``std`` by ``std.with_state``."""

Tree = list[Any]
Corners = list[list[float]]

ARC_CORNERS = 24
"""Corners along each outer arc; inner arcs and the center take fewer or more in proportion."""


def _row_order(slices: int) -> list[int]:
    """Slices clockwise from the one on the left, so a row of keys reads left to right."""

    left = slices * 3 // 4
    return [(left + step) % slices for step in range(slices)]


def menu(items: Mapping[int, Any]) -> Tree:
    """A menu with ``items`` by slice number; other slices stay empty."""

    return [items.get(index) for index in range(SLICES)]


def row(*positions: str) -> Tree:
    """A menu holding a row of keys left to right, clockwise from the slice on the left."""

    return menu(dict(zip(_row_order(SLICES), positions)))


def column(upper: str, lower: str) -> Tree:
    """A menu holding an upper and a lower key: up (slice 0) and down."""

    return menu({0: upper, SLICES // 2: lower})


TKL = menu(
    {
        # Up: the digits.
        0: row(*(f"AE{index:02d}" for index in range(1, 11))),
        # Upper right: the other symbols, Tab, and Enter.
        1: row("TLDE", "AE11", "AE12", "AD11", "AD12", "LSGT", "AC11", "TAB", "RTRN"),
        # Right: arrows point their own way; Ins, Home, and PgUp run across the top.
        2: menu({0: "UP", 3: "RGHT", 5: "DOWN", 7: "LEFT", 8: "INS", 9: "HOME", 1: "PGUP", 2: "DELE", 6: "END", 4: "PGDN"}),
        # Escape, the function keys in fours, and the rare keys.
        3: menu(
            {
                7: "ESC",
                8: row("FK01", "FK02", "FK03", "FK04"),
                9: row("FK05", "FK06", "FK07", "FK08"),
                0: row("FK09", "FK10", "FK11", "FK12"),
                1: row("PRSC", "SCLK", "PAUS"),
                2: "CAPS",
                3: "MENU",
            }
        ),
        4: "BKSP",
        # Down: Space, like the bar under the board.
        5: "SPCE",
        6: row("LFSH", "LCTL", "LWIN", "LALT", "RALT", "RWIN", "RCTL", "RTSH"),
        # Left, top to bottom: the board's three letter rows.
        7: row(*(f"AB{index:02d}" for index in range(1, 11))),
        8: row(*(f"AC{index:02d}" for index in range(1, 11))),
        9: row(*(f"AD{index:02d}" for index in range(1, 11))),
    }
)
"""The bundled map of the ``std.board.TKL`` positions on a 10-slice wheel."""


def wheel(
    wheel_id: str,
    tree: Tree,
    layouts: Mapping[str, Mapping[str, Mapping[str, Any]]],
    layout: axidev_osk.Binding,
    opts: Mapping[str, Any] | None = None,
    *,
    inner: float = 0.25,
    spacing: float = 0,
) -> axidev_osk.Map:
    """An ``axidev_osk.canvas`` whose slices walk ``tree``; ``opts`` overrides any canvas field.

    ``layouts`` and the ``layout`` binding give each position its entry, as
    for ``keys.at``. A key slice behaves exactly like that key's button
    (``keys.behavior``): pressing sends it down and holding repeats it, and a
    modifier latches until it is picked again. Releasing a key slice returns
    to the top; releasing a menu slice opens it.

    The center's radii are ``inner`` times the wheel's, and ``spacing`` pixels
    separate every part. Until the canvas first reports its size, the shapes
    fit its minimum size.
    """

    path_var = ["std", "wheels", wheel_id]
    size_var = ["nodes", wheel_id, "size"]
    defaults = {"id": wheel_id, "report_size": True}
    fields = axidev_osk.merge(defaults, opts)
    slices = len(tree)

    def ellipse(state: Any) -> tuple[float, float]:
        """The wheel's radii, from its reported size or its minimum size before the first report."""

        size = axidev_osk.read(state, size_var)
        width = size["width"] if size is not None else _value(fields.get("min_width", 0), state)
        height = size["height"] if size is not None else _value(fields.get("min_height", 0), state)
        return max(width, 1) / 2, max(height, 1) / 2

    def path(state: Any) -> list[int]:
        return list(axidev_osk.read(state, path_var) or [])

    def item(state: Any, index: int) -> Any:
        node: Any = tree
        for step in [*path(state), index]:
            node = node[step] if isinstance(node, list) else None
        return node

    behaviors: dict[tuple[str, str], dict[str, Any]] = {}

    def behavior(state: Any, position: str) -> dict[str, Any]:
        """The key behavior the active layout gives ``position``, built once per layout."""

        name = layout(state)
        if (name, position) not in behaviors:
            behaviors[(name, position)] = keys.behavior(layouts[name][position])
        return behaviors[(name, position)]

    def slice_button(index: int) -> axidev_osk.Map:
        def field(name: str, default: Any) -> axidev_osk.Binding:
            def bound(state: Any) -> Any:
                found = item(state, index)
                if isinstance(found, list):
                    return _preview([_value(behavior(state, position)["label"], state) for position in _positions(found)]) if name == "label" else default
                if found is None:
                    return default
                return _value(behavior(state, found).get(name, default), state)

            return bound

        def kind(state: Any) -> dict[str, str]:
            found = item(state, index)
            return {"wheelItem": "key" if isinstance(found, str) else "menu" if isinstance(found, list) else "empty"}

        def on_press(ctx: Any, event: Any) -> list[axidev_osk.Map]:
            found = item(ctx.state, index)
            handler = behavior(ctx.state, found).get("on_press") if isinstance(found, str) else None
            return handler(ctx, event) if handler is not None else []

        def on_release(ctx: Any, event: Any) -> list[axidev_osk.Map]:
            found = item(ctx.state, index)
            if isinstance(found, list):
                return [axidev_osk.state.set(path_var, [*path(ctx.state), index])]
            if isinstance(found, str):
                handler = behavior(ctx.state, found).get("on_release")
                return [*(handler(ctx, event) if handler is not None else []), axidev_osk.state.set(path_var, None)]
            return []

        return axidev_osk.button(
            id=f"{wheel_id}:slice:{index}",
            shape=lambda state: wedge(*ellipse(state), inner, spacing, index, slices),
            anchor=lambda state: middle(*ellipse(state), inner, index, slices),
            label=field("label", ""),
            active=field("active", False),
            latched=field("latched", False),
            on_press=on_press,
            on_release=on_release,
            style={"properties": kind},
        )

    center = axidev_osk.button(
        id=f"{wheel_id}:center",
        shape=lambda state: hub(*ellipse(state), inner, spacing),
        anchor=lambda state: list(ellipse(state)),
        label=lambda state: "×" if path(state) else "",
        on_release=lambda ctx, event: [axidev_osk.state.set(path_var, None)],
        style={"properties": {"wheelItem": "center"}},
    )
    children = [*(slice_button(index) for index in range(slices)), center]
    return axidev_osk.canvas(**axidev_osk.merge(fields, {"children": children}))


def wedge(radius_x: float, radius_y: float, inner: float, spacing: float, index: int, slices: int) -> Corners:
    """Slice ``index`` of ``slices`` of the ellipse with radii ``radius_x`` and ``radius_y``, as canvas corners.

    The slice runs from the center's edge to the wheel's edge, slice 0 on
    top and numbered clockwise; each of its sides sits ``spacing / 2`` pixels
    inside the line between it and its neighbour, so neighbours stay
    ``spacing`` apart.
    """

    gap = spacing / 2
    middle = index * 2 * math.pi / slices
    half = math.pi / slices
    outer = (radius_x, radius_y)
    hole = (radius_x * inner + gap, radius_y * inner + gap)
    sides = [_side(radius_x, radius_y, middle, middle + turn, gap) for turn in (-half, half)]
    corners = _arc(outer, _meet(outer, *sides[0]), _meet(outer, *sides[1]), ARC_CORNERS)
    corners += _arc(hole, _meet(hole, *sides[1]), _meet(hole, *sides[0]), max(2, round(ARC_CORNERS * inner)), backward=True)
    return [[radius_x + x, radius_y + y] for x, y in corners]


def middle(radius_x: float, radius_y: float, inner: float, index: int, slices: int) -> list[float]:
    """The point halfway between the center's edge and the wheel's edge along slice ``index``'s middle."""

    turn = index * 2 * math.pi / slices
    reach = (1 + inner) / 2
    return [radius_x + radius_x * reach * math.sin(turn), radius_y - radius_y * reach * math.cos(turn)]


def hub(radius_x: float, radius_y: float, inner: float, spacing: float) -> Corners:
    """The center of the ellipse with radii ``radius_x`` and ``radius_y``, ``spacing / 2`` pixels inside the slices."""

    gap = spacing / 2
    reach_x, reach_y = max(1.0, radius_x * inner - gap), max(1.0, radius_y * inner - gap)
    steps = ARC_CORNERS * 2
    return [
        [radius_x + reach_x * math.sin(turn), radius_y - reach_y * math.cos(turn)]
        for turn in (step * 2 * math.pi / steps for step in range(steps))
    ]


def _side(radius_x: float, radius_y: float, middle: float, edge: float, gap: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """A slice side: the line from the center toward ``edge`` on the ellipse, moved ``gap`` toward ``middle``.

    Returns a point on the line and its direction, both relative to the center.
    Angles run clockwise from the top, and y grows downward as on screen.
    """

    along_x, along_y = radius_x * math.sin(edge), -radius_y * math.cos(edge)
    length = math.hypot(along_x, along_y)
    along_x, along_y = along_x / length, along_y / length
    normal_x, normal_y = -along_y, along_x
    if normal_x * math.sin(middle) * radius_x - normal_y * math.cos(middle) * radius_y < 0:
        normal_x, normal_y = -normal_x, -normal_y
    return (normal_x * gap, normal_y * gap), (along_x, along_y)


def _meet(radii: tuple[float, float], start: tuple[float, float], along: tuple[float, float]) -> tuple[float, float]:
    """Where the ray from ``start`` along ``along`` leaves the ellipse with ``radii`` around the center."""

    (radius_x, radius_y), (start_x, start_y), (along_x, along_y) = radii, start, along
    a = (along_x / radius_x) ** 2 + (along_y / radius_y) ** 2
    b = 2 * (start_x * along_x / radius_x**2 + start_y * along_y / radius_y**2)
    c = (start_x / radius_x) ** 2 + (start_y / radius_y) ** 2 - 1
    distance = (-b + math.sqrt(max(0.0, b * b - 4 * a * c))) / (2 * a)
    return start_x + along_x * distance, start_y + along_y * distance


def _arc(
    radii: tuple[float, float],
    first: tuple[float, float],
    last: tuple[float, float],
    steps: int,
    *,
    backward: bool = False,
) -> list[tuple[float, float]]:
    """Corners along the ellipse with ``radii`` from ``first`` to ``last``, clockwise or, ``backward``, counterclockwise."""

    radius_x, radius_y = radii

    def turn(point: tuple[float, float]) -> float:
        return math.atan2(point[0] / radius_x, -point[1] / radius_y)

    start, end = turn(first), turn(last)
    if backward:
        start, end = end, start
    while end < start:
        end += 2 * math.pi
    corners = [
        (radius_x * math.sin(start + (end - start) * step / steps), -radius_y * math.cos(start + (end - start) * step / steps))
        for step in range(steps + 1)
    ]
    return corners[::-1] if backward else corners


def _value(found: Any, state: Any) -> Any:
    return found(state) if callable(found) else found


def _positions(tree: Tree) -> list[str]:
    """Every position under a menu, in the left-to-right order ``row`` places them."""

    found: list[str] = []
    for node in (tree[index] for index in _row_order(len(tree))):
        if isinstance(node, str):
            found.append(node)
        elif isinstance(node, list):
            found.extend(_positions(node))
    return found


def _preview(legends: list[str]) -> list[str]:
    """A menu's label: the legend of every key in it, as parts the button spreads over its wedge."""

    return legends
