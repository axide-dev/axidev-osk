"""Which values each field of an event's argument record can take.

An event's argument record marks each field that is not a plain boolean:
``profile_window`` for a window the profile defines, ``profile_node`` for one of its
nodes, ``one_of`` for a closed set of values, and ``stand_in`` for an open set
(free text, numbers, key names) that a few representative values stand in for.
A field typed ``X | None`` also takes ``None``. ``key`` names the argument when
the record's field name differs from it, as ``window_id`` reads ``window``.

The config check reads these marks to build every event a profile handler can
receive, so it can call the handler with each of them.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from dataclasses import Field, field, fields, is_dataclass
from typing import Any

from ..messages import DataMap, DataValue, copy_data_value

_VALUES = "axidev_osk.values"
_KEY = "axidev_osk.key"
_WINDOW = "window"
_NODE = "node"


class EventFieldError(TypeError):
    """An event's argument record has a field whose values are not marked."""


def profile_window(*, key: str | None = None) -> Any:
    """A field naming one of the profile's windows."""

    return field(metadata={_VALUES: _WINDOW, _KEY: key})


def profile_node(*, key: str | None = None) -> Any:
    """A field naming one of the profile's nodes."""

    return field(metadata={_VALUES: _NODE, _KEY: key})


def one_of(*values: DataValue, key: str | None = None) -> Any:
    """A field holding one of exactly these values."""

    return field(metadata={_VALUES: tuple(values), _KEY: key})


def stand_in(*values: DataValue, key: str | None = None) -> Any:
    """A field from an open set of values, which these representative values stand in for."""

    return field(metadata={_VALUES: tuple(values), _KEY: key})


def event_samples(
    decoder: Callable[[DataMap], object],
    *,
    windows: Sequence[str],
    nodes: Sequence[str],
) -> list[DataMap]:
    """Every combination of marked field values of the record ``decoder`` returns, as event arguments.

    Raises ``EventFieldError`` when the decoder does not name a dataclass
    record, or a field that is not a boolean carries no mark.
    """

    record = _returned_record(decoder)
    keys: list[str] = []
    choices: list[list[DataValue]] = []
    for item in fields(record):
        keys.append(item.metadata.get(_KEY) or item.name)
        choices.append(_field_values(record, item, windows, nodes))
    return [
        {key: copy_data_value(value) for key, value in zip(keys, combination)}
        for combination in itertools.product(*choices)
    ]


def _returned_record(decoder: Callable[[DataMap], object]) -> type:
    """The argument record a decoder's return annotation names."""

    annotation = getattr(decoder, "__annotations__", {}).get("return")
    if isinstance(annotation, str):
        annotation = getattr(decoder, "__globals__", {}).get(annotation)
    if not isinstance(annotation, type) or not is_dataclass(annotation):
        raise EventFieldError(f"{getattr(decoder, '__name__', decoder)!r} does not return an argument record")
    return annotation


def _field_values(
    record: type,
    item: Field[Any],
    windows: Sequence[str],
    nodes: Sequence[str],
) -> list[DataValue]:
    # Records are declared with postponed annotations, so a field's type is read from its text.
    parts = [part.strip() for part in (item.type if isinstance(item.type, str) else getattr(item.type, "__name__", "")).split("|")]
    optional = "None" in parts
    base = [part for part in parts if part != "None"]
    marked = item.metadata.get(_VALUES)
    if marked == _WINDOW:
        values: list[DataValue] = list(windows)
    elif marked == _NODE:
        values = list(nodes)
    elif isinstance(marked, tuple):
        values = list(marked)
    elif base == ["bool"]:
        values = [False, True]
    else:
        raise EventFieldError(f"{record.__name__}.{item.name} does not mark which values it takes")
    if optional and None not in values:
        values.append(None)
    return values
