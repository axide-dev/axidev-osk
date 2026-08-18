"""Keyboard layout DTOs shared by config builders and runtime components."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyDisplay:
    """Resolved display text for a key under a modifier state.

    Attributes:
        label: Primary label shown on the key.
        secondary_label: Optional secondary label shown with the primary label.
        requires_modifiers: Modifier IDs that must be active for this display to apply.
        excludes_modifiers: Modifier IDs that must be inactive for this display to apply.
    """

    label: str
    secondary_label: str | None = None
    requires_modifiers: frozenset[str] = frozenset()
    excludes_modifiers: frozenset[str] = frozenset()


@dataclass(frozen=True)
class KeySpec:
    """Declarative keyboard key or spacer geometry and behavior.

    Attributes:
        label: Primary default label.
        row: Sparse layout row.
        column: Sparse layout column.
        width: Width in keyboard units.
        height: Height in keyboard rows.
        is_spacer: Whether this spec reserves space without creating a key widget.
        secondary_label: Optional default secondary label.
        key_id: Logical key identity used for shared state.
        latchable: Whether this key can stay logically active after release.
        io_key: Backend key name emitted for normal presses.
        holds_when_latched: Whether the backend key should stay held while latched.
        honors_latched_modifiers: Whether display resolution should account for active latches.
        repeats: Whether holding this key should produce repeat events.
        display_variants: Modifier-aware display alternatives.
    """

    label: str
    row: int
    column: int
    width: float = 1.0
    height: int = 1
    is_spacer: bool = False
    secondary_label: str | None = None
    key_id: str | None = None
    latchable: bool = False
    io_key: str | None = None
    holds_when_latched: bool = False
    honors_latched_modifiers: bool = True
    repeats: bool = True
    display_variants: tuple[KeyDisplay, ...] = ()

    def resolve_display(self, active_modifiers: frozenset[str]) -> KeyDisplay:
        """Return the most specific display variant for active modifier IDs."""

        best_match: KeyDisplay | None = None
        best_specificity = -1

        for variant in self.display_variants:
            if not variant.requires_modifiers.issubset(active_modifiers):
                continue
            if variant.excludes_modifiers & active_modifiers:
                continue

            specificity = len(variant.requires_modifiers) + len(variant.excludes_modifiers)
            if specificity > best_specificity:
                best_match = variant
                best_specificity = specificity

        if best_match is not None:
            return best_match

        return KeyDisplay(label=self.label, secondary_label=self.secondary_label)
