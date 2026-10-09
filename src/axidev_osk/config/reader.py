"""Path-aware reading of plain profile config maps.

Profiles are plain data plus functions, the same shape a Lua table produces.
``ConfigReader`` reads one map, reports errors with the full config path, and
rejects keys the decoder did not consume so typos fail loudly. A key set to
``None`` counts as absent, the way a Lua table has no key set to ``nil``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from typing import TypeVar

from ..function_registry import FunctionRef, FunctionRegistry
from ..messages import DataMap, DataValue, copy_data_map, copy_data_value

T = TypeVar("T")

_MISSING = object()
_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


class ConfigError(ValueError):
    """A profile config value is missing, malformed, or unknown."""


Bindable = DataValue | FunctionRef
"""A node property given either as a plain value or as a binding function."""


class ConfigReader:
    """Read typed fields from one config map at a known path."""

    def __init__(self, data: object, path: str, functions: FunctionRegistry) -> None:
        if not isinstance(data, Mapping):
            raise ConfigError(f"{path} must be a map, got {type(data).__name__}")
        for key in data:
            if not isinstance(key, str):
                raise ConfigError(f"{path} keys must be strings")
        self._data: Mapping[str, object] = data
        self._path = path
        self._functions = functions
        self._consumed: set[str] = set()

    @property
    def path(self) -> str:
        return self._path

    @property
    def functions(self) -> FunctionRegistry:
        return self._functions

    def field_path(self, key: str) -> str:
        return f"{self._path}.{key}"

    def has(self, key: str) -> bool:
        return self._data.get(key) is not None

    def raw(self, key: str, default: object = _MISSING) -> object:
        self._consumed.add(key)
        value = self._data.get(key)
        if value is not None:
            return value
        if default is _MISSING:
            raise ConfigError(f"{self.field_path(key)} is required")
        return default

    def string(self, key: str, default: str | None | object = _MISSING) -> str:
        value = self.raw(key, default)
        if not isinstance(value, str) or not value:
            raise ConfigError(f"{self.field_path(key)} must be a non-empty string")
        return value

    def optional_string(self, key: str) -> str | None:
        value = self.raw(key, None)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ConfigError(f"{self.field_path(key)} must be a string")
        return value

    def boolean(self, key: str, default: bool | object = _MISSING) -> bool:
        value = self.raw(key, default)
        if not isinstance(value, bool):
            raise ConfigError(f"{self.field_path(key)} must be a boolean")
        return value

    def integer(self, key: str, default: int | object = _MISSING, *, minimum: int | None = None) -> int:
        value = self.raw(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{self.field_path(key)} must be an integer")
        if minimum is not None and value < minimum:
            raise ConfigError(f"{self.field_path(key)} must be at least {minimum}")
        return value

    def number(
        self,
        key: str,
        default: float | object = _MISSING,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        value = self.raw(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ConfigError(f"{self.field_path(key)} must be a finite number")
        number = float(value)
        if minimum is not None and number < minimum:
            raise ConfigError(f"{self.field_path(key)} must be at least {minimum}")
        if maximum is not None and number > maximum:
            raise ConfigError(f"{self.field_path(key)} must be at most {maximum}")
        return number

    def color(self, key: str, default: str | object = _MISSING) -> str:
        """Read a ``#RRGGBB`` or ``#AARRGGBB`` color."""

        value = self.raw(key, default)
        if not isinstance(value, str) or not _COLOR.fullmatch(value):
            raise ConfigError(f"{self.field_path(key)} must be a color like #RRGGBB or #AARRGGBB")
        return value

    def choice(self, key: str, choices: frozenset[str], default: str | object = _MISSING) -> str:
        value = self.string(key, default)
        if value not in choices:
            raise ConfigError(f"{self.field_path(key)} must be one of {', '.join(sorted(choices))}")
        return value

    def data_map(self, key: str, default: DataMap | object = _MISSING) -> DataMap:
        value = self.raw(key, default)
        try:
            return copy_data_map(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{self.field_path(key)} must be plain data: {exc}") from exc

    def function(self, key: str) -> FunctionRef:
        value = self.raw(key)
        if not callable(value):
            raise ConfigError(f"{self.field_path(key)} must be a function")
        return self._functions.register(value)

    def optional_function(self, key: str) -> FunctionRef | None:
        value = self.raw(key, None)
        if value is None:
            return None
        if not callable(value):
            raise ConfigError(f"{self.field_path(key)} must be a function")
        return self._functions.register(value)

    def bindable(self, key: str, default: DataValue | object = _MISSING) -> Bindable:
        """Read a plain value or a binding function ``fn(state) -> value``."""

        value = self.raw(key, default)
        if callable(value):
            return self._functions.register(value)
        try:
            return copy_data_value(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{self.field_path(key)} must be plain data or a function: {exc}") from exc

    def string_list(self, key: str, default: list[str] | object = _MISSING) -> tuple[str, ...]:
        value = self.raw(key, default)
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise ConfigError(f"{self.field_path(key)} must be a list of non-empty strings")
        return tuple(value)

    def child(self, key: str) -> "ConfigReader":
        return ConfigReader(self.raw(key), self.field_path(key), self._functions)

    def optional_child(self, key: str) -> "ConfigReader | None":
        value = self.raw(key, None)
        if value is None:
            return None
        return ConfigReader(value, self.field_path(key), self._functions)

    def children(self, key: str, default: object = _MISSING) -> list["ConfigReader"]:
        """Read a list of maps, skipping ``None`` items as a Lua array has no ``nil`` entries."""

        value = self.raw(key, default)
        if not isinstance(value, list):
            raise ConfigError(f"{self.field_path(key)} must be a list")
        return [
            ConfigReader(item, f"{self.field_path(key)}[{index}]", self._functions)
            for index, item in enumerate(value)
            if item is not None
        ]

    def items(self, key: str, default: object = _MISSING) -> list[tuple[str, object]]:
        """Read a map's entries, skipping keys set to ``None``."""

        value = self.raw(key, default)
        if not isinstance(value, Mapping):
            raise ConfigError(f"{self.field_path(key)} must be a map")
        entries: list[tuple[str, object]] = []
        for name, item in value.items():
            if not isinstance(name, str):
                raise ConfigError(f"{self.field_path(key)} keys must be strings")
            if item is not None:
                entries.append((name, item))
        return entries

    def decode(self, decoder: Callable[["ConfigReader"], T]) -> T:
        """Run ``decoder`` on this map and reject keys it did not read."""

        result = decoder(self)
        self.finish()
        return result

    def finish(self) -> None:
        unknown = sorted(key for key, value in self._data.items() if value is not None and key not in self._consumed)
        if unknown:
            raise ConfigError(f"{self._path} has unknown keys: {', '.join(unknown)}")
