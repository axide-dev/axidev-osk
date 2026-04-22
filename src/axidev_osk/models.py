from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeySpec:
    label: str
    width: float = 1.0
    secondary_label: str | None = None
    key_id: str | None = None
    latchable: bool = False
