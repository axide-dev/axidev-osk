"""Small native-data decoders used by registered runtime messages."""

from __future__ import annotations

from collections.abc import Iterable

from ..messages import DataMap, DataValue, RuntimeAction
from ..models import KeyDisplay, KeySpec


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


def key_spec_from_data(arguments: DataMap) -> KeySpec:
    """Decode a native-data key specification."""

    require_keys(
        arguments,
        (
            "label",
            "row",
            "column",
            "width",
            "height",
            "is_spacer",
            "secondary_label",
            "key_id",
            "latchable",
            "io_key",
            "holds_when_latched",
            "honors_latched_modifiers",
            "repeats",
            "display_variants",
            "action",
        ),
    )
    variants_value = arguments["display_variants"]
    if not isinstance(variants_value, list):
        raise TypeError("Argument 'display_variants' must be a list")
    variants: list[KeyDisplay] = []
    for index, value in enumerate(variants_value):
        if not isinstance(value, dict):
            raise TypeError(f"Display variant {index} must be a map")
        require_keys(
            value,
            ("label", "secondary_label", "requires_modifiers", "excludes_modifiers"),
        )
        required = _string_set(value, "requires_modifiers")
        excluded = _string_set(value, "excludes_modifiers")
        variants.append(
            KeyDisplay(
                label=string_value(value, "label"),
                secondary_label=optional_string_value(value, "secondary_label"),
                requires_modifiers=required,
                excludes_modifiers=excluded,
            )
        )

    action_value = arguments["action"]
    action: RuntimeAction | None = None
    if action_value is not None:
        if not isinstance(action_value, dict):
            raise TypeError("Argument 'action' must be a map or null")
        action = runtime_action_from_data(action_value)

    return KeySpec(
        label=string_value(arguments, "label"),
        row=int_value(arguments, "row"),
        column=int_value(arguments, "column"),
        width=number_value(arguments, "width"),
        height=int_value(arguments, "height"),
        is_spacer=bool_value(arguments, "is_spacer"),
        secondary_label=optional_string_value(arguments, "secondary_label"),
        key_id=optional_string_value(arguments, "key_id"),
        latchable=bool_value(arguments, "latchable"),
        io_key=optional_string_value(arguments, "io_key"),
        holds_when_latched=bool_value(arguments, "holds_when_latched"),
        honors_latched_modifiers=bool_value(arguments, "honors_latched_modifiers"),
        repeats=bool_value(arguments, "repeats"),
        display_variants=tuple(variants),
        action=action,
    )


def _string_set(arguments: DataMap, key: str) -> frozenset[str]:
    value = arguments[key]
    if not isinstance(value, list):
        raise TypeError(f"Argument {key!r} must be a list")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"Argument {key!r} must contain only strings")
    return frozenset(item for item in value if isinstance(item, str))
