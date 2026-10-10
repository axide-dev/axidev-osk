"""Typed settings records for engine windows and attachments."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum


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
class DwellClickConfig:
    """Pointer dwell activation policy for one window.

    Attributes:
        enabled: Whether resting the pointer clicks inside the window.
        delay_ms: Base time required to activate the current target.
        dead_zone_px: Movement required to rearm after activation.
        full_speed_px_s: Highest speed that advances at the maximum rate.
        stop_speed_px_s: Speed at which progress stops completely.
        maximum_progress_rate: Progress multiplier at or below full speed.
        indicator_start_progress: Progress required before feedback appears.
        direction_reversal_progress_factor: Progress retained after a clear
            reversal inside the same target.
        movement_penalty_px: Distance that removes one full dwell of progress.
        distance_curve_full_px: Travel distance at which slowdown uses the
            normal rather than short-distance curve.
        velocity_release_ms: Time for remembered speed to fall from the stop
            threshold to zero after movement ends.
    """

    enabled: bool = False
    delay_ms: int = 200
    dead_zone_px: int = 10
    full_speed_px_s: float = 20.0
    stop_speed_px_s: float = 240.0
    maximum_progress_rate: float = 1.75
    indicator_start_progress: float = 0.25
    direction_reversal_progress_factor: float = 0.5
    movement_penalty_px: float = 15.0
    distance_curve_full_px: float = 200.0
    velocity_release_ms: int = 100

    def __post_init__(self) -> None:
        """Reject timing and distance values that cannot define a dwell."""

        if not math.isfinite(self.delay_ms) or self.delay_ms < 1:
            raise ValueError("Dwell click delay must be at least 1 millisecond")
        if not math.isfinite(self.dead_zone_px) or self.dead_zone_px < 0:
            raise ValueError(
                "Dwell click dead zone must be finite and non-negative"
            )
        if not math.isfinite(self.full_speed_px_s) or self.full_speed_px_s < 0:
            raise ValueError(
                "Dwell click full speed must be finite and non-negative"
            )
        if (
            not math.isfinite(self.stop_speed_px_s)
            or self.stop_speed_px_s <= self.full_speed_px_s
        ):
            raise ValueError(
                "Dwell click stop speed must be finite and greater than full speed"
            )
        if (
            not math.isfinite(self.maximum_progress_rate)
            or self.maximum_progress_rate < 1
        ):
            raise ValueError(
                "Dwell click maximum progress rate must be finite and at least 1"
            )
        if (
            not math.isfinite(self.indicator_start_progress)
            or not 0 <= self.indicator_start_progress <= 1
        ):
            raise ValueError(
                "Dwell click indicator start progress must be between 0 and 1"
            )
        if (
            not math.isfinite(self.direction_reversal_progress_factor)
            or not 0 <= self.direction_reversal_progress_factor <= 1
        ):
            raise ValueError(
                "Dwell click direction reversal progress factor must be between 0 and 1"
            )
        if not math.isfinite(self.movement_penalty_px) or self.movement_penalty_px <= 0:
            raise ValueError(
                "Dwell click movement penalty distance must be finite and positive"
            )
        if (
            not math.isfinite(self.distance_curve_full_px)
            or self.distance_curve_full_px <= 0
        ):
            raise ValueError(
                "Dwell click full curve distance must be finite and positive"
            )
        if (
            not math.isfinite(self.velocity_release_ms)
            or self.velocity_release_ms < 1
        ):
            raise ValueError(
                "Dwell click velocity release must be at least 1 millisecond"
            )


@dataclass(frozen=True, slots=True)
class PointerLocatorConfig:
    """Pointer glow settings for one pointer_locator attachment.

    Attributes:
        id: Attachment ID.
        radius_percent: Glow radius as a percentage of the surface's shorter side.
        maximum_opacity_percent: Glow opacity at the pointer position.
        radius_standard_deviations: Number of Gaussian standard deviations inside the radius.
        gap_color: Glow color while the pointer is between buttons.
    """

    id: str
    radius_percent: float
    maximum_opacity_percent: float
    radius_standard_deviations: float
    gap_color: str

    def __post_init__(self) -> None:
        """Reject values that cannot define a visible glow."""

        if not 0.0 < self.radius_percent <= 100.0:
            raise ValueError("Pointer locator radius percent must be greater than 0 and at most 100")
        if not 0.0 < self.maximum_opacity_percent <= 100.0:
            raise ValueError("Pointer locator maximum opacity percent must be greater than 0 and at most 100")
        if not math.isfinite(self.radius_standard_deviations) or self.radius_standard_deviations < 0.1:
            raise ValueError("Pointer locator radius standard deviations must be finite and at least 0.1")


@dataclass(frozen=True, slots=True)
class HotCornerConfig:
    """Hot-corner sensor timing, size, and indicator colors.

    The colors have no defaults: the profile gives them, as the engine owns no
    colors.

    Attributes:
        indicator_background: Fill of the indicator disc.
        indicator_track: Color of the ring the progress runs along.
        indicator_progress: Color of the progress arc.
        indicator_center: Fill of the center, which strengthens as the dwell completes.
        dwell_ms: Cursor dwell time required before a corner triggers.
        poll_interval_ms: Cursor/sensor polling interval in milliseconds.
        corner_size_px: Edge length of each hot-corner sensor region.
        indicator_size_px: Edge length of the visual dwell indicator.
        indicator_margin_px: Pixel margin between the indicator and screen edges.
    """

    indicator_background: str
    indicator_track: str
    indicator_progress: str
    indicator_center: str
    dwell_ms: int = 200
    poll_interval_ms: int = 25
    corner_size_px: int = 20
    indicator_size_px: int = 52
    indicator_margin_px: int = 14
