"""A wheel keyboard: board positions reached by picking slices of an ellipse.

The wheel is an ``axidev_osk.canvas`` that reports its size; every slice is a button
whose ``shape`` binding draws its wedge of the ellipse filling that size, so
the wheel stretches with its window. A map is a list with one item per slice,
slice 0 on top and numbered clockwise. An item is a board position (``std.board``), which sends that
position's key from the active layout, a nested list, which opens as a menu
of its own, or ``None`` for an empty slice. Picking a key returns to the top
unless the wheel is set to stay in its menu.

The center is a ring of four segments: Back goes up one menu, Stay latches
the wheel to keep its menu open after a key, Top goes back to the top menu,
and Release lets go of every latched modifier.

Library state lives under ``std``:

- ``std.wheels.<wheel id>``: the menu path the wheel has open, a list of
  slice numbers.
- ``std.wheel_stays.<wheel id>``: whether picking a key keeps that menu open.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ... import axidev_osk
from . import keys
from .styles import lit, merge_style

SLICES = 10

STATE = {
    "wheels": axidev_osk.var(axidev_osk.map_of(axidev_osk.list_of("integer"))),
    "wheel_stays": axidev_osk.var(axidev_osk.map_of("boolean")),
}
"""The library's wheel variables, merged under ``std`` by ``std.with_state``."""

Tree = list[Any]
Corners = list[list[float]]

ARC_CORNERS = 24
"""Corners along each outer arc; inner arcs and the center take fewer or more in proportion."""

CENTER = ("back", "stay", "top", "release")
"""The center's segments, clockwise from the top."""


def _row_order(slices: int) -> list[int]:
    """Slices clockwise from the one on the left, so a row of keys reads left to right."""

    left = slices * 3 // 4
    return [(left + step) % slices for step in range(slices)]


def menu(items: Mapping[int, Any], slices: int = SLICES) -> Tree:
    """A menu of ``slices`` slices with ``items`` by slice number; other slices stay empty."""

    return [items.get(index) for index in range(slices)]


def row(*positions: str, slices: int = SLICES) -> Tree:
    """A menu holding a row of keys left to right, clockwise from the slice on the left."""

    return menu(dict(zip(_row_order(slices), positions)), slices)


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
    center: Mapping[str, Mapping[str, Any]] | None = None,
    slice_opts: Mapping[str, Any] | None = None,
    key_opts: Mapping[str, Any] | None = None,
) -> axidev_osk.Map:
    """An ``axidev_osk.canvas`` whose slices walk ``tree``; ``opts`` overrides any canvas field.

    ``layouts`` and the ``layout`` binding give each position its entry, as
    for ``keys.at``. A key slice behaves exactly like that key's button
    (``keys.behavior``): pressing sends it down and holding repeats it, and a
    modifier latches until it is picked again. Releasing a key slice returns
    to the top unless Stay is on; releasing a menu slice opens it.

    The center's radii are ``inner`` times the wheel's, and ``spacing`` pixels
    separate every part. Until the canvas first reports its size, the shapes
    fit its minimum size.

    ``center`` maps a segment name of ``CENTER`` to fields that override that
    segment's button, such as its ``label``; ``slice_opts`` overrides fields
    of every slice's button; and ``key_opts`` is the ``opts`` every key's
    behavior is built with, such as a modifier's ``mode`` (``keys.behavior``).
    A ``style`` in ``center`` or ``slice_opts`` adds to the wheel's own
    (``styles.merge_style``).

    Raises ``ValueError`` when a menu of ``tree`` has another number of
    slices than its top level, or an item that is not a position, a menu, or
    ``None``; when ``center`` names no segment of ``CENTER``; or when
    ``opts`` turns ``report_geometry`` off, since the wheel fits its shapes
    to the size the canvas reports.
    """

    path_var = ["std", "wheels", wheel_id]
    stay_var = ["std", "wheel_stays", wheel_id]
    defaults = {"id": wheel_id, "report_geometry": True}
    fields = axidev_osk.merge(defaults, opts)
    if not fields["report_geometry"]:
        raise ValueError(f"wheel {wheel_id!r} needs report_geometry: its shapes follow the canvas's reported size")
    size_var = ["nodes", fields["id"], "size"]
    slices = len(tree)
    _check_tree(tree, slices, [])

    def ellipse(state: Any) -> tuple[float, float]:
        """The wheel's radii, from its reported size or its minimum size before the first report."""

        size = axidev_osk.read(state, size_var)
        if size is not None:
            return max(size["width"], 1) / 2, max(size["height"], 1) / 2

        def minimum(name: str) -> float:
            found = fields.get(name, 0)
            pixels: Any = found(state) if callable(found) else found
            return max(pixels, 1) / 2

        return minimum("min_width"), minimum("min_height")

    def path(state: Any) -> list[int]:
        return list(axidev_osk.read(state, path_var) or [])

    def stays(state: Any) -> bool:
        return bool(axidev_osk.read(state, stay_var))

    def item(state: Any, index: int) -> Any:
        node: Any = tree
        for step in [*path(state), index]:
            node = node[step] if isinstance(node, list) else None
        return node

    value, run = keys.on_layout(_positions(tree), layouts, layout, key_opts)

    def slice_button(index: int) -> axidev_osk.Map:
        def field(name: str, default: Any) -> axidev_osk.Binding:
            def bound(state: Any) -> Any:
                found = item(state, index)
                if isinstance(found, list):
                    # A menu shows every key inside it, spread over its wedge.
                    return [value(state, position, "label", "") for position in _positions(found)] if name == "label" else default
                return value(state, found, name, default) if found is not None else default

            return bound

        def kind(state: Any) -> dict[str, str]:
            found = item(state, index)
            return {"wheelItem": "key" if isinstance(found, str) else "menu" if isinstance(found, list) else "empty"}

        def on_press(ctx: Any, event: Any) -> list[axidev_osk.Map]:
            found = item(ctx.state, index)
            return run(ctx, event, found, "on_press") if isinstance(found, str) else []

        def on_release(ctx: Any, event: Any) -> list[axidev_osk.Map]:
            found = item(ctx.state, index)
            if isinstance(found, list):
                return [axidev_osk.state.set(path_var, [*path(ctx.state), index])]
            if isinstance(found, str):
                sent = run(ctx, event, found, "on_release")
                return sent if stays(ctx.state) else [*sent, axidev_osk.state.set(path_var, None)]
            return []

        lit_properties = lit(field("active", False), field("latched", False))["properties"]
        style = {"properties": lambda state: {**lit_properties(state), **kind(state)}}
        defaults = {
            "id": f"{wheel_id}:slice:{index}",
            "shape": lambda state: wedge(*ellipse(state), 1.0, inner, spacing, index, slices),
            "anchor": lambda state: middle(*ellipse(state), 1.0, inner, index, slices),
            "label": field("label", ""),
            "on_press": on_press,
            "on_release": on_release,
        }
        return _button(defaults, style, slice_opts)

    def go_up(ctx: Any, event: Any) -> list[axidev_osk.Map]:
        del event
        return [axidev_osk.state.set(path_var, path(ctx.state)[:-1] or None)]

    def toggle_stay(ctx: Any, event: Any) -> list[axidev_osk.Map]:
        del event
        return [axidev_osk.state.set(stay_var, not stays(ctx.state))]

    def in_menu(state: Any) -> bool:
        return bool(path(state))

    segments: dict[str, dict[str, Any]] = {
        "back": {"label": "Back", "enabled": in_menu, "on_release": go_up},
        "stay": {"label": "Stay", "latched": stays, "on_release": toggle_stay},
        "top": {
            "label": "Top",
            "enabled": in_menu,
            "on_release": lambda ctx, event: [axidev_osk.state.set(path_var, None)],
        },
        "release": {
            "label": "Release",
            "enabled": keys.any_modifier_latched,
            "on_release": lambda ctx, event: keys.release_modifiers(ctx.state),
        },
    }
    unknown = sorted(set(center or {}) - set(CENTER))
    if unknown:
        raise ValueError(f"wheel center has no segment {', '.join(unknown)}; its segments are {', '.join(CENTER)}")

    def center_button(index: int, name: str) -> axidev_osk.Map:
        segment = dict(segments[name])
        lit_properties = lit(latched=segment.pop("latched", False))["properties"]

        def properties(state: Any) -> dict[str, Any]:
            return {**lit_properties(state), "wheelItem": "center", "wheelCenter": name}

        defaults = {
            **segment,
            "id": f"{wheel_id}:center:{name}",
            "shape": lambda state: wedge(*ellipse(state), inner, 0.0, spacing, index, len(CENTER)),
            "anchor": lambda state: middle(*ellipse(state), inner, 0.0, index, len(CENTER)),
        }
        return _button(defaults, {"properties": properties}, (center or {}).get(name))

    children = [
        *(slice_button(index) for index in range(slices)),
        *(center_button(index, name) for index, name in enumerate(CENTER)),
    ]
    return axidev_osk.canvas(**axidev_osk.merge(fields, {"children": children}))


def _button(defaults: Mapping[str, Any], style: axidev_osk.Map, opts: Mapping[str, Any] | None) -> axidev_osk.Map:
    """A button from ``defaults`` with ``opts`` merged last and its ``style`` added to ``style``."""

    extra = dict(opts or {})
    merged_style = merge_style(style, extra.pop("style", None))
    return axidev_osk.button(**axidev_osk.merge({**defaults, "style": merged_style}, extra))


def wedge(radius_x: float, radius_y: float, outer: float, inner: float, spacing: float, index: int, slices: int) -> Corners:
    """Slice ``index`` of ``slices`` of the ring between ``inner`` and ``outer`` times the ellipse with radii ``radius_x`` and ``radius_y``.

    Slice 0 is on top and they are numbered clockwise; the corners are canvas
    pixels. Each side sits ``spacing / 2`` pixels inside the line between the
    slice and its neighbour, so neighbours stay ``spacing`` apart. A ring
    inside another (``outer`` below 1) stays ``spacing / 2`` pixels inside it,
    and one reaching the middle (``inner`` of 0) keeps a hole just large
    enough for its sides to meet its inner arc.
    """

    gap = spacing / 2
    mid_angle = index * 2 * math.pi / slices
    half = math.pi / slices
    rim_gap = gap if outer < 1 else 0.0
    # Kept above zero, since a rim is divided by; only a wheel narrower than its gaps comes near.
    rim = (max(radius_x * outer - rim_gap, 0.01), max(radius_y * outer - rim_gap, 0.01))
    # Two sides ``gap`` inside their lines cross ``gap / sin(half)`` from the middle.
    least = gap / math.sin(half) + 1 if half < math.pi / 2 else gap + 1
    hole = (max(radius_x * inner + gap, least), max(radius_y * inner + gap, least))
    # A wheel only a few pixels across leaves no room for the gaps; the hole then takes half the rim, so the slice stays whole.
    hole = (min(hole[0], rim[0] / 2), min(hole[1], rim[1] / 2))
    sides = [_side(radius_x, radius_y, mid_angle, mid_angle + turn, gap) for turn in (-half, half)]
    reach = ARC_CORNERS * SLICES / slices
    corners = _arc(rim, _meet(rim, *sides[0]), _meet(rim, *sides[1]), max(2, round(reach * outer)))
    corners += _arc(hole, _meet(hole, *sides[1]), _meet(hole, *sides[0]), max(2, round(reach * inner)), backward=True)
    return [[radius_x + x, radius_y + y] for x, y in corners]


def middle(radius_x: float, radius_y: float, outer: float, inner: float, index: int, slices: int) -> list[float]:
    """The point halfway across the ring between ``inner`` and ``outer`` along slice ``index``'s middle."""

    turn = index * 2 * math.pi / slices
    reach = (outer + inner) / 2
    return [radius_x + radius_x * reach * math.sin(turn), radius_y - radius_y * reach * math.cos(turn)]


def _side(radius_x: float, radius_y: float, mid_angle: float, edge: float, gap: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """A slice side: the line from the center toward ``edge`` on the ellipse, moved ``gap`` toward ``mid_angle``.

    Returns a point on the line and its direction, both relative to the center.
    Angles run clockwise from the top, and y grows downward as on screen.
    """

    along_x, along_y = radius_x * math.sin(edge), -radius_y * math.cos(edge)
    length = math.hypot(along_x, along_y)
    along_x, along_y = along_x / length, along_y / length
    normal_x, normal_y = -along_y, along_x
    if normal_x * math.sin(mid_angle) * radius_x - normal_y * math.cos(mid_angle) * radius_y < 0:
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


def _check_tree(tree: Tree, slices: int, path: list[int]) -> None:
    """Reject a menu with another slice count than the top level, or an item no slice can show."""

    where = f"wheel menu {path}" if path else "wheel tree"
    if len(tree) != slices:
        raise ValueError(f"{where} has {len(tree)} slices; every menu needs {slices}, like the top level")
    for index, node in enumerate(tree):
        if isinstance(node, list):
            _check_tree(node, slices, [*path, index])
        elif node is not None and not isinstance(node, str):
            raise ValueError(f"{where} slice {index} must be a position, a menu, or None, not {type(node).__name__}")


def _positions(tree: Tree) -> list[str]:
    """Every position under a menu, in the left-to-right order ``row`` places them."""

    found: list[str] = []
    for node in (tree[index] for index in _row_order(len(tree))):
        if isinstance(node, str):
            found.append(node)
        elif isinstance(node, list):
            found.extend(_positions(node))
    return found

