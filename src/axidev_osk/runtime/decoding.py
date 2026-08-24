"""Small native-data decoders used by registered runtime messages."""

from __future__ import annotations

from collections.abc import Iterable

from ..messages import DataMap, DataValue, RuntimeAction


def require_keys(arguments: DataMap, required: Iterable[str], *, optional: Iterable[str] = ()) -> None:
    """Require exactly the declared argument keys."""

    required_set = set(required)
    allowed = required_set | set(optional)
    missing = required_set - arguments.keys()
    unexpected = arguments.keys() - allowed
    if missing:
        raise ValueError(f"Missing arguments: {', '.join(sorted(missing))}")
    if unexpected:
        raise ValueError(f"Unexpected arguments: {', '.join(sorted(unexpected))}")


def string_value(arguments: DataMap, key: str) -> str:
    value = arguments[key]
    if not isinstance(value, str):
        raise TypeError(f"Argument {key!r} must be a string")
    return value


def non_empty_string_value(arguments: DataMap, key: str) -> str:
    value = string_value(arguments, key)
    if not value.strip():
        raise ValueError(f"Argument {key!r} must not be empty")
    return value


def optional_string_value(arguments: DataMap, key: str) -> str | None:
    value = arguments[key]
    if value is not None and not isinstance(value, str):
        raise TypeError(f"Argument {key!r} must be a string or null")
    return value


def bool_value(arguments: DataMap, key: str) -> bool:
    value = arguments[key]
    if not isinstance(value, bool):
        raise TypeError(f"Argument {key!r} must be a boolean")
    return value


def int_value(arguments: DataMap, key: str) -> int:
    value = arguments[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Argument {key!r} must be an integer")
    return value


def number_value(arguments: DataMap, key: str) -> float:
    value = arguments[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Argument {key!r} must be a number")
    return float(value)


def map_value(arguments: DataMap, key: str) -> DataMap:
    value = arguments[key]
    if not isinstance(value, dict):
        raise TypeError(f"Argument {key!r} must be a map")
    return value


def data_value(arguments: DataMap, key: str) -> DataValue:
    return arguments[key]


def runtime_action_from_data(arguments: DataMap) -> RuntimeAction:
    """Decode a native-data runtime action."""

    require_keys(arguments, ("action", "arguments"))
    return RuntimeAction(
        action=string_value(arguments, "action"),
        arguments=map_value(arguments, "arguments"),
    )


def string_set_value(arguments: DataMap, key: str) -> frozenset[str]:
    """Decode a list of unique strings as an immutable set."""

    value = arguments[key]
    if not isinstance(value, list):
        raise TypeError(f"Argument {key!r} must be a list")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"Argument {key!r} must contain only strings")
    return frozenset(item for item in value if isinstance(item, str))
