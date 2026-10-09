"""The profile-facing ``osk`` surface, written in Python until Lua replaces it.

Everything here builds plain maps. Nothing calls the engine directly. A Lua
``osk`` module will expose the same names and return the same tables:

- Node builders: ``window``, ``grid``, ``box``, ``stack``, ``button``,
  ``label``, ``spacer``.
- Attachment builders: ``dwell``, ``pointer_locator``, ``hot_corners``,
  ``secure_input_panel``.
- Action builders grouped by subject: ``state``, ``keyboard``, ``window``,
  ``dwell``, ``process``, ``log``, ``app``, ``linux``.
- Helpers: ``config``, ``profile``, ``merge``, ``read``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

Map = dict[str, Any]


def action(name: str, **arguments: Any) -> Map:
    """Build one action map; every action builder below uses this shape."""

    return {"action": name, "arguments": {key: value for key, value in arguments.items() if value is not None}}


def merge(defaults: Mapping[str, Any], opts: Mapping[str, Any] | None = None) -> Map:
    """Return ``defaults`` with any field from ``opts`` replacing it."""

    merged = dict(defaults)
    if opts:
        merged.update(opts)
    return merged


def read(state: Any, path: str | list[str]) -> Any:
    """Read a state path, returning ``None`` when any part is absent.

    ``path`` is ``"a.b.c"`` or ``["a", "b", "c"]``; use the list form when a
    segment comes from a name that may contain dots, such as a key or node ID.
    """

    value = state
    for segment in path.split(".") if isinstance(path, str) else path:
        if value is None:
            return None
        value = value[segment]
    return value


def config(*, active_profile: str, profiles: Mapping[str, Map]) -> Map:
    return {"active_profile": active_profile, "profiles": dict(profiles)}


def profile(
    *,
    windows: list[Map],
    state: Map | None = None,
    attachments: list[Map] | None = None,
    on: Mapping[str, Any] | None = None,
    theme: Map | None = None,
) -> Map:
    result: Map = {"windows": windows}
    if state is not None:
        result["state"] = state
    if attachments is not None:
        result["attachments"] = attachments
    if on is not None:
        result["on"] = dict(on)
    if theme is not None:
        result["theme"] = theme
    return result


def _node(kind: str, fields: Mapping[str, Any]) -> Map:
    return {"kind": kind, **fields}


def grid(**fields: Any) -> Map:
    return _node("grid", fields)


def box(**fields: Any) -> Map:
    return _node("box", fields)


def stack(**fields: Any) -> Map:
    return _node("stack", fields)


def button(**fields: Any) -> Map:
    return _node("button", fields)


def label(**fields: Any) -> Map:
    return _node("label", fields)


def spacer(**fields: Any) -> Map:
    return _node("spacer", fields)


class _Window:
    """``osk.window(...)`` builds a window; ``osk.window.show(...)`` builds an action."""

    def __call__(self, **fields: Any) -> Map:
        return dict(fields)

    @staticmethod
    def show(window: str) -> Map:
        return action("window.show", window=window)

    @staticmethod
    def hide(window: str) -> Map:
        return action("window.hide", window=window)

    @staticmethod
    def close(window: str) -> Map:
        return action("window.close", window=window)

    @staticmethod
    def move_by(window: str, dx: int, dy: int) -> Map:
        return action("window.move_by", window=window, dx=dx, dy=dy)

    @staticmethod
    def set_opacity(window: str, opacity: float) -> Map:
        return action("window.set_opacity", window=window, opacity=opacity)

    @staticmethod
    def block_input(window: str, allowed: list[str] | None = None) -> Map:
        return {"action": "window.block_input", "arguments": {"window": window, "except": list(allowed or [])}}

    @staticmethod
    def unblock_input(window: str) -> Map:
        return action("window.unblock_input", window=window)


window = _Window()


class _Dwell:
    """``osk.dwell(...)`` attaches dwell clicking; ``osk.dwell.set_enabled`` toggles it."""

    def __call__(self, **fields: Any) -> Map:
        return {"kind": "dwell", **fields}

    @staticmethod
    def set_enabled(dwell: str, enabled: bool) -> Map:
        return action("dwell.set_enabled", dwell=dwell, enabled=enabled)


dwell = _Dwell()


def pointer_locator(**fields: Any) -> Map:
    return {"kind": "pointer_locator", **fields}


def hot_corners(**fields: Any) -> Map:
    return {"kind": "hot_corners", **fields}


def secure_input_panel(**fields: Any) -> Map:
    return {"kind": "secure_input_panel", **fields}


class state:  # noqa: N801 - mirrors the Lua ``osk.state`` table
    @staticmethod
    def set(path: str | list[str], value: Any) -> Map:
        """Set a profile state path (``"a.b"`` or ``["a", "b"]``); ``None`` removes it."""

        return {"action": "state.set", "arguments": {"path": path if isinstance(path, str) else list(path), "value": value}}


class keyboard:  # noqa: N801
    @staticmethod
    def down(key: str, mods: list[str] | None = None, repeat: bool = True) -> Map:
        return action("keyboard.down", key=key, mods=list(mods or []), repeat=repeat)

    @staticmethod
    def up(key: str) -> Map:
        return action("keyboard.up", key=key)

    @staticmethod
    def tap(key: str, mods: list[str] | None = None) -> Map:
        return action("keyboard.tap", key=key, mods=list(mods or []))

    @staticmethod
    def type_text(text: str) -> Map:
        return action("keyboard.type_text", text=text)


class process:  # noqa: N801
    @staticmethod
    def spawn(argv: list[str], tag: str, detached: bool = False) -> Map:
        return action("process.spawn", argv=list(argv), tag=tag, detached=detached)


class log:  # noqa: N801
    @staticmethod
    def info(message: str) -> Map:
        return action("log.info", message=message)

    @staticmethod
    def warn(message: str) -> Map:
        return action("log.warn", message=message)

    @staticmethod
    def error(message: str) -> Map:
        return action("log.error", message=message)


class app:  # noqa: N801
    @staticmethod
    def quit(exit_code: int = 0) -> Map:
        return action("app.quit", exit_code=exit_code)


class linux:  # noqa: N801
    @staticmethod
    def open_permission_setup() -> Map:
        return action("linux.open_permission_setup")
