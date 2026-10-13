"""Declared state variables: their types, defaults, and the paths inside them.

A profile declares every state variable it uses in place inside a nested
``state`` map, as plain data a Lua table can produce:

    {"settings": {"dwell_delay": {"var": "integer", "default": 200}}}

A type is one of ``"boolean"``, ``"integer"``, ``"number"``, ``"string"``,
``{"list": T}``, ``{"map": T}``, or ``{"record": {field: declaration}}``. A
scalar needs a ``default``; a list or map defaults to empty, and a record takes
its default from its fields' declarations. The engine stores these values and
checks them against their type, but it never knows what they mean.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias

from ..messages import DataMap, DataValue, copy_data_value

StatePath: TypeAlias = tuple[str, ...]

SCALARS = frozenset({"boolean", "integer", "number", "string"})


class VariableError(ValueError):
    """A declaration is malformed, or a value does not fit its declared type."""


@dataclass(frozen=True, slots=True)
class Scalar:
    name: str


@dataclass(frozen=True, slots=True)
class ListOf:
    item: "VarType"


@dataclass(frozen=True, slots=True)
class MapOf:
    item: "VarType"


@dataclass(frozen=True, slots=True)
class Record:
    fields: Mapping[str, "Variable"]


VarType: TypeAlias = Scalar | ListOf | MapOf | Record


@dataclass(frozen=True, slots=True)
class Variable:
    """One declared variable: its type and the value ``None`` resets it to."""

    type: VarType
    default: DataValue


def path_text(path: StatePath) -> str:
    return ".".join(path)


def is_declaration(value: object) -> bool:
    """Whether a map in a ``state`` tree declares a variable rather than grouping others."""

    return isinstance(value, Mapping) and "var" in value


def decode_state(data: object, path: str) -> dict[StatePath, Variable]:
    """Read a nested ``state`` map into its declared variables, keyed by state path."""

    if not isinstance(data, Mapping):
        raise VariableError(f"{path} must be a map")
    declared: dict[StatePath, Variable] = {}
    _collect(data, (), path, declared)
    return declared


def _collect(data: Mapping[object, object], prefix: StatePath, path: str, declared: dict[StatePath, Variable]) -> None:
    for name, value in data.items():
        if not isinstance(name, str) or not name:
            raise VariableError(f"{path} keys must be non-empty strings")
        if value is None:
            continue
        child_path = f"{path}.{name}"
        if is_declaration(value):
            declared[(*prefix, name)] = decode_variable(value, child_path)
        elif isinstance(value, Mapping):
            _collect(value, (*prefix, name), child_path, declared)
        else:
            raise VariableError(f"{child_path} must be a variable declaration (axidev_osk.var) or a map of them")


def decode_variable(data: object, path: str) -> Variable:
    """Read one ``{"var": type, "default": value}`` declaration."""

    if not isinstance(data, Mapping):
        raise VariableError(f"{path} must be a variable declaration")
    unknown = sorted(str(key) for key, value in data.items() if key not in {"var", "default"} and value is not None)
    if unknown:
        raise VariableError(f"{path} has unknown keys: {', '.join(unknown)}")
    var_type = decode_type(data.get("var"), f"{path}.var")
    raw_default = data.get("default")
    if isinstance(var_type, Record):
        if raw_default is not None:
            raise VariableError(f"{path}.default cannot be set on a record; its fields carry their defaults")
        return Variable(var_type, record_default(var_type))
    if raw_default is None:
        if isinstance(var_type, Scalar):
            raise VariableError(f"{path}.default is required for a {var_type.name}")
        raw_default = [] if isinstance(var_type, ListOf) else {}
    return Variable(var_type, check(var_type, raw_default, f"{path}.default"))


def decode_type(data: object, path: str) -> VarType:
    if isinstance(data, str):
        if data not in SCALARS:
            raise VariableError(f"{path} must be one of {', '.join(sorted(SCALARS))}, a list, a map, or a record")
        return Scalar(data)
    if isinstance(data, Mapping) and len(data) == 1:
        ((form, inner),) = data.items()
        if form == "list":
            return ListOf(decode_type(inner, f"{path}.list"))
        if form == "map":
            return MapOf(decode_type(inner, f"{path}.map"))
        if form == "record":
            if not isinstance(inner, Mapping) or not inner:
                raise VariableError(f"{path}.record must be a non-empty map of field declarations")
            fields: dict[str, Variable] = {}
            for name, field_data in inner.items():
                if not isinstance(name, str) or not name:
                    raise VariableError(f"{path}.record keys must be non-empty strings")
                fields[name] = decode_variable(field_data, f"{path}.record.{name}")
            return Record(fields)
    raise VariableError(f"{path} must be a type: a scalar name, {{list = T}}, {{map = T}}, or {{record = {{...}}}}")


def record_default(record: Record) -> DataMap:
    return {name: copy_data_value(field.default) for name, field in record.fields.items()}


def check(var_type: VarType, value: object, path: str) -> DataValue:
    """Return a stored copy of ``value`` when it fits ``var_type``; raise ``VariableError`` otherwise."""

    if isinstance(var_type, Scalar):
        if not _scalar_fits(var_type.name, value):
            raise VariableError(f"{path} must be a {var_type.name}, got {_describe(value)}")
        return value  # type: ignore[return-value]
    if isinstance(var_type, ListOf):
        if not isinstance(value, list):
            raise VariableError(f"{path} must be a list, got {_describe(value)}")
        return [check(var_type.item, item, f"{path}[{index}]") for index, item in enumerate(value)]
    if not isinstance(value, Mapping):
        raise VariableError(f"{path} must be a map, got {_describe(value)}")
    if isinstance(var_type, MapOf):
        entries: DataMap = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise VariableError(f"{path} keys must be non-empty strings")
            if item is not None:
                entries[key] = check(var_type.item, item, f"{path}.{key}")
        return entries
    unknown = sorted(str(key) for key in value if key not in var_type.fields)
    if unknown:
        raise VariableError(f"{path} has unknown fields: {', '.join(unknown)}")
    return {
        name: check(field.type, value[name], f"{path}.{name}") if value.get(name) is not None else copy_data_value(field.default)
        for name, field in var_type.fields.items()
    }


def _scalar_fits(name: str, value: object) -> bool:
    if name == "boolean":
        return isinstance(value, bool)
    if name == "string":
        return isinstance(value, str)
    if isinstance(value, bool):
        return False
    if name == "integer":
        return isinstance(value, int)
    return isinstance(value, (int, float)) and math.isfinite(value)


def _describe(value: object) -> str:
    return "nothing" if value is None else type(value).__name__


@dataclass(frozen=True, slots=True)
class Slot:
    """Where a path lands inside a declared variable.

    ``variable`` is the declared path. ``type`` is the type at the slot.
    ``default`` is what ``None`` resets the slot to, or ``None`` when the slot is
    a map entry, which ``None`` removes instead.
    """

    variable: StatePath
    type: VarType
    default: DataValue


def descend(variable_path: StatePath, variable: Variable, rest: StatePath) -> Slot:
    """Follow ``rest`` into map entries and record fields of one variable."""

    var_type: VarType = variable.type
    default: DataValue = variable.default
    walked = variable_path
    for segment in rest:
        if isinstance(var_type, MapOf):
            var_type, default = var_type.item, None
        elif isinstance(var_type, Record):
            field = var_type.fields.get(segment)
            if field is None:
                raise VariableError(f"{path_text((*walked, segment))} is not a field of the record {path_text(walked)}")
            var_type, default = field.type, field.default
        else:
            raise VariableError(f"{path_text((*walked, segment))} is undeclared: {path_text(walked)} has no entries")
        walked = (*walked, segment)
    return Slot(variable_path, var_type, default)


def empty_value(var_type: VarType) -> DataValue:
    """The value a new map entry starts from before one of its fields is set."""

    if isinstance(var_type, Record):
        return record_default(var_type)
    if isinstance(var_type, MapOf):
        return {}
    return None
