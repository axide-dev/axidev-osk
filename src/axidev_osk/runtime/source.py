"""Structured runtime source paths used by events, behavior, and state."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..messages import DataMap, DataValue
from .decoding import non_empty_string_value


@dataclass(frozen=True, slots=True)
class SourcePathSegment:
    """One typed identity segment in a runtime source path."""

    kind: str
    id: str

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("Source path segment kind cannot be empty")
        if not self.id:
            raise ValueError("Source path segment ID cannot be empty")


@dataclass(frozen=True, slots=True)
class SourcePath:
    """Ordered address of a configured runtime node."""

    segments: tuple[SourcePathSegment, ...]

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("Source path cannot be empty")

    def child(self, kind: str, source_id: str) -> "SourcePath":
        return SourcePath((*self.segments, SourcePathSegment(kind, source_id)))

    def through(self, kind: str) -> "SourcePath":
        """Return this path through its last segment of ``kind``."""

        for index in range(len(self.segments) - 1, -1, -1):
            if self.segments[index].kind == kind:
                return SourcePath(self.segments[: index + 1])
        raise ValueError(f"Source path has no {kind!r} segment")


def source_path_to_data(path: SourcePath) -> list[DataValue]:
    """Encode a source path as queue-safe native data."""

    return [{"kind": segment.kind, "id": segment.id} for segment in path.segments]


def source_path_from_data(value: DataValue) -> SourcePath:
    """Decode a source path from queue-safe native data."""

    if not isinstance(value, list):
        raise TypeError("Source path must be a list")
    segments: list[SourcePathSegment] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise TypeError(f"Source path segment {index} must be a map")
        if set(item) != {"kind", "id"}:
            raise ValueError(f"Source path segment {index} must contain exactly 'kind' and 'id'")
        data: DataMap = item
        segments.append(
            SourcePathSegment(
                kind=non_empty_string_value(data, "kind"),
                id=non_empty_string_value(data, "id"),
            )
        )
    return SourcePath(tuple(segments))


def source_state_namespace(path: SourcePath) -> str:
    """Return the central-state namespace for a source path."""

    encoded = json.dumps(
        source_path_to_data(path),
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"source:{encoded}"
