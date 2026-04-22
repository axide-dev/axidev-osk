from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyDisplay:
    label: str
    secondary_label: str | None = None
    requires_modifiers: frozenset[str] = frozenset()
    excludes_modifiers: frozenset[str] = frozenset()


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
    display_variants: tuple[KeyDisplay, ...] = ()

    def resolve_display(self, active_modifiers: frozenset[str]) -> KeyDisplay:
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
