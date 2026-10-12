"""Keyboard key builders built only from ``axidev_osk`` primitives.

Every key is built from a layout entry (``std.layouts``): ``key``, ``letter``,
``shifted``, ``modifier``, and ``lock`` build one fixed entry, ``at`` builds the
entry the active layout puts on a board position, and ``tap`` uses an entry at
once, for menus such as ``std.wheel``.

Library state lives under ``std``:

- ``std.latched.<latch>``: the output a latched modifier holds down.
- ``std.one_shot.<latch>``: the output a one-shot modifier adds to the next
  key press, which holds that real modifier key down around it.
- ``std.held.<node>``: the one-shot modifiers a key's press held down, by
  latch, so its release lets go of exactly those.

A modifier's latch is shared by the left and right keys of one modifier when
nothing else about them differs: ``ShiftLeft`` and ``ShiftRight`` both labelled
``Shift`` share one latch, while ``Alt`` and ``AltGr`` keep their own. Latching
either key lights both, and tapping the other releases the original press. The
``latch`` option names a latch explicitly to group or separate keys any other
way.

Profiles route ``keyboard.reset`` to ``on_reset`` (``std.with_handlers`` does it)
so latches clear when the engine releases every held key, and declare these
variables with ``std.with_state``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ... import axidev_osk
from . import layouts

_SHIFT_KEYS = ("ShiftLeft", "ShiftRight")
_LOCK_NAMES = {"CapsLock": "capslock", "NumLock": "numlock"}
_SIDES = ("Left", "Right")
_BEHAVIOR = ("repeat", "mode", "latch")

STATE = {
    "latched": axidev_osk.var(axidev_osk.map_of("string")),
    "one_shot": axidev_osk.var(axidev_osk.map_of("string")),
    "held": axidev_osk.var(axidev_osk.map_of(axidev_osk.map_of("string"))),
}
"""The library's key variables, merged under ``std`` by ``std.with_state``."""


def shift_active(state: Any) -> bool:
    """Whether Shift is held, physically or by a pending one-shot Shift."""

    return any(key_down(state, name) for name in _SHIFT_KEYS) or any(
        name in _SHIFT_KEYS for name in one_shot_keys(state)
    )


def key_down(state: Any, name: str) -> bool:
    """Whether a key is observed down; ``name`` may contain dots, such as ``.``."""

    return bool(axidev_osk.read(state, ["input", "keys", name]))


def caps_active(state: Any) -> bool:
    return bool(axidev_osk.read(state, "input.locks.capslock"))


def _one_shot(state: Any) -> dict[str, str]:
    pending = axidev_osk.read(state, "std.one_shot")
    return {latch: pending[latch] for latch in pending} if pending is not None else {}


def one_shot_keys(state: Any) -> list[str]:
    """Modifier keys waiting for the next key press."""

    return sorted(_one_shot(state).values())


def legend(state: Any, entry: Mapping[str, Any]) -> str:
    """What a layout entry shows: its shifted legend while Shift (and, for letters, not Caps Lock) is on."""

    shifted = entry.get("shifted")
    if shifted is None:
        return entry["label"]
    shift = shift_active(state)
    if entry["kind"] == "letter":
        shift = shift != caps_active(state)
    return shifted if shift else entry["label"]


def from_entry(entry: Mapping[str, Any], opts: Mapping[str, Any] | None = None) -> axidev_osk.Map:
    """A key button for one layout entry; ``opts`` overrides any button field."""

    defaults = {"id": f"key:{entry['output']}", **entry_fields(entry, opts)}
    return axidev_osk.button(**axidev_osk.merge(defaults, _without(opts, *_BEHAVIOR)))


def at(
    position: str,
    layouts: Mapping[str, Mapping[str, Mapping[str, Any]]],
    layout: axidev_osk.Binding,
    opts: Mapping[str, Any] | None = None,
) -> axidev_osk.Map:
    """A key for a board position whose meaning follows the active layout.

    ``layouts`` maps layout names to tables of entries by position, and the
    ``layout`` binding names the active one. Its legend, lit state, and what
    a press sends all come from the active layout's entry for ``position``.
    """

    variants = {name: entry_fields(table[position], opts) for name, table in layouts.items() if position in table}

    def value(field: str, default: Any) -> axidev_osk.Binding:
        def bound(state: Any) -> Any:
            found = variants[layout(state)].get(field, default)
            return found(state) if callable(found) else found

        return bound

    def callback(field: str) -> axidev_osk.Callback:
        def run(ctx: Any, event: Any) -> list[axidev_osk.Map]:
            handler = variants[layout(ctx.state)].get(field)
            return handler(ctx, event) if handler is not None else []

        return run

    defaults = {
        "id": f"key:{position}",
        "label": value("label", ""),
        "active": value("active", False),
        "latched": value("latched", False),
        "on_press": callback("on_press"),
        "on_release": callback("on_release"),
    }
    return axidev_osk.button(**axidev_osk.merge(defaults, _without(opts, *_BEHAVIOR)))


def tap(state: Any, entry: Mapping[str, Any]) -> list[axidev_osk.Map]:
    """Actions that use a layout entry at once, the way one click on a menu item does.

    A modifier toggles as a one-shot modifier for the next key. Any other key
    is tapped with the waiting one-shot modifiers, which then clear.
    """

    if entry["kind"] == "modifier":
        path = _one_shot_path(entry)
        return [axidev_osk.state.set(path, None if waiting(state, entry) else entry["output"])]
    held = _one_shot(state)
    actions = [axidev_osk.keyboard.tap(entry["output"], sorted(held.values()) or None)]
    actions += [axidev_osk.state.set(["std", "one_shot", latch], None) for latch in sorted(held)]
    return actions


def waiting(state: Any, entry: Mapping[str, Any]) -> bool:
    """Whether a modifier entry waits for the next key, as ``tap`` left it."""

    return entry["kind"] == "modifier" and axidev_osk.read(state, _one_shot_path(entry)) is not None


def _one_shot_path(entry: Mapping[str, Any]) -> list[str]:
    return ["std", "one_shot", _default_latch(entry["label"], entry["output"], "one_shot", True)]


def key(label: Any, output: str, opts: Mapping[str, Any] | None = None) -> axidev_osk.Map:
    """A momentary key: press sends ``output`` down, release sends it up."""

    return from_entry({"kind": "key", "label": label, "output": output}, opts)


def letter(char: str, opts: Mapping[str, Any] | None = None) -> axidev_osk.Map:
    """A letter key whose legend follows Shift and Caps Lock."""

    return from_entry(layouts.letter(char), opts)


def shifted(label: str, shifted_label: str, output: str, opts: Mapping[str, Any] | None = None) -> axidev_osk.Map:
    """A symbol key whose legend switches with Shift only."""

    return from_entry(layouts.shifted(label, shifted_label, output), opts)


def modifier(label: str, output: str, opts: Mapping[str, Any] | None = None) -> axidev_osk.Map:
    """A latching modifier.

    ``mode = "held"`` (default) holds the real key down from the first tap
    until the second. ``mode = "one_shot"`` sends nothing itself; the next key
    press holds the real modifier key down around it. See the module docstring
    for how keys share a latch.
    """

    return from_entry(layouts.modifier(label, output), opts)


def lock(label: str, output: str, opts: Mapping[str, Any] | None = None) -> axidev_osk.Map:
    """A lock key such as Caps Lock, lit from the system's observed lock state."""

    return from_entry(layouts.lock(label, output), opts)


def entry_fields(entry: Mapping[str, Any], opts: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The button fields a layout entry gives a key: its label, lit states, and callbacks.

    ``opts`` may set ``repeat`` for any key, and ``mode`` and ``latch`` for a modifier.
    """

    kind, output = entry["kind"], entry["output"]
    if kind == "modifier":
        return _modifier_fields(entry["label"], output, opts)
    repeat = False if kind == "lock" else _flag(opts, "repeat", True)
    fields = _key_fields(output, repeat)
    fields["label"] = entry["label"] if kind in {"key", "lock"} else (lambda state: legend(state, entry))
    if kind == "lock":
        lock_name = _LOCK_NAMES.get(output)
        if lock_name is None:
            raise ValueError(f"{output!r} is not an observed lock key")
        fields["latched"] = lambda state: bool(axidev_osk.read(state, ["input", "locks", lock_name]))
    elif kind not in {"key", "letter", "shifted"}:
        raise ValueError(f"Unknown layout entry kind {kind!r}")
    return fields


def _key_fields(output: str, repeat: bool) -> dict[str, Any]:
    def on_press(ctx: Any, event: Any) -> list[axidev_osk.Map]:
        held = _one_shot(ctx.state)
        actions = [axidev_osk.keyboard.down(name, repeat=False) for _latch, name in sorted(held.items())]
        actions.append(axidev_osk.keyboard.down(output, repeat=repeat))
        if held:
            actions.append(axidev_osk.state.set(["std", "held", event["node"]], held))
        return actions

    def on_release(ctx: Any, event: Any) -> list[axidev_osk.Map]:
        actions = [axidev_osk.keyboard.up(output)]
        held = axidev_osk.read(ctx.state, ["std", "held", event["node"]])
        if held is None:
            return actions
        for latch in sorted(held):
            actions.append(axidev_osk.keyboard.up(held[latch]))
            actions.append(axidev_osk.state.set(["std", "one_shot", latch], None))
        actions.append(axidev_osk.state.set(["std", "held", event["node"]], None))
        return actions

    return {
        "active": lambda state: key_down(state, output),
        "on_press": on_press,
        "on_release": on_release,
    }


def _modifier_fields(label: str, output: str, opts: Mapping[str, Any] | None) -> dict[str, Any]:
    repeat = _flag(opts, "repeat", True)
    mode = (opts or {}).get("mode") or "held"
    latch = (opts or {}).get("latch") or _default_latch(label, output, mode, repeat)
    if mode not in {"held", "one_shot"}:
        raise ValueError(f"Unknown modifier mode {mode!r}")
    latch_path = ["std", "one_shot" if mode == "one_shot" else "latched", latch]

    def latched(state: Any) -> bool:
        return axidev_osk.read(state, latch_path) is not None

    if mode == "one_shot":

        def toggle_one_shot(ctx: Any, event: Any) -> list[axidev_osk.Map]:
            del event
            return [axidev_osk.state.set(latch_path, None if latched(ctx.state) else output)]

        return {"label": label, "latched": latched, "on_release": toggle_one_shot}

    def on_press(ctx: Any, event: Any) -> list[axidev_osk.Map]:
        del event
        if latched(ctx.state):
            return []
        return [axidev_osk.keyboard.down(output, repeat=repeat)]

    def on_release(ctx: Any, event: Any) -> list[axidev_osk.Map]:
        del event
        held = axidev_osk.read(ctx.state, latch_path)
        if held is not None:
            return [axidev_osk.state.set(latch_path, None), axidev_osk.keyboard.up(held)]
        return [axidev_osk.state.set(latch_path, output)]

    return {
        "label": label,
        "latched": latched,
        "active": lambda state: key_down(state, output),
        "on_press": on_press,
        "on_release": on_release,
    }


def on_reset(ctx: Any, event: Any) -> list[axidev_osk.Map]:
    """Clear library latches after the engine released every held key."""

    del ctx, event
    return [
        axidev_osk.state.set("std.latched", None),
        axidev_osk.state.set("std.one_shot", None),
        axidev_osk.state.set("std.held", None),
    ]


def _default_latch(label: str, output: str, mode: str, repeat: bool) -> str:
    """Name the latch a key shares with its other-side twin only when everything else matches."""

    side = next((side for side in _SIDES if output.endswith(side) and len(output) > len(side)), "")
    return f"{output[: len(output) - len(side)]}|{label}|{mode}|{repeat}"


def _flag(opts: Mapping[str, Any] | None, name: str, default: bool) -> bool:
    """Read a boolean option, where ``None`` counts as absent as Lua's ``nil`` does."""

    value = (opts or {}).get(name)
    return default if value is None else bool(value)


def _without(opts: Mapping[str, Any] | None, *names: str) -> dict[str, Any]:
    return {name: value for name, value in (opts or {}).items() if name not in names}
