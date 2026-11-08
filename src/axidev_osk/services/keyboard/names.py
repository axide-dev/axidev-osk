"""The official spelling of key and modifier names, as axidev_io gives it.

axidev_io accepts many spellings of one key (``esc``, ``Escape``) and of one
modifier (``ctrl``, ``Control``, ``Ctrl``), but names each by exactly one. The
engine accepts only that official name, so a profile that sends ``esc`` fails
loudly instead of depending on how forgiving the parser is. Parsing and
formatting names works right after import, without initializing keyboard output.
"""

from __future__ import annotations

from typing import Any


class KeyNameError(ValueError):
    """A key or modifier name is unknown, or is not the official spelling."""


class KeyNamesUnavailable(RuntimeError):
    """axidev_io cannot be imported, so names cannot be checked."""


class KeyNames:
    """Check key and modifier names against axidev_io's official spelling."""

    def __init__(self, keys: Any) -> None:
        """``keys`` is axidev_io's ``keyboard.keys`` helper."""

        self._keys = keys

    @classmethod
    def load(cls) -> "KeyNames":
        """Import axidev_io's key helpers; raises ``KeyNamesUnavailable`` when it cannot be imported."""

        try:
            from axidev_io import keyboard
        except Exception as exc:
            raise KeyNamesUnavailable(f"axidev_io cannot be imported: {exc}") from exc
        return cls(keyboard.keys)

    def check_key(self, name: str) -> None:
        """Raise ``KeyNameError`` unless ``name`` is a key's official name."""

        try:
            official = self._keys.format(self._keys.parse(name))
        except Exception as exc:
            raise KeyNameError(f"Unknown key name {name!r}") from exc
        if official != name:
            raise KeyNameError(f"Key name {name!r} is not the official spelling; use {official!r}")

    def check_modifier(self, name: str) -> None:
        """Raise ``KeyNameError`` unless ``name`` is one modifier's official name."""

        try:
            official = self._keys.modifiers.to_names(self._keys.modifiers.resolve([name]))
        except Exception as exc:
            raise KeyNameError(f"Unknown modifier name {name!r}") from exc
        if len(official) != 1:
            raise KeyNameError(f"Unknown modifier name {name!r}")
        if official[0] != name:
            raise KeyNameError(f"Modifier name {name!r} is not the official spelling; use {official[0]!r}")

    def check(self, key: str, mods: tuple[str, ...] = ()) -> None:
        """Check a key and the modifiers sent with it."""

        self.check_key(key)
        for mod in mods:
            self.check_modifier(mod)
