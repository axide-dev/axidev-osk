"""Pixel metrics shared by keyboard grid components.

Pure data: a single dataclass plus a default instance reused across the
keyboard grid and its key buttons. Centralizing this here keeps cell sizing
consistent without coupling buttons and grids to one another.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyboardMetrics:
    """Pixel-level dimensions for keyboard grid cells.

    Attributes:
        key_unit_px: Edge length of a single 1u key cell, in pixels.
        grid_gap_px: Gap between adjacent cells, in pixels. Used when a
            key spans multiple rows so the spanned cells visually merge.
    """

    key_unit_px: int = 48
    grid_gap_px: int = 4

    def span_width(self, units: float) -> int:
        """Compute pixel width for a key spanning ``units`` columns.

        Args:
            units: Width in keyboard units (e.g. ``1.0``, ``1.5``, ``2.25``).

        Returns:
            Pixel width, never less than ``key_unit_px``.

        Side effects:
            None.
        """

        return max(self.key_unit_px, round(self.key_unit_px * units))

    def span_height(self, units: int) -> int:
        """Compute pixel height for a key spanning ``units`` rows.

        Args:
            units: Integer number of rows spanned (>= 1).

        Returns:
            Pixel height including inter-row gaps so the spanned region
            aligns flush with the surrounding grid.

        Side effects:
            None.
        """

        return (self.key_unit_px * units) + (self.grid_gap_px * (units - 1))


DEFAULT_KEYBOARD_METRICS = KeyboardMetrics()
