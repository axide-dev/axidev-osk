"""Visual layout DTOs shared by config builders and components."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KeyDisplay:
    """Resolved key text selected by active runtime state tags."""

    label: str
    secondary_label: str | None = None
    requires_state_tags: frozenset[str] = frozenset()
    excludes_state_tags: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class KeyVisual:
    """Visual text and grid placement for one key component."""

    label: str
    row: int
    column: int
    width: float = 1.0
    height: int = 1
    secondary_label: str | None = None
    display_variants: tuple[KeyDisplay, ...] = ()

    def resolve_display(self, active_state_tags: frozenset[str]) -> KeyDisplay:
        """Return the most specific display variant for active state tags."""

        best_match: KeyDisplay | None = None
        best_specificity = -1
        for variant in self.display_variants:
            if not variant.requires_state_tags.issubset(active_state_tags):
                continue
            if variant.excludes_state_tags & active_state_tags:
                continue
            specificity = len(variant.requires_state_tags) + len(variant.excludes_state_tags)
            if specificity > best_specificity:
                best_match = variant
                best_specificity = specificity

        if best_match is not None:
            return best_match
        return KeyDisplay(label=self.label, secondary_label=self.secondary_label)


@dataclass(frozen=True, slots=True)
class SpacerVisual:
    """Grid placement for one non-interactive spacer component."""

    row: int
    column: int
    width: float = 1.0
    height: int = 1
