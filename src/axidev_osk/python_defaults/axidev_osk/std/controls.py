"""Settings controls built only from ``axidev_osk`` primitives: checkbox, stepper, menu, dropdown, and strip.

Each control reads and writes state, so a profile decides what it controls.
Menus and dropdowns open as inline panels inside the window, not as popups,
because popups fail on layer-shell windows. A menu is a button plus a panel
the profile places anywhere in the same window; the window grows while the
panel shows and shrinks back when it hides. A strip is a menu shaped as a
bottom row: closed it shows only a ``⋯`` button, open it shows its controls
beside the button and their panels above it.

Library state lives under ``std.menus.<group>``: the ID of the menu open in
that group. Menus in one group close each other; a menu without a group is
its own group. Menus inside a strip share the group ``strip_group(strip id)``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ... import axidev_osk

STATE = {"menus": axidev_osk.var(axidev_osk.map_of("string"))}
"""The library's control variables, merged under ``std`` by ``std.with_state``."""

Number = int | float
NumberOrBinding = Number | Callable[[Any], Number]
OnSelect = Callable[[Any, Any], "list[axidev_osk.Map]"]
"""``fn(ctx, value) -> [actions]``: what choosing a dropdown value does."""


def menu_open(state: Any, menu: str, group: str | None = None) -> bool:
    return axidev_osk.read(state, ["std", "menus", group or menu]) == menu


def open_menu(menu: str, group: str | None = None) -> list[axidev_osk.Map]:
    """Open ``menu``, closing whichever menu of its group was open."""

    return [axidev_osk.state.set(["std", "menus", group or menu], menu)]


def close_menu(menu: str, group: str | None = None) -> list[axidev_osk.Map]:
    return [axidev_osk.state.set(["std", "menus", group or menu], None)]


def toggle_menu(state: Any, menu: str, group: str | None = None) -> list[axidev_osk.Map]:
    return close_menu(menu, group) if menu_open(state, menu, group) else open_menu(menu, group)


def strip_group(strip: str) -> str:
    """The menu group of the menus placed inside a strip."""

    return f"{strip}:items"


def checkbox(id: str, label: Any, path: str | list[str], opts: Mapping[str, Any] | None = None) -> axidev_osk.Map:  # noqa: A002
    """A button lit while the boolean at ``path`` is true; releasing it flips the value."""

    def toggle(ctx: Any, event: Any) -> list[axidev_osk.Map]:
        del event
        return [axidev_osk.state.set(path, not axidev_osk.read(ctx.state, path))]

    defaults = {
        "id": id,
        "label": label,
        "latched": lambda state: bool(axidev_osk.read(state, path)),
        "on_release": toggle,
    }
    return axidev_osk.button(**axidev_osk.merge(defaults, opts))


def stepper(
    id: str,  # noqa: A002
    path: str | list[str],
    *,
    minimum: NumberOrBinding,
    maximum: NumberOrBinding,
    step: Number,
    label: str | None = None,
    format: Callable[[Number], str] | None = None,  # noqa: A002
    opts: Mapping[str, Any] | None = None,
) -> axidev_osk.Map:
    """A caption, a minus button, the value at ``path``, and a plus button, in one row.

    ``minimum`` and ``maximum`` may be bindings, so linked settings can bound
    each other. Each press moves the value by ``step`` and clamps it to the
    bounds; a button is disabled once the value reaches its bound. ``format``
    turns the value into its label text. ``opts`` replaces fields of the row.
    """

    show = format or _format_number

    def value(state: Any) -> Number:
        return axidev_osk.read(state, path)

    def bound(limit: NumberOrBinding, state: Any) -> Number:
        return limit(state) if callable(limit) else limit

    def move(direction: int) -> axidev_osk.Callback:
        def on_release(ctx: Any, event: Any) -> list[axidev_osk.Map]:
            del event
            current = value(ctx.state)
            # Rounding keeps repeated decimal steps such as 0.05 from drifting.
            moved = round(current + direction * step, 9)
            clamped = min(max(moved, bound(minimum, ctx.state)), bound(maximum, ctx.state))
            if isinstance(current, int) and isinstance(step, int):
                clamped = int(clamped)
            return [] if clamped == current else [axidev_osk.state.set(path, clamped)]

        return on_release

    children: list[axidev_osk.Map] = []
    if label is not None:
        children.append(axidev_osk.label(id=f"{id}:label", text=label, stretch=1))
    children.extend(
        [
            axidev_osk.button(
                id=f"{id}:down",
                label="−",
                enabled=lambda state: value(state) > bound(minimum, state),
                on_release=move(-1),
                style={"classes": ["stepperButton"]},
            ),
            axidev_osk.label(
                id=f"{id}:value",
                text=lambda state: show(value(state)),
                align="center",
                style={"classes": ["stepperValue"]},
            ),
            axidev_osk.button(
                id=f"{id}:up",
                label="+",
                enabled=lambda state: value(state) < bound(maximum, state),
                on_release=move(1),
                style={"classes": ["stepperButton"]},
            ),
        ]
    )
    defaults = {"id": id, "direction": "horizontal", "spacing": 4, "children": children}
    return axidev_osk.box(**axidev_osk.merge(defaults, opts))


def menu(
    id: str,  # noqa: A002
    label: Any,
    children: Sequence[axidev_osk.Map],
    *,
    group: str | None = None,
    opts: Mapping[str, Any] | None = None,
    panel_opts: Mapping[str, Any] | None = None,
) -> tuple[axidev_osk.Map, axidev_osk.Map]:
    """Return a button that opens and closes the menu, and the panel it shows.

    The profile places both, usually the button in a strip and the panel in
    that strip's panels. Opening the menu closes the other menus of ``group``.
    ``opts`` replaces fields of the button and ``panel_opts`` fields of the panel.
    """

    button_defaults = {
        "id": id,
        "label": label,
        "latched": lambda state: menu_open(state, id, group),
        "on_release": lambda ctx, event: toggle_menu(ctx.state, id, group),
    }
    panel_defaults = {
        "id": f"{id}:panel",
        "visible": lambda state: menu_open(state, id, group),
        "spacing": 4,
        "children": list(children),
        "style": {"classes": ["menuPanel"]},
    }
    return axidev_osk.button(**axidev_osk.merge(button_defaults, opts)), axidev_osk.box(**axidev_osk.merge(panel_defaults, panel_opts))


def dropdown(
    id: str,  # noqa: A002
    choices: Sequence[tuple[Any, str]],
    *,
    value: Callable[[Any], Any],
    on_select: OnSelect,
    label: str | None = None,
    group: str | None = None,
    opts: Mapping[str, Any] | None = None,
    panel_opts: Mapping[str, Any] | None = None,
) -> tuple[axidev_osk.Map, axidev_osk.Map]:
    """A menu listing ``choices`` as ``(value, text)`` pairs; picking one runs ``on_select`` and closes it.

    ``value`` is a binding naming the current choice, which the button shows
    and the panel lights.
    """

    texts = {choice: text for choice, text in choices}

    def button_label(state: Any) -> str:
        current = texts.get(value(state), str(value(state)))
        return f"{label}: {current} ▾" if label is not None else f"{current} ▾"

    def pick(choice: Any) -> axidev_osk.Callback:
        def on_release(ctx: Any, event: Any) -> list[axidev_osk.Map]:
            del event
            return [*close_menu(id, group), *on_select(ctx, choice)]

        return on_release

    items = [
        axidev_osk.button(
            id=f"{id}:choice:{index}",
            label=text,
            latched=lambda state, choice=choice: value(state) == choice,
            on_release=pick(choice),
        )
        for index, (choice, text) in enumerate(choices)
    ]
    return menu(id, button_label, items, group=group, opts=opts, panel_opts=panel_opts)


def strip(
    id: str,  # noqa: A002
    children: Sequence[axidev_osk.Map],
    *,
    panels: Sequence[axidev_osk.Map] = (),
    opts: Mapping[str, Any] | None = None,
    toggle_opts: Mapping[str, Any] | None = None,
) -> axidev_osk.Map:
    """A bottom row holding a ``⋯`` button that shows ``children`` beside it and ``panels`` above it.

    Closed, the strip is only that button: wide and easy to hit, but one short
    row tall. Menus among ``children`` take ``group=strip_group(id)`` and put
    their panels in ``panels``. Closing the strip closes them too. ``opts``
    replaces fields of the strip's outer box and ``toggle_opts`` fields of the
    ``⋯`` button, whose style name is ``stripToggle``.
    """

    def is_open(state: Any) -> bool:
        return menu_open(state, id)

    def toggle(ctx: Any, event: Any) -> list[axidev_osk.Map]:
        del event
        if is_open(ctx.state):
            return [*close_menu(id), axidev_osk.state.set(["std", "menus", strip_group(id)], None)]
        return open_menu(id)

    defaults = {
        "id": id,
        "spacing": 4,
        "children": [
            axidev_osk.box(id=f"{id}:panels", visible=is_open, spacing=4, children=list(panels)),
            axidev_osk.box(
                id=f"{id}:row",
                direction="horizontal",
                spacing=6,
                children=[
                    axidev_osk.box(
                        id=f"{id}:controls",
                        direction="horizontal",
                        spacing=6,
                        visible=is_open,
                        stretch=1,
                        children=list(children),
                    ),
                    axidev_osk.spacer(id=f"{id}:gap", visible=lambda state: not is_open(state), stretch=1),
                    axidev_osk.button(
                        **axidev_osk.merge(
                            {
                                "id": f"{id}:toggle",
                                "label": "⋯",
                                "latched": is_open,
                                "on_release": toggle,
                                "min_width": 64,
                                "max_width": 64,
                                "min_height": 24,
                                "max_height": 24,
                                "style": {"object_name": "stripToggle"},
                            },
                            toggle_opts,
                        )
                    ),
                ],
            ),
        ],
    }
    return axidev_osk.box(**axidev_osk.merge(defaults, opts))


def with_strip(window: Mapping[str, Any], strip_node: axidev_osk.Map) -> axidev_osk.Map:
    """Return ``window`` with ``strip_node`` placed under its content, which takes all spare height."""

    content = axidev_osk.merge(window["content"], {"stretch": 1})
    return axidev_osk.window(
        **axidev_osk.merge(
            window,
            {"content": axidev_osk.box(id=f"{content['id']}:with-strip", children=[content, strip_node])},
        )
    )


def _format_number(value: Number) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)
