"""Registry and calling rules for profile callbacks and state bindings.

Profile functions are Python callables today and Lua functions later. The
engine only stores them behind ``FunctionRef`` IDs, calls them with plain
data, and accepts plain data back. Queue messages carry the IDs, never the
functions themselves.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..messages import DataMap, DataValue, RuntimeAction, copy_data_map
from .decoding import runtime_action_from_data
from .state import ReadRecorder, StatePath, StateTree, StateView

ProfileFunction = Callable[..., object]


@dataclass(frozen=True, slots=True)
class FunctionRef:
    """Stable ID of one registered profile function."""

    id: str


class FunctionRegistry:
    """Hold profile functions for the lifetime of one loaded profile."""

    def __init__(self) -> None:
        self._functions: dict[str, ProfileFunction] = {}
        self._ids_by_object: dict[int, str] = {}

    def register(self, function: ProfileFunction) -> FunctionRef:
        if not callable(function):
            raise TypeError("Only callables can be registered as profile functions")
        existing = self._ids_by_object.get(id(function))
        if existing is not None and self._functions.get(existing) is function:
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

    def clear(self) -> None:
        self._functions.clear()
        self._ids_by_object.clear()


@dataclass(frozen=True, slots=True)
class CallbackContext:
    """Everything a callback may use: a read-only view of current state."""

    state: StateView


def call_callback(
    registry: FunctionRegistry,
    ref: FunctionRef,
    state: StateTree,
    event: DataMap,
) -> list[RuntimeAction]:
    """Call ``fn(ctx, event)`` and decode the returned actions.

    A callback may return ``None`` or a list of action maps shaped like
    ``{"action": "window.show", "arguments": {...}}``.
    """

    function = registry.get(ref)
    result = function(CallbackContext(state=state.view()), copy_data_map(event))
    if result is None:
        return []
    if not isinstance(result, (list, tuple)):
        raise TypeError(f"Callback must return a list of actions, got {type(result).__name__}")
    actions: list[RuntimeAction] = []
    for index, item in enumerate(result):
        if not isinstance(item, dict):
            raise TypeError(f"Callback result item {index} must be an action map")
        actions.append(runtime_action_from_data(copy_data_map(item)))
    return actions


def evaluate_binding(
    registry: FunctionRegistry,
    ref: FunctionRef,
    state: StateTree,
) -> tuple[DataValue, frozenset[StatePath]]:
    """Call ``fn(state)`` and return its plain value plus the paths it read."""

    recorder = ReadRecorder()
    value = registry.get(ref)(state.view(recorder))
    if isinstance(value, StateView):
        value = value.to_data()
    plain = copy_data_map({"value": value})["value"]
    return plain, recorder.paths
