"""Pointer-locator colors built only from ``axidev_osk`` primitives.

The engine's ``pointer_locator`` attachment glows each button in its
``locator_color``, and in the attachment's ``gap_color`` between buttons.
``colored`` gives a set of buttons the standard pattern: keys alternate warm
and cool hues like a checkerboard, and nearby keys of the same temperature get
different hues, so the glow shows which key the pointer is on.

The pattern follows where the keys really are on screen. ``colored`` turns on
``report_geometry`` for its buttons and binds each one's color to
``std.locator.<node id>``; ``on`` gives the handlers that fill those colors.
Qt places the keys one by one, so each placement only restarts the
``std.locator`` timer, and the colors are computed once when it fires.

Library state lives under ``std.locator``: each colored node's color, by node
ID.
"""

from __future__ import annotations

import colorsys
import statistics
from collections.abc import Mapping, Sequence
from typing import Any

from ... import axidev_osk

PALETTE = {"warm": [330.0, 90.0], "cool": [150.0, 120.0], "nearby_sizes": 2.25}
"""The pattern's defaults, which the ``opts`` of ``on`` and ``palette`` override field by field.

``warm`` and ``cool`` give where each temperature's hues start on the hue
wheel and how far they span, in degrees. Keys closer than ``nearby_sizes``
typical key sizes count as nearby and get different hues.
"""

TIMER = "std.locator"
"""The timer that gathers one layout's geometry reports into one coloring."""

STATE = {"locator": axidev_osk.var(axidev_osk.map_of("string"))}
"""The library's locator variables, merged under ``std`` by ``std.with_state``."""


def colored(nodes: Sequence[Mapping[str, Any]], opts: Mapping[str, Any] | None = None) -> list[axidev_osk.Map]:
    """Return ``nodes`` reporting their geometry, each glowing the color ``on`` gives it.

    ``opts`` fields replace the fields this sets on every node.
    """

    return [
        axidev_osk.merge({**node, "report_geometry": True, "locator_color": _color_of(node["id"])}, opts)
        for node in nodes
    ]


def on(nodes: Sequence[Mapping[str, Any]], opts: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The handlers that color ``nodes`` from their reported geometry; pass them to ``std.with_handlers``.

    ``opts`` overrides fields of ``PALETTE``.
    """

    ids = [node["id"] for node in nodes]
    members = frozenset(ids)

    def on_geometry_changed(ctx: Any, event: Any) -> list[axidev_osk.Map]:
        del ctx
        if event["node"] not in members:
            return []
        return [axidev_osk.timer.start(TIMER, 0)]

    def on_timer_fired(ctx: Any, event: Any) -> list[axidev_osk.Map]:
        if event["id"] != TIMER:
            return []
        placed = []
        rects = []
        for node_id in ids:
            position = axidev_osk.read(ctx.state, ["nodes", node_id, "position"])
            size = axidev_osk.read(ctx.state, ["nodes", node_id, "size"])
            if position is None or size is None or size["width"] <= 0 or size["height"] <= 0:
                continue
            placed.append(node_id)
            rects.append({"x": position["x"], "y": position["y"], "width": size["width"], "height": size["height"]})
        return [axidev_osk.state.set(["std", "locator"], dict(zip(placed, palette(rects, opts), strict=True)))]

    return {"node.geometry_changed": on_geometry_changed, "timer.fired": on_timer_fired}


def palette(rects: Sequence[Mapping[str, Any]], opts: Mapping[str, Any] | None = None) -> list[str]:
    """One ``#RRGGBB`` color for each rectangle (``x``, ``y``, ``width``, ``height``, in whole pixels).

    ``opts`` overrides fields of ``PALETTE``.

    Rectangles alternate between warm and cool hues by row and position in
    their row; within each temperature, nearby rectangles get different hues.
    The same rectangles always get the same colors, in whatever order they come.
    Edges and centers follow whole-pixel rules: a rectangle's last pixel is
    ``x + width - 1``, and its center is rounded down.
    """

    if not rects:
        return []
    options = axidev_osk.merge(PALETTE, opts)
    given = [(int(r["x"]), int(r["y"]), int(r["width"]), int(r["height"])) for r in rects]
    # Colored from the top left, so the colors do not depend on the order the rectangles come in.
    order = sorted(range(len(given)), key=lambda index: (_center(given[index])[1], _center(given[index])[0], index))
    boxes = [given[index] for index in order]
    typical = statistics.median(min(width, height) for _x, _y, width, height in boxes)
    graph = _nearby(boxes, typical * options["nearby_sizes"])
    parities = _checkerboard(boxes, typical)
    colors = [""] * len(boxes)
    for parity, (start, span) in enumerate((options["warm"], options["cool"])):
        members = [index for index, value in enumerate(parities) if value == parity]
        lookup = {member: position for position, member in enumerate(members)}
        subgraph = [{lookup[n] for n in graph[member] if n in lookup} for member in members]
        hues = _color_graph(subgraph)
        count = max(hues, default=-1) + 1
        for member, hue in zip(members, hues, strict=True):
            colors[order[member]] = _hsv_name(
                (start + span * hue / count) % 360.0 / 360.0, 1.0, 1.0 if hue % 2 == 0 else 0.7
            )
    return colors


def _color_of(node_id: str) -> Any:
    return lambda state: axidev_osk.read(state, ["std", "locator", node_id])


def _center(box: tuple[int, int, int, int]) -> tuple[int, int]:
    x, y, width, height = box
    return (2 * x + width - 1) // 2, (2 * y + height - 1) // 2


def _nearby(boxes: list[tuple[int, int, int, int]], distance: float) -> list[set[int]]:
    limit = distance**2
    neighbors: list[set[int]] = [set() for _ in boxes]
    for index, (x, y, width, height) in enumerate(boxes):
        for other, (ox, oy, owidth, oheight) in enumerate(boxes[:index]):
            horizontal = max(x - (ox + owidth - 1), ox - (x + width - 1), 0)
            vertical = max(y - (oy + oheight - 1), oy - (y + height - 1), 0)
            if horizontal**2 + vertical**2 <= limit:
                neighbors[index].add(other)
                neighbors[other].add(index)
    return neighbors


def _checkerboard(boxes: list[tuple[int, int, int, int]], typical: float) -> list[int]:
    rows: list[list[int]] = []
    for index in range(len(boxes)):
        if not rows or abs(_center(boxes[index])[1] - _center(boxes[rows[-1][0]])[1]) > typical / 2:
            rows.append([index])
        else:
            rows[-1].append(index)
    parities = [0] * len(boxes)
    for row_index, row in enumerate(rows):
        row.sort(key=lambda index: _center(boxes[index])[0])
        for column_index, index in enumerate(row):
            parities[index] = (row_index + column_index) % 2
    return parities


def _color_graph(graph: list[set[int]]) -> list[int]:
    """Greedy coloring that picks the most constrained vertex first (DSATUR)."""

    colors = [-1] * len(graph)
    while -1 in colors:
        vertex = max(
            (index for index, color in enumerate(colors) if color < 0),
            key=lambda index: (
                len({colors[n] for n in graph[index] if colors[n] >= 0}),
                len(graph[index]),
                -index,
            ),
        )
        taken = {colors[n] for n in graph[vertex] if colors[n] >= 0}
        colors[vertex] = next(color for color in range(len(graph)) if color not in taken)
    return colors


def _hsv_name(hue: float, saturation: float, value: float) -> str:
    red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)
    # Halves round up, as Qt rounds a color channel.
    return "#" + "".join(f"{int(channel * 255 + 0.5):02x}" for channel in (red, green, blue))
