"""The profile-facing ``axidev_osk`` surface, written in Python until Lua replaces it.

Everything here builds plain maps. Nothing calls the engine directly. A Lua
``axidev_osk`` module will expose the same names and return the same tables:

- Node builders: ``window``, ``grid``, ``box``, ``stack``, ``button``,
  ``label``, ``spacer``.
- Attachment builders: ``dwell``, ``pointer_locator``, ``hot_corners``,
  ``secure_input_panel``.
- Action builders grouped by subject: ``state``, ``keyboard``, ``window``,
  ``process``, ``log``, ``app``, ``linux``.
- State declarations: ``var`` with the types ``list_of``, ``map_of``, and
  ``record``.
- Helpers: ``config``, ``profile``, ``merge``, ``read``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

Map = dict[str, Any]
Binding = Callable[[Any], Any]
"""``fn(state) -> value``: a value that follows state, accepted by any value field."""
Callback = Callable[[Any, Any], "list[Map] | None"]
"""``fn(ctx, event) -> [actions]``: what happens when an event arrives."""


def action(name: str, **arguments: Any) -> Map:
    """Build one action map, leaving out arguments set to ``None`` as Lua leaves out ``nil``.

    ``state.set`` builds its map directly, because a ``None`` value is how it removes a path.
    """

    return {"action": name, "arguments": {key: value for key, value in arguments.items() if value is not None}}


def merge(defaults: Mapping[str, Any], opts: Mapping[str, Any] | None = None) -> Map:
    """Return ``defaults`` with any field from ``opts`` replacing it."""

    merged = dict(defaults)
    if opts:
        merged.update(opts)
    return merged


def read(state: Any, path: str | list[str]) -> Any:
    """Read a state path, returning ``None`` when any part is absent or is not a map.

    ``path`` is ``"a.b.c"`` or ``["a", "b", "c"]``; use the list form when a
    segment comes from a name that may contain dots, such as a key or node ID.
    """

    value = state
    for segment in path.split(".") if isinstance(path, str) else path:
        if value is None or isinstance(value, (str, int, float, list, tuple)):
            return None
        value = value[segment]
    return value


def var(var_type: Any, default: Any = None) -> Map:
    """Declare a state variable of ``var_type``; ``None`` resets it to ``default``.

    ``var_type`` is ``"boolean"``, ``"integer"``, ``"number"``, ``"string"``,
    ``list_of(T)``, ``map_of(T)``, or ``record({...})``. A list or map defaults
    to empty, and a record takes its default from its fields.
    """

    declaration: Map = {"var": var_type}
    if default is not None:
        declaration["default"] = default
    return declaration


def list_of(item: Any) -> Map:
    return {"list": item}


def map_of(item: Any) -> Map:
    return {"map": item}


def record(fields: Mapping[str, Map]) -> Map:
    """A record type whose fields are ``var`` declarations."""

    return {"record": dict(fields)}


def config(*, active_profile: str, profiles: Mapping[str, Map], state: Map | None = None) -> Map:
    """Build a root config; ``state`` declares variables every profile shares, which survive a profile switch."""

    result: Map = {"active_profile": active_profile, "profiles": dict(profiles)}
    if state is not None:
        result["state"] = state
    return result


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
    """``axidev_osk.window(...)`` builds a window; ``axidev_osk.window.show(...)`` builds an action."""

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
    def resize_by(window: str, dx: int, dy: int) -> Map:
        return action("window.resize_by", window=window, dx=dx, dy=dy)

    @staticmethod
    def move_to(window: str, x: int, y: int) -> Map:
        """Put ``window``'s top-left corner at the screen point ``(x, y)``."""

        return action("window.move_to", window=window, x=x, y=y)

    @staticmethod
    def resize_to(window: str, width: int, height: int) -> Map:
        return action("window.resize_to", window=window, width=width, height=height)

    @staticmethod
    def click(window: str, x: int, y: int, button: str = "left") -> Map:
        """Click whatever is under the screen point ``(x, y)`` in ``window`` with the mouse ``button``."""

        return action("window.click", window=window, x=x, y=y, button=button)


window = _Window()


def dwell(**fields: Any) -> Map:
    return {"kind": "dwell", **fields}


def pointer_locator(**fields: Any) -> Map:
    return {"kind": "pointer_locator", **fields}


def hot_corners(**fields: Any) -> Map:
    return {"kind": "hot_corners", **fields}


def secure_input_panel(**fields: Any) -> Map:
    return {"kind": "secure_input_panel", **fields}


class state:  # noqa: N801 - mirrors the Lua ``axidev_osk.state`` table
    @staticmethod
    def set(path: str | list[str], value: Any) -> Map:
        """Set a declared state path (``"a.b"`` or ``["a", "b"]``); ``None`` resets it to its default or removes a map entry."""

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


class timer:  # noqa: N801
    @staticmethod
    def start(timer_id: str, delay_ms: int, repeat: bool = False) -> Map:
        """Post ``timer.fired`` with ``timer_id`` after ``delay_ms``, and every ``delay_ms`` while ``repeat``."""

        return action("timer.start", id=timer_id, delay_ms=delay_ms, repeat=repeat)

    @staticmethod
    def cancel(timer_id: str) -> Map:
        return action("timer.cancel", id=timer_id)


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
