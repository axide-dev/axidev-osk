"""Bundled US ISO visual layout and its separate behavior catalog."""

from __future__ import annotations

from ...models import KeyDisplay, KeyVisual
from ...runtime.behavior_models import KeyboardBehaviorMode, KeyboardOutput
from ...runtime.behaviors import keyboard_behavior
from ..models import BehaviorConfig, GridConfig, KeyConfig, LayoutConfig

UNIT = 4
MAIN_BLOCK_WIDTH = 60
NAV_START = 64
LAYOUT_ID = "layout:us-iso"
GRID_ID = "grid:us-iso:keyboard"

# These IDs were generated from the shipped layout. Each visual uses its ID
# directly below, while output behavior is joined through this exact-ID map.
_OUTPUT_BY_COMPONENT_ID = {
    "key-5c54ee726af74aa7": "Escape",
    "key-bdcf09da3a202e62": "F1",
    "key-fdc70245aae3410c": "F2",
    "key-ca16eda6b1891af4": "F3",
    "key-82acdc858cccdc1b": "F4",
    "key-e7eb5db66f33d248": "F5",
    "key-042972b66ec9da88": "F6",
    "key-799472e937dd282b": "F7",
    "key-be4f90c7f2b56a31": "F8",
    "key-e0502bedca3e8d2c": "F9",
    "key-7602dede35eaf26e": "F10",
    "key-4d2488576bc83769": "F11",
    "key-c98f8b8aa6abd0ac": "F12",
    "key-515671db3895067f": "PrintScreen",
    "key-d31535e62738fcdb": "ScrollLock",
    "key-56dd6f4fafb550fe": "Pause",
    "key-5749d70b98266d03": "`",
    "key-1da0a2bf04836f6f": "1",
    "key-4ad6a4ef3130e307": "2",
    "key-7f8a03f59966fd32": "3",
    "key-4259e339e7e34c6a": "4",
    "key-04bf56cecc0bfcfd": "5",
    "key-da83e7d272b40a2d": "6",
    "key-d6b44e927b612e2a": "7",
    "key-7e279f2d411d9c78": "8",
    "key-1341fbdefce5f24e": "9",
    "key-b372aa400246633e": "0",
    "key-6257b82b013c89fe": "-",
    "key-fcad4cda09d33753": "=",
    "key-fa2d3e3fb57cb334": "Backspace",
    "key-d1e2779baa751f68": "Insert",
    "key-43a9f8fba5d37497": "Home",
    "key-efb8c355bd7250c6": "PageUp",
    "key-2defdac8c250c324": "Tab",
    "key-18404b2cce96ff35": "Q",
    "key-a08f85301c8d97bd": "W",
    "key-44d947c0b66bb3fb": "E",
    "key-30ea38dd5965f55e": "R",
    "key-1594ef70ee70106f": "T",
    "key-dc8121e76f1582df": "Y",
    "key-1124a591d73619be": "U",
    "key-2b5bf05506b0f0bf": "I",
    "key-998869f839580451": "O",
    "key-136eb67434983829": "P",
    "key-d4d064bb7ee9b43e": "[",
    "key-b72cd12dae4c6310": "]",
    "key-ba8bdcd343001c8e": "Delete",
    "key-d855d8ccc4e10e16": "End",
    "key-8ba4cd7f0a6ddafc": "PageDown",
    "key-a3b9c717473feb03": "CapsLock",
    "key-57c70e7dcd3f77aa": "A",
    "key-6c34719afd75b5ba": "S",
    "key-d6e04757428495b2": "D",
    "key-fca72c22c4b5085c": "F",
    "key-b4cd3dabf6da1101": "G",
    "key-14e15477653007fa": "H",
    "key-bbbc099b70e28078": "J",
    "key-6b5a8c52a3dfe4c2": "K",
    "key-7283b50370a56b26": "L",
    "key-bd279ec10b0bb5ad": ";",
    "key-98a4191de5a08f40": "'",
    "key-7348d7fa1b425df8": "Enter",
    "key-79dd3bb91c1989ce": "ShiftLeft",
    "key-d907156057e1aa4f": "\\",
    "key-0a707c2d086c5b9e": "Z",
    "key-e2bc96e8c835c177": "X",
    "key-611579a0df6eb4fa": "C",
    "key-40e8b534df124e61": "V",
    "key-6c342e16ce323176": "B",
    "key-d9de0985f4d133e7": "N",
    "key-6c13726499dbb1b1": "M",
    "key-e47031a1301ddb73": ",",
    "key-bf34cafff7e1f9fd": ".",
    "key-97b1ba40ab436eb4": "/",
    "key-993aa770de985a17": "ShiftRight",
    "key-d6395a9121316843": "Up",
    "key-1c7aa4c8f2ad736c": "CtrlLeft",
    "key-30053be7a830def5": "SuperLeft",
    "key-855853a6e6554165": "AltLeft",
    "key-26f49093d0a0e64e": "Space",
    "key-75f932e22d8cb9e4": "AltRight",
    "key-4de28b604a2a60f7": "SuperRight",
    "key-0390554e1df20555": "Menu",
    "key-398ba92c947ae2ca": "CtrlRight",
    "key-8ec8a1a38a4c3052": "Left",
    "key-e3095d897213c4de": "Down",
    "key-ab9809958f5303c4": "Right",
}

_HELD_TOGGLE_KEYS = frozenset(
    {"ShiftLeft", "ShiftRight", "CtrlLeft", "CtrlRight", "SuperLeft", "SuperRight", "AltLeft", "AltRight"}
)


def u(value: int) -> int:
    return value * UNIT


def key(
    label: str,
    *,
    row: int,
    column: int,
    width: float = 1.0,
    height: int = 1,
    secondary_label: str | None = None,
    display_variants: tuple[KeyDisplay, ...] = (),
) -> KeyVisual:
    """Build visual-only key data."""

    return KeyVisual(
        label=label,
        row=row,
        column=column,
        width=width,
        height=height,
        secondary_label=secondary_label,
        display_variants=display_variants,
    )


def shifted_key(
    label: str,
    shifted_label: str,
    *,
    row: int,
    column: int,
    width: float = 1.0,
    height: int = 1,
) -> KeyVisual:
    return key(
        label,
        row=row,
        column=column,
        width=width,
        height=height,
        display_variants=(
            KeyDisplay(label=shifted_label, requires_state_tags=frozenset({"shift"})),
        ),
    )


def letter_key(
    label: str,
    *,
    row: int,
    column: int,
    width: float = 1.0,
    height: int = 1,
) -> KeyVisual:
    lower_label = label.lower()
    upper_label = label.upper()
    return key(
        lower_label,
        row=row,
        column=column,
        width=width,
        height=height,
        display_variants=(
            KeyDisplay(
                label=upper_label,
                requires_state_tags=frozenset({"shift"}),
                excludes_state_tags=frozenset({"caps"}),
            ),
            KeyDisplay(
                label=upper_label,
                requires_state_tags=frozenset({"caps"}),
                excludes_state_tags=frozenset({"shift"}),
            ),
        ),
    )


def _build_us_iso_components() -> tuple[KeyConfig, ...]:
    """Pair every shipped stable ID directly with its visual definition."""

    return (
        KeyConfig("key-5c54ee726af74aa7", key("Esc", row=0, column=u(0))),
        KeyConfig("key-bdcf09da3a202e62", key("F1", row=0, column=u(2))),
        KeyConfig("key-fdc70245aae3410c", key("F2", row=0, column=u(3))),
        KeyConfig("key-ca16eda6b1891af4", key("F3", row=0, column=u(4))),
        KeyConfig("key-82acdc858cccdc1b", key("F4", row=0, column=u(5))),
        KeyConfig("key-e7eb5db66f33d248", key("F5", row=0, column=u(7))),
        KeyConfig("key-042972b66ec9da88", key("F6", row=0, column=u(8))),
        KeyConfig("key-799472e937dd282b", key("F7", row=0, column=u(9))),
        KeyConfig("key-be4f90c7f2b56a31", key("F8", row=0, column=u(10))),
        KeyConfig("key-e0502bedca3e8d2c", key("F9", row=0, column=u(12))),
        KeyConfig("key-7602dede35eaf26e", key("F10", row=0, column=u(13))),
        KeyConfig("key-4d2488576bc83769", key("F11", row=0, column=u(14))),
        KeyConfig("key-c98f8b8aa6abd0ac", key("F12", row=0, column=u(15))),
        KeyConfig("key-515671db3895067f", key("PrtSc", row=0, column=NAV_START)),
        KeyConfig(
            "key-d31535e62738fcdb",
            key("ScrLk", row=0, column=NAV_START + u(1)),
        ),
        KeyConfig(
            "key-56dd6f4fafb550fe",
            key("Pause", row=0, column=NAV_START + u(2)),
        ),
        KeyConfig("key-5749d70b98266d03", shifted_key("`", "~", row=1, column=u(0))),
        KeyConfig("key-1da0a2bf04836f6f", shifted_key("1", "!", row=1, column=u(1))),
        KeyConfig("key-4ad6a4ef3130e307", shifted_key("2", "@", row=1, column=u(2))),
        KeyConfig("key-7f8a03f59966fd32", shifted_key("3", "#", row=1, column=u(3))),
        KeyConfig("key-4259e339e7e34c6a", shifted_key("4", "$", row=1, column=u(4))),
        KeyConfig("key-04bf56cecc0bfcfd", shifted_key("5", "%", row=1, column=u(5))),
        KeyConfig("key-da83e7d272b40a2d", shifted_key("6", "^", row=1, column=u(6))),
        KeyConfig("key-d6b44e927b612e2a", shifted_key("7", "&&", row=1, column=u(7))),
        KeyConfig("key-7e279f2d411d9c78", shifted_key("8", "*", row=1, column=u(8))),
        KeyConfig("key-1341fbdefce5f24e", shifted_key("9", "(", row=1, column=u(9))),
        KeyConfig("key-b372aa400246633e", shifted_key("0", ")", row=1, column=u(10))),
        KeyConfig("key-6257b82b013c89fe", shifted_key("-", "_", row=1, column=u(11))),
        KeyConfig("key-fcad4cda09d33753", shifted_key("=", "+", row=1, column=u(12))),
        KeyConfig(
            "key-fa2d3e3fb57cb334",
            key("Backspace", row=1, column=u(13), width=2.0),
        ),
        KeyConfig("key-d1e2779baa751f68", key("Ins", row=1, column=NAV_START)),
        KeyConfig(
            "key-43a9f8fba5d37497",
            key("Home", row=1, column=NAV_START + u(1)),
        ),
        KeyConfig(
            "key-efb8c355bd7250c6",
            key("PgUp", row=1, column=NAV_START + u(2)),
        ),
        KeyConfig("key-2defdac8c250c324", key("Tab", row=2, column=u(0), width=1.5)),
        KeyConfig("key-18404b2cce96ff35", letter_key("Q", row=2, column=6)),
        KeyConfig("key-a08f85301c8d97bd", letter_key("W", row=2, column=10)),
        KeyConfig("key-44d947c0b66bb3fb", letter_key("E", row=2, column=14)),
        KeyConfig("key-30ea38dd5965f55e", letter_key("R", row=2, column=18)),
        KeyConfig("key-1594ef70ee70106f", letter_key("T", row=2, column=22)),
        KeyConfig("key-dc8121e76f1582df", letter_key("Y", row=2, column=26)),
        KeyConfig("key-1124a591d73619be", letter_key("U", row=2, column=30)),
        KeyConfig("key-2b5bf05506b0f0bf", letter_key("I", row=2, column=34)),
        KeyConfig("key-998869f839580451", letter_key("O", row=2, column=38)),
        KeyConfig("key-136eb67434983829", letter_key("P", row=2, column=42)),
        KeyConfig("key-d4d064bb7ee9b43e", shifted_key("[", "{", row=2, column=46)),
        KeyConfig("key-b72cd12dae4c6310", shifted_key("]", "}", row=2, column=50)),
        KeyConfig("key-08f8b62608b6de45", key("Ghost", row=2, column=54)),
        KeyConfig("key-ba8bdcd343001c8e", key("Del", row=2, column=NAV_START)),
        KeyConfig(
            "key-d855d8ccc4e10e16",
            key("End", row=2, column=NAV_START + u(1)),
        ),
        KeyConfig(
            "key-8ba4cd7f0a6ddafc",
            key("PgDn", row=2, column=NAV_START + u(2)),
        ),
        KeyConfig(
            "key-a3b9c717473feb03",
            key("Caps", row=3, column=u(0), width=1.75),
        ),
        KeyConfig("key-57c70e7dcd3f77aa", letter_key("A", row=3, column=7)),
        KeyConfig("key-6c34719afd75b5ba", letter_key("S", row=3, column=11)),
        KeyConfig("key-d6e04757428495b2", letter_key("D", row=3, column=15)),
        KeyConfig("key-fca72c22c4b5085c", letter_key("F", row=3, column=19)),
        KeyConfig("key-b4cd3dabf6da1101", letter_key("G", row=3, column=23)),
        KeyConfig("key-14e15477653007fa", letter_key("H", row=3, column=27)),
        KeyConfig("key-bbbc099b70e28078", letter_key("J", row=3, column=31)),
        KeyConfig("key-6b5a8c52a3dfe4c2", letter_key("K", row=3, column=35)),
        KeyConfig("key-7283b50370a56b26", letter_key("L", row=3, column=39)),
        KeyConfig("key-bd279ec10b0bb5ad", shifted_key(";", ":", row=3, column=43)),
        KeyConfig("key-98a4191de5a08f40", shifted_key("'", '"', row=3, column=47)),
        KeyConfig("key-7348d7fa1b425df8", key("Enter", row=3, column=51, width=2.25)),
        KeyConfig("key-79dd3bb91c1989ce", key("Shift", row=4, column=u(0), width=1.25)),
        KeyConfig("key-d907156057e1aa4f", shifted_key("\\", "|", row=4, column=5)),
        KeyConfig("key-0a707c2d086c5b9e", letter_key("Z", row=4, column=9)),
        KeyConfig("key-e2bc96e8c835c177", letter_key("X", row=4, column=13)),
        KeyConfig("key-611579a0df6eb4fa", letter_key("C", row=4, column=17)),
        KeyConfig("key-40e8b534df124e61", letter_key("V", row=4, column=21)),
        KeyConfig("key-6c342e16ce323176", letter_key("B", row=4, column=25)),
        KeyConfig("key-d9de0985f4d133e7", letter_key("N", row=4, column=29)),
        KeyConfig("key-6c13726499dbb1b1", letter_key("M", row=4, column=33)),
        KeyConfig("key-e47031a1301ddb73", shifted_key(",", "<", row=4, column=37)),
        KeyConfig("key-bf34cafff7e1f9fd", shifted_key(".", ">", row=4, column=41)),
        KeyConfig("key-97b1ba40ab436eb4", shifted_key("/", "?", row=4, column=45)),
        KeyConfig("key-993aa770de985a17", key("Shift", row=4, column=49, width=2.75)),
        KeyConfig(
            "key-d6395a9121316843",
            key("↑", row=4, column=NAV_START + u(1)),
        ),
        KeyConfig("key-1c7aa4c8f2ad736c", key("Ctrl", row=5, column=u(0), width=1.25)),
        KeyConfig("key-30053be7a830def5", key("Super", row=5, column=5, width=1.25)),
        KeyConfig("key-855853a6e6554165", key("Alt", row=5, column=10, width=1.25)),
        KeyConfig("key-26f49093d0a0e64e", key("Space", row=5, column=15, width=6.25)),
        KeyConfig("key-75f932e22d8cb9e4", key("AltGr", row=5, column=40, width=1.25)),
        KeyConfig("key-4de28b604a2a60f7", key("Super", row=5, column=45, width=1.25)),
        KeyConfig("key-0390554e1df20555", key("Menu", row=5, column=50, width=1.25)),
        KeyConfig("key-398ba92c947ae2ca", key("Ctrl", row=5, column=55, width=1.25)),
        KeyConfig("key-8ec8a1a38a4c3052", key("←", row=5, column=NAV_START)),
        KeyConfig(
            "key-e3095d897213c4de",
            key("↓", row=5, column=NAV_START + u(1)),
        ),
        KeyConfig(
            "key-ab9809958f5303c4",
            key("→", row=5, column=NAV_START + u(2)),
        ),
    )


def build_us_iso_layout() -> list[KeyVisual]:
    """Return the bundled US ISO visual layout in display order."""

    return [component.visual for component in _build_us_iso_components()]


def build_us_iso_layout_config() -> LayoutConfig:
    components = _build_us_iso_components()
    return LayoutConfig(
        id=LAYOUT_ID,
        name="us-iso",
        grids=(GridConfig(id=GRID_ID, components=components, nav_start_column=NAV_START),),
    )


def build_us_iso_behavior_configs() -> dict[str, BehaviorConfig]:
    """Return keyboard behavior by explicit component ID; Ghost is excluded."""

    component_ids = {component.id for component in _build_us_iso_components()}
    unknown_ids = _OUTPUT_BY_COMPONENT_ID.keys() - component_ids
    if unknown_ids:
        raise ValueError(f"US ISO outputs target unknown component IDs: {sorted(unknown_ids)}")
    behaviors: dict[str, BehaviorConfig] = {}
    for component_id, output_key in _OUTPUT_BY_COMPONENT_ID.items():
        mode = KeyboardBehaviorMode.MOMENTARY
        uses_active_state_tags = True
        if output_key == "CapsLock":
            mode = KeyboardBehaviorMode.LOGICAL_TOGGLE
            uses_active_state_tags = False
        elif output_key in _HELD_TOGGLE_KEYS:
            mode = KeyboardBehaviorMode.HELD_TOGGLE
            uses_active_state_tags = False
        behaviors[component_id] = keyboard_behavior(
            mode,
            KeyboardOutput(
                output_key=output_key,
                repeats=True,
                uses_active_state_tags=uses_active_state_tags,
            ),
        )
    return behaviors
