"""Keyboard layout DTOs shared by config builders and runtime components."""

from __future__ import annotations

from dataclasses import dataclass

from .messages import DataMap, DataValue, RuntimeAction, runtime_action_to_data


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
        action: Optional window action used instead of keyboard output.
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
    action: RuntimeAction | None = None

    def __post_init__(self) -> None:
        """Reject action keys with conflicting keyboard behavior."""

        if self.action is None:
            return
        if self.is_spacer:
            raise ValueError("Action keys cannot be spacers")
        if self.io_key is not None or self.key_id is not None or self.latchable or self.holds_when_latched:
            raise ValueError("Action keys cannot define keyboard output or latch behavior")
        if self.repeats:
            raise ValueError("Action keys cannot repeat")

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


def key_spec_to_data(spec: KeySpec) -> DataMap:
    """Encode a key specification as queue-safe native data."""

    display_variants: list[DataValue] = []
    for variant in spec.display_variants:
        required_modifiers: list[DataValue] = []
        required_modifiers.extend(sorted(variant.requires_modifiers))
        excluded_modifiers: list[DataValue] = []
        excluded_modifiers.extend(sorted(variant.excludes_modifiers))
        display_variant: DataMap = {
            "label": variant.label,
            "secondary_label": variant.secondary_label,
            "requires_modifiers": required_modifiers,
            "excludes_modifiers": excluded_modifiers,
        }
        display_variants.append(display_variant)
    action_data: DataMap | None = None
    if spec.action is not None:
        action_data = runtime_action_to_data(spec.action)
    data: DataMap = {
        "label": spec.label,
        "row": spec.row,
        "column": spec.column,
        "width": spec.width,
        "height": spec.height,
        "is_spacer": spec.is_spacer,
        "secondary_label": spec.secondary_label,
        "key_id": spec.key_id,
        "latchable": spec.latchable,
        "io_key": spec.io_key,
        "holds_when_latched": spec.holds_when_latched,
        "honors_latched_modifiers": spec.honors_latched_modifiers,
        "repeats": spec.repeats,
        "display_variants": display_variants,
        "action": action_data,
    }
    return data
