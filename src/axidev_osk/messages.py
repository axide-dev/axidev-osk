"""Generic native-data messages shared by config and runtime code."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TypeAlias


DataValue: TypeAlias = None | bool | int | float | str | list["DataValue"] | dict[str, "DataValue"]
DataMap: TypeAlias = dict[str, DataValue]

_MESSAGE_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


def copy_data_map(value: object) -> DataMap:
    """Validate and recursively copy a native-data map."""

    copied = copy_data_value(value, path="arguments")
    if not isinstance(copied, dict):
        raise TypeError("arguments must be a map")
    return copied


def copy_data_value(value: object, *, path: str = "value") -> DataValue:
    """Validate and recursively copy one native-data value."""

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain only finite numbers")
        return value
    if isinstance(value, list):
        return [copy_data_value(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict):
        copied: DataMap = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings")
            copied[key] = copy_data_value(item, path=f"{path}.{key}")
        return copied
    raise TypeError(f"{path} contains unsupported value {type(value).__name__}")


def data_equal(left: DataValue, right: DataValue) -> bool:
    """Compare plain data the way Lua does: ``True`` is not ``1``, while ``1`` equals ``1.0``."""

    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(data_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(data_equal(left[key], right[key]) for key in left)
    if isinstance(left, (list, dict)) or isinstance(right, (list, dict)):
        return False
    return left == right


def _validate_message_name(name: str, *, field: str) -> None:
    if not _MESSAGE_NAME.fullmatch(name):
        raise ValueError(f"{field} must be a lowercase dot-separated name")


@dataclass(frozen=True, slots=True)
class RuntimeAction:
    """A queue-ready request to execute a registered action."""

    action: str
    arguments: DataMap

    def __post_init__(self) -> None:
        _validate_message_name(self.action, field="action")
        object.__setattr__(self, "arguments", copy_data_map(self.arguments))


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """A queue-ready observation delivered to registered event handlers."""

    event: str
    arguments: DataMap

    def __post_init__(self) -> None:
        _validate_message_name(self.event, field="event")
        object.__setattr__(self, "arguments", copy_data_map(self.arguments))


RuntimeMessage: TypeAlias = RuntimeAction | RuntimeEvent
MessageResult: TypeAlias = list[RuntimeMessage]
