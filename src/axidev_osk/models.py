from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeySpec:
    label: str
    row: int
    column: int
    width: float = 1.0
    height: int = 1
    secondary_label: str | None = None
    key_id: str | None = None
    latchable: bool = False
    io_key: str | None = None
    latched_io_key: str | None = None
    holds_when_latched: bool = False
    honors_latched_modifiers: bool = True
