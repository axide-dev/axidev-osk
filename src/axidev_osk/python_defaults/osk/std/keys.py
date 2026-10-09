"""Keyboard key builders built only from ``osk`` primitives.

Library state lives under ``std``:

- ``std.latched.<node id>``: a modifier button is latched.
- ``std.one_shot.<modifier>``: a one-shot modifier waits for the next key.

Profiles should route ``keyboard.reset`` to ``on_reset`` so latches clear
when the engine releases every held key.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ... import osk

_SHIFT_KEYS = ("ShiftLeft", "ShiftRight")
_MODIFIER_NAMES = {
    "ShiftLeft": "Shift",
    "ShiftRight": "Shift",
    "CtrlLeft": "Ctrl",
    "CtrlRight": "Ctrl",
    "AltLeft": "Alt",
    "AltRight": "AltGr",
    "SuperLeft": "Super",
    "SuperRight": "Super",
}
_LOCK_NAMES = {"CapsLock": "capslock", "NumLock": "numlock"}


def shift_active(state: Any) -> bool:
    """Whether Shift is held, physically or by a latched on-screen Shift."""

    return any(key_down(state, name) for name in _SHIFT_KEYS) or bool(
        osk.read(state, "std.one_shot.Shift")
    )


def key_down(state: Any, name: str) -> bool:
    """Whether a key is observed down; ``name`` may contain dots, such as ``.``."""

    return bool(osk.read(state, ["input", "keys", name]))


def caps_active(state: Any) -> bool:
    return bool(osk.read(state, "input.locks.capslock"))


def one_shot_mods(state: Any) -> list[str]:
    pending = osk.read(state, "std.one_shot")
    return sorted(name for name in pending if pending[name]) if pending is not None else []


def key(label: Any, output: str, opts: Mapping[str, Any] | None = None) -> osk.Map:
    """A momentary key: press sends ``output`` down, release sends it up."""

    repeat = bool((opts or {}).get("repeat", True))

    def on_press(ctx: Any, event: Any) -> list[osk.Map]:
        del event
        return [osk.keyboard.down(output, mods=one_shot_mods(ctx.state), repeat=repeat)]

    def on_release(ctx: Any, event: Any) -> list[osk.Map]:
        del event
        actions = [osk.keyboard.up(output)]
        for name in one_shot_mods(ctx.state):
            actions.append(osk.state.set(["std", "one_shot", name], None))
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
    until the second. ``mode = "one_shot"`` sends nothing itself and adds the
    modifier to the next key press.
    """

    options = dict(opts or {})
    mode = options.pop("mode", "held")
    repeat = bool(options.pop("repeat", True))
    node_id = options.get("id", f"key:{output}")
    latch_path = ["std", "latched", node_id]
    modifier_name = _MODIFIER_NAMES.get(output, output)

    if mode == "one_shot":
        one_shot_path = ["std", "one_shot", modifier_name]

        def toggle_one_shot(ctx: Any, event: Any) -> list[osk.Map]:
            del event
            return [osk.state.set(one_shot_path, None if osk.read(ctx.state, one_shot_path) else True)]

        defaults: dict[str, Any] = {
            "id": node_id,
            "label": label,
            "latched": lambda state: bool(osk.read(state, one_shot_path)),
            "on_release": toggle_one_shot,
        }
        return osk.button(**osk.merge(defaults, options))
    if mode != "held":
        raise ValueError(f"Unknown modifier mode {mode!r}")

    def on_press(ctx: Any, event: Any) -> list[osk.Map]:
        del event
        if osk.read(ctx.state, latch_path):
            return []
        return [osk.keyboard.down(output, repeat=repeat)]

    def on_release(ctx: Any, event: Any) -> list[osk.Map]:
        del event
        if osk.read(ctx.state, latch_path):
            return [osk.state.set(latch_path, None), osk.keyboard.up(output)]
        return [osk.state.set(latch_path, True)]

    defaults = {
        "id": node_id,
        "label": label,
        "latched": lambda state: bool(osk.read(state, latch_path)),
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
    return [osk.state.set("std.latched", None), osk.state.set("std.one_shot", None)]


def _without(opts: Mapping[str, Any] | None, *names: str) -> dict[str, Any]:
    return {name: value for name, value in (opts or {}).items() if name not in names}
