"""Serializable configuration DTOs for windows, surfaces, grids, and components."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from ..models import KeySpec


class OverlayPlacement(str, Enum):
    """Placement preset for an overlay-backed window."""

    CENTER = "center"
    TOP_RIGHT = "top-right"


@dataclass(slots=True)
class AlwaysOnTopWindowConfig:
    """Platform-agnostic overlay placement policy.

    Attributes:
        placement: Preset describing where the overlay should be anchored.
        screen_margin: Pixel margin from the chosen screen edge.
        manage_position: Whether the overlay controller should keep the
            window placed; ``False`` lets the host owner manage geometry.
    """

    placement: OverlayPlacement = OverlayPlacement.TOP_RIGHT
    screen_margin: int = 16
    manage_position: bool = True


@dataclass(frozen=True, slots=True)
class OverlayConfig:
    """Overlay behavior for a window.

    Attributes:
        always_on_top: Whether the window should use the overlay backend.
        config: Platform-aware overlay placement and sizing policy.
    """

    always_on_top: bool = True
    config: AlwaysOnTopWindowConfig = field(default_factory=AlwaysOnTopWindowConfig)


@dataclass(frozen=True, slots=True)
class ChromeConfig:
    """Optional custom window chrome requested by a window config.

    Attributes:
        enabled: Whether custom chrome may be installed when the overlay backend needs it.
    """

    enabled: bool = True



@dataclass(frozen=True, slots=True)
class KeyConfig:
    """Declarative key component placement and behavior.

    Attributes:
        id: Deterministic component ID used by events, state, and Qt properties.
        spec: Keyboard key semantics and grid placement inherited from the prototype model.
    """

    id: str
    spec: KeySpec
    kind: Literal["key"] = "key"


@dataclass(frozen=True, slots=True)
class SpacerConfig:
    """Declarative spacer component used to reserve grid cells.

    Attributes:
        id: Deterministic component ID used by validation and Qt properties.
        spec: Spacer geometry stored in the same unit system as keys.
    """

    id: str
    spec: KeySpec
    kind: Literal["spacer"] = "spacer"


@dataclass(frozen=True, slots=True)
class ButtonConfig:
    """Declarative push-button component for prompt actions.

    Attributes:
        id: Deterministic component ID used by events and Qt properties.
        label: Visible text shown on the button.
        role: Semantic action emitted by the button.
        object_name: Optional Qt object name for existing QSS/tests.
        style_sheet: Optional local stylesheet for prompt buttons.
    """

    id: str
    label: str
    role: str
    object_name: str | None = None
    style_sheet: str | None = None
    kind: Literal["button"] = "button"


@dataclass(frozen=True, slots=True)
class GridConfig:
    """Declarative grid containing keys or other grid-positioned components.

    Attributes:
        id: Deterministic grid ID.
        components: Components placed inside the grid.
        nav_start_column: Sparse-column start for the navigation block in US ISO data.
        body_row_count: Number of keyboard rows that should receive stretch.
    """

    id: str
    components: tuple[KeyConfig | SpacerConfig, ...]
    nav_start_column: int
    body_row_count: int = 6


@dataclass(frozen=True, slots=True)
class LayoutConfig:
    """Declarative layout composed from one or more grids.

    Attributes:
        id: Deterministic layout ID.
        name: Stable layout name suitable for future config selection.
        grids: Grid DTOs instantiated by component builders.
    """

    id: str
    name: str
    grids: tuple[GridConfig, ...]


@dataclass(frozen=True, slots=True)
class PromptConfig:
    """Declarative prompt component for confirmation windows.

    Attributes:
        id: Deterministic prompt component ID.
        message: Primary prompt text.
        buttons: Prompt action buttons.
        prompt_glyph: Badge glyph displayed beside the message.
        hint: Optional secondary explanatory copy.
        danger: Whether the prompt should use danger styling.
    """

    id: str
    message: str
    buttons: tuple[ButtonConfig, ...]
    prompt_glyph: str = "!"
    hint: str | None = None
    danger: bool = False
    kind: Literal["prompt"] = "prompt"


@dataclass(frozen=True, slots=True)
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
        """Return pixel width for a key spanning ``units`` columns."""

        return max(self.key_unit_px, round(self.key_unit_px * units))

    def span_height(self, units: int) -> int:
        """Return pixel height for a key spanning ``units`` rows including gaps."""

        return (self.key_unit_px * units) + (self.grid_gap_px * (units - 1))


@dataclass(frozen=True, slots=True)
class KeyboardGridConfig:
    """Declarative keyboard grid component.

    Attributes:
        id: Deterministic component ID.
        layout: Keyboard layout data used by the grid component.
        metrics: Pixel metrics applied to keys in this grid.
    """

    id: str
    layout: LayoutConfig
    metrics: KeyboardMetrics = field(default_factory=KeyboardMetrics)
    kind: Literal["keyboard-grid"] = "keyboard-grid"


@dataclass(frozen=True, slots=True)
class KeyboardStatusConfig:
    """Declarative keyboard backend status component.

    Attributes:
        id: Deterministic component ID.
    """

    id: str
    kind: Literal["keyboard-status"] = "keyboard-status"


ComponentConfig = KeyConfig | SpacerConfig | ButtonConfig | PromptConfig | KeyboardGridConfig | KeyboardStatusConfig


@dataclass(frozen=True, slots=True)
class SurfaceConfig:
    """Generic root content surface hosted by a window.

    Attributes:
        id: Deterministic surface ID.
        kind: Surface builder key.
        components: Child components mounted into the surface.
        margins: Qt layout margins in pixels ordered left, top, right, bottom.
        spacing: Qt layout spacing in pixels.
        minimum_size: Optional lower bound for startup size as ``(width, height)``.
    """

    id: str
    components: tuple[ComponentConfig, ...]
    kind: Literal["surface"] = "surface"
    margins: tuple[int, int, int, int] = (10, 10, 10, 10)
    spacing: int = 8
    minimum_size: tuple[int, int] = (0, 0)


@dataclass(frozen=True, slots=True)
class WindowConfig:
    """Window declaration consumed by the generic window builder.

    Attributes:
        id: Deterministic window ID used by the window manager.
        title: User-visible window title.
        surface: Root surface content declaration.
        overlay: Overlay behavior for this window.
        chrome: Optional custom chrome policy.
    """

    id: str
    title: str
    surface: SurfaceConfig
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    chrome: ChromeConfig = field(default_factory=ChromeConfig)


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Root application configuration owned by the runtime.

    Attributes:
        windows: Windows available to the runtime, keyed by deterministic IDs.
        startup_window_ids: IDs of windows shown during startup.
        keyboard_window_id: ID of the default keyboard surface.
    """

    windows: tuple[WindowConfig, ...]
    startup_window_ids: tuple[str, ...]
    keyboard_window_id: str
