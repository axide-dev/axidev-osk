from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyboardMetrics:
    key_unit_px: int = 48
    grid_gap_px: int = 4

    def span_width(self, units: float) -> int:
        return max(self.key_unit_px, round(self.key_unit_px * units))

    def span_height(self, units: int) -> int:
        return (self.key_unit_px * units) + (self.grid_gap_px * (units - 1))


DEFAULT_KEYBOARD_METRICS = KeyboardMetrics()
