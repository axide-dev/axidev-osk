"""Calling rules for profile callbacks and state bindings.

The engine calls profile functions with plain data and accepts plain data
back. The functions themselves live in ``function_registry``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from ..function_registry import FunctionRef, FunctionRegistry
from ..messages import DataMap, DataValue, RuntimeAction, copy_data_value
from .decoding import runtime_action_from_data
from .state import ReadRecorder, StateTree, StateView


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
    ``{"action": "window.show", "arguments": {...}}``. ``event`` is handed over
    as is: the dispatcher already gives each profile handler its own copy, and
    each returned action copies its arguments when it is built.
    """

    function = registry.get(ref)
    result = function(CallbackContext(state=state.view()), event)
    if result is None:
        return []
    if not isinstance(result, list):
        raise TypeError(f"Callback must return a list of actions, got {type(result).__name__}")
    actions: list[RuntimeAction] = []
    for index, item in enumerate(result):
        if not isinstance(item, dict):
            raise TypeError(f"Callback result item {index} must be an action map")
        actions.append(runtime_action_from_data(cast(DataMap, item)))
    return actions


def evaluate_binding(
    registry: FunctionRegistry,
    ref: FunctionRef,
    state: StateTree,
    recorder: ReadRecorder,
) -> DataValue:
    """Call ``fn(state)`` and return its plain value; ``recorder`` collects the paths it read, even on failure."""

    value = registry.get(ref)(state.view(recorder))
    if isinstance(value, StateView):
        value = value.to_data()
    return copy_data_value(value)
