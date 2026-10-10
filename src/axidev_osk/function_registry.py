"""Stable IDs for profile functions, shared by the config decoder and the runtime.

Profile functions are Python callables today and Lua functions later. The
engine only stores them behind ``FunctionRef`` IDs; queue messages carry the
IDs, never the functions themselves.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

ProfileFunction = Callable[..., object]


@dataclass(frozen=True, slots=True)
class FunctionRef:
    """Stable ID of one registered profile function."""

    id: str


class FunctionRegistry:
    """Hold profile functions for the lifetime of the process.

    Registering the same function again returns its existing ID. The registry
    keeps every function alive, so an ID never points at a different function.
    """

    def __init__(self) -> None:
        self._functions: dict[str, ProfileFunction] = {}
        self._ids_by_object: dict[int, str] = {}

    def register(self, function: ProfileFunction) -> FunctionRef:
        if not callable(function):
            raise TypeError("Only callables can be registered as profile functions")
        existing = self._ids_by_object.get(id(function))
        if existing is not None:
            return FunctionRef(existing)
        function_id = f"fn:{len(self._functions) + 1}"
        self._functions[function_id] = function
        self._ids_by_object[id(function)] = function_id
        return FunctionRef(function_id)

    def get(self, ref: FunctionRef) -> ProfileFunction:
        function = self._functions.get(ref.id)
        if function is None:
            raise LookupError(f"Profile function {ref.id!r} is not registered")
        return function
