"""Keyboard key builders built only from ``osk`` primitives.

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
so latches clear when the engine releases every held key.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ... import osk

_SHIFT_KEYS = ("ShiftLeft", "ShiftRight")
_LOCK_NAMES = {"CapsLock": "capslock", "NumLock": "numlock"}
_SIDES = ("Left", "Right")


def shift_active(state: Any) -> bool:
    """Whether Shift is held, physically or by a pending one-shot Shift."""

    return any(key_down(state, name) for name in _SHIFT_KEYS) or any(
        name in _SHIFT_KEYS for name in one_shot_keys(state)
    )


def key_down(state: Any, name: str) -> bool:
    """Whether a key is observed down; ``name`` may contain dots, such as ``.``."""

    return bool(osk.read(state, ["input", "keys", name]))


def caps_active(state: Any) -> bool:
    return bool(osk.read(state, "input.locks.capslock"))


def _one_shot(state: Any) -> dict[str, str]:
    pending = osk.read(state, "std.one_shot")
    return {latch: pending[latch] for latch in pending} if pending is not None else {}


def one_shot_keys(state: Any) -> list[str]:
    """Modifier keys waiting for the next key press."""

    return sorted(_one_shot(state).values())


def key(label: Any, output: str, opts: Mapping[str, Any] | None = None) -> osk.Map:
    """A momentary key: press sends ``output`` down, release sends it up."""

    repeat = _flag(opts, "repeat", True)

    def on_press(ctx: Any, event: Any) -> list[osk.Map]:
        held = _one_shot(ctx.state)
        actions = [osk.keyboard.down(name, repeat=False) for _latch, name in sorted(held.items())]
        actions.append(osk.keyboard.down(output, repeat=repeat))
        if held:
            actions.append(osk.state.set(["std", "held", event["node"]], held))
        return actions

    def on_release(ctx: Any, event: Any) -> list[osk.Map]:
        actions = [osk.keyboard.up(output)]
        held = osk.read(ctx.state, ["std", "held", event["node"]])
        if held is None:
            return actions
        for latch in sorted(held):
            actions.append(osk.keyboard.up(held[latch]))
            actions.append(osk.state.set(["std", "one_shot", latch], None))
        actions.append(osk.state.set(["std", "held", event["node"]], None))
        return actions

    defaults = {
        "id": f"key:{output}",
        "label": label,
        "active": lambda state: key_down(state, output),
        "on_press": on_press,
        "on_release": on_release,
    }
    return osk.button(**osk.merge(defaults, _without(opts, "repeat")))


def letter(char: str, opts: Mapping[str, Any] | None = None) -> osk.Map:
    """A letter key whose legend follows Shift and Caps Lock."""

    lower, upper = char.lower(), char.upper()
    return key(
        lambda state: upper if shift_active(state) != caps_active(state) else lower,
        upper,
        opts,
    )


def shifted(label: str, shifted_label: str, output: str, opts: Mapping[str, Any] | None = None) -> osk.Map:
    """A symbol key whose legend switches with Shift only."""

    return key(lambda state: shifted_label if shift_active(state) else label, output, opts)


def modifier(label: str, output: str, opts: Mapping[str, Any] | None = None) -> osk.Map:
    """A latching modifier.

    ``mode = "held"`` (default) holds the real key down from the first tap
    until the second. ``mode = "one_shot"`` sends nothing itself; the next key
    press holds the real modifier key down around it. See the module docstring
    for how keys share a latch.
    """

    repeat = _flag(opts, "repeat", True)
    options = _without(opts, "mode", "repeat", "latch")
    mode = (opts or {}).get("mode") or "held"
    latch = (opts or {}).get("latch") or _default_latch(label, output, mode, repeat)
    if mode not in {"held", "one_shot"}:
        raise ValueError(f"Unknown modifier mode {mode!r}")
    latch_path = ["std", "one_shot" if mode == "one_shot" else "latched", latch]

    def latched(state: Any) -> bool:
        return osk.read(state, latch_path) is not None

    if mode == "one_shot":

        def toggle_one_shot(ctx: Any, event: Any) -> list[osk.Map]:
            del event
            return [osk.state.set(latch_path, None if latched(ctx.state) else output)]

        defaults: dict[str, Any] = {
            "id": f"key:{output}",
            "label": label,
            "latched": latched,
            "on_release": toggle_one_shot,
        }
        return osk.button(**osk.merge(defaults, options))

    def on_press(ctx: Any, event: Any) -> list[osk.Map]:
        del event
        if latched(ctx.state):
            return []
        return [osk.keyboard.down(output, repeat=repeat)]

    def on_release(ctx: Any, event: Any) -> list[osk.Map]:
        del event
        held = osk.read(ctx.state, latch_path)
        if held is not None:
            return [osk.state.set(latch_path, None), osk.keyboard.up(held)]
        return [osk.state.set(latch_path, output)]

    defaults = {
        "id": f"key:{output}",
        "label": label,
        "latched": latched,
        "active": lambda state: key_down(state, output),
        "on_press": on_press,
        "on_release": on_release,
    }
    return osk.button(**osk.merge(defaults, options))


def lock(label: str, output: str, opts: Mapping[str, Any] | None = None) -> osk.Map:
    """A lock key such as Caps Lock, lit from the system's observed lock state."""

    lock_name = _LOCK_NAMES.get(output)
    if lock_name is None:
        raise ValueError(f"{output!r} is not an observed lock key")
    return key(
        label,
        output,
        osk.merge(
            {"repeat": False, "latched": lambda state: bool(osk.read(state, ["input", "locks", lock_name]))},
            opts,
        ),
    )


def on_reset(ctx: Any, event: Any) -> list[osk.Map]:
    """Clear library latches after the engine released every held key."""

    del ctx, event
    return [
        osk.state.set("std.latched", None),
        osk.state.set("std.one_shot", None),
        osk.state.set("std.held", None),
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
