"""Typed settings records for engine windows and attachments."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Anchor:
    """Where a window starts on its screen, as a point of the space the window leaves free there.

    ``x`` runs from 0 at the left edge to 1 at the right edge, and ``y`` from 0
    at the top to 1 at the bottom, each edge kept ``screen_margin`` away; 0.5
    centers the window on that axis.

    Placement is an anchor rather than a position because on Wayland a
    layer-shell window can only be placed by screen edges and margins, so an
    anchor is what every platform can honor: X11 and Windows place the window
    at the point it names, and Wayland turns it into margins. KWin places its
    input panel itself, so there the anchor does nothing.
    """

    x: float
    y: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.x <= 1.0 and 0.0 <= self.y <= 1.0):
            raise ValueError("An anchor's x and y must be between 0 and 1")


ANCHORS = {
    f"{vertical}{horizontal}".strip("-") or "center": Anchor(x, y)
    for vertical, y in (("top-", 0.0), ("", 0.5), ("bottom-", 1.0))
    for horizontal, x in (("left", 0.0), ("", 0.5), ("right", 1.0))
}
"""The engine's named anchors: ``top-left``, ``top``, ``top-right``, ``left``, ``center``, ``right``,
``bottom-left``, ``bottom``, and ``bottom-right``."""


@dataclass(slots=True)
class AlwaysOnTopWindowConfig:
    """Platform-agnostic overlay placement policy.

    Attributes:
        placement: Where the window starts on its screen.
        screen_margin: Pixel margin from the screen edges the anchor keeps.
        manage_position: Whether the overlay controller should keep the
            window placed; ``False`` lets the host owner manage geometry.
        keep_on_screen: Whether a floating window that grows past its
            screen's edge is moved back inside it.
    """

    placement: Anchor = ANCHORS["top-right"]
    screen_margin: int = 16
    manage_position: bool = True
    keep_on_screen: bool = True


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
        enabled: Whether resting the pointer inside the window reports ``dwell.completed``.
        delay_ms: Base time required to activate the current target.
        dead_zone_px: Movement required to rearm after activation.
        full_speed_px_s: Highest speed that advances at the maximum rate.
        stop_speed_px_s: Speed at which progress stops completely.
        maximum_progress_rate: Progress multiplier at or below full speed.
        indicator_start_progress: Progress required before feedback appears.
        direction_reversal_progress_factor: Progress retained after a clear
            reversal inside the same target.
        direction_reversal_angle_deg: How far, in degrees, the pointer must
            turn between two samples for the turn to count as a reversal.
        movement_penalty_px: Distance that removes one full dwell of progress.
        distance_curve_full_px: Travel distance at which slowdown uses the
            normal rather than short-distance curve.
        velocity_release_ms: Time for remembered speed to fall from the stop
            threshold to zero after movement ends.
        acceleration_exponent_near: How strongly slowing down speeds a dwell
            up right after a click; smaller values speed it up sooner.
        acceleration_exponent_far: How strongly slowing down speeds a dwell up
            after ``distance_curve_full_px`` of travel, or before any click.
        poll_interval_ms: How often the pointer is sampled.
        pause_while_pressed: Whether a held mouse button discards the current
            dwell and keeps a new one from starting until it is released.
        indicator_size_px: Width and height of the progress indicator.
        indicator_min_dot_px: Dot diameter when progress starts.
        indicator_max_dot_px: Dot diameter at full progress.
        indicator_fade_ms: How long the dot fades after a cancel or a click.
        indicator_opacity: Opacity of the growing dot and of the dot that fades
            after a cancel or a click.
        indicator_track_opacity: Opacity of the full-size dot drawn behind the
            growing one.

    The dot's colors come from the window's palette: ``Mid`` while it grows and
    when it fades after a cancel, ``Highlight`` when it fades after a click.
    """

    enabled: bool = False
    delay_ms: int = 200
    dead_zone_px: int = 10
    full_speed_px_s: float = 20.0
    stop_speed_px_s: float = 240.0
    maximum_progress_rate: float = 1.75
    indicator_start_progress: float = 0.25
    direction_reversal_progress_factor: float = 0.5
    direction_reversal_angle_deg: float = 120.0
    movement_penalty_px: float = 15.0
    distance_curve_full_px: float = 200.0
    velocity_release_ms: int = 100
    acceleration_exponent_near: float = 0.25
    acceleration_exponent_far: float = 0.5
    poll_interval_ms: int = 16
    pause_while_pressed: bool = True
    indicator_size_px: int = 30
    indicator_min_dot_px: int = 4
    indicator_max_dot_px: int = 24
    indicator_fade_ms: int = 250
    indicator_opacity: float = 0.94
    indicator_track_opacity: float = 0.51

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
        if self.indicator_size_px < 1:
            raise ValueError("Dwell click indicator size must be at least 1 pixel")
        if not 0 <= self.indicator_min_dot_px <= self.indicator_max_dot_px <= self.indicator_size_px:
            raise ValueError(
                "Dwell click indicator dots must satisfy 0 <= minimum <= maximum <= indicator size"
            )
        if self.indicator_fade_ms < 0:
            raise ValueError("Dwell click indicator fade must be at least 0 milliseconds")
        if not 0 < self.direction_reversal_angle_deg <= 180:
            raise ValueError("Dwell click direction reversal angle must be over 0 and at most 180 degrees")
        if not 0 < self.acceleration_exponent_near <= self.acceleration_exponent_far:
            raise ValueError("Dwell click acceleration exponents must satisfy 0 < near <= far")
        if self.poll_interval_ms < 1:
            raise ValueError("Dwell click poll interval must be at least 1 millisecond")
        for opacity in (self.indicator_opacity, self.indicator_track_opacity):
            if not 0 <= opacity <= 1:
                raise ValueError("Dwell click indicator opacities must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class PointerLocatorConfig:
    """Pointer glow settings for one pointer_locator attachment.

    Attributes:
        id: Attachment ID.
        gap_color: Glow color while the pointer is between buttons.
        radius_percent: Glow radius as a percentage of the surface's shorter side.
        maximum_opacity_percent: Glow opacity at the pointer position.
        radius_standard_deviations: Number of Gaussian standard deviations inside the radius.
        poll_interval_ms: How often the pointer is sampled while it is over the window.
    """

    id: str
    gap_color: str
    radius_percent: float = 30.0
    maximum_opacity_percent: float = 60.0
    radius_standard_deviations: float = 3.0
    poll_interval_ms: int = 16

    def __post_init__(self) -> None:
        """Reject values that cannot define a visible glow."""

        if not 0.0 < self.radius_percent <= 100.0:
            raise ValueError("Pointer locator radius percent must be greater than 0 and at most 100")
        if not 0.0 < self.maximum_opacity_percent <= 100.0:
            raise ValueError("Pointer locator maximum opacity percent must be greater than 0 and at most 100")
        if not math.isfinite(self.radius_standard_deviations) or self.radius_standard_deviations < 0.1:
            raise ValueError("Pointer locator radius standard deviations must be finite and at least 0.1")
        if self.poll_interval_ms < 1:
            raise ValueError("Pointer locator poll interval must be at least 1 millisecond")


@dataclass(frozen=True, slots=True)
class HotCornerConfig:
    """Hot-corner sensor timing, size, and indicator colors.

    The colors have no defaults: the profile gives them, as the engine owns no
    colors. Each is drawn with its own alpha, so ``#AARRGGBB`` sets how
    transparent it is.

    Attributes:
        enabled: Whether the corners are watched at all.
        fires_on_rest: Whether the built-in trigger runs: a corner fires
            ``hot_corner.triggered`` once the pointer rests in it for
            ``dwell_ms``, while the indicator shows the progress. Without it,
            ``hot_corner.entered`` and ``hot_corner.left`` are still reported,
            so a profile can decide on its own when a corner fires.
        indicator_background: Fill of the indicator disc.
        indicator_track: Color of the ring the progress runs along.
        indicator_progress: Color of the progress arc.
        indicator_center: Fill of the center once the dwell completes.
        dwell_ms: Cursor dwell time required before a corner triggers.
        poll_interval_ms: Cursor/sensor polling interval in milliseconds.
        corner_size_px: Edge length of each hot-corner sensor region.
        indicator_size_px: Edge length of the visual dwell indicator.
        indicator_margin_px: Pixel margin between the indicator and screen edges.
        indicator_disc_inset_px: Space between the indicator's edge and its disc.
        indicator_ring_inset_px: Space between the indicator's edge and its ring.
        indicator_center_inset_px: Space between the indicator's edge and its center.
        indicator_track_width_px: Line width of the ring.
        indicator_progress_width_px: Line width of the progress arc.
        indicator_center_start_opacity: Share of ``indicator_center``'s alpha
            the center has when a dwell starts; it reaches the full alpha as the
            dwell completes.
    """

    indicator_background: str
    indicator_track: str
    indicator_progress: str
    indicator_center: str
    enabled: bool = True
    fires_on_rest: bool = True
    dwell_ms: int = 200
    poll_interval_ms: int = 25
    corner_size_px: int = 20
    indicator_size_px: int = 52
    indicator_margin_px: int = 14
    indicator_disc_inset_px: int = 2
    indicator_ring_inset_px: int = 6
    indicator_center_inset_px: int = 16
    indicator_track_width_px: int = 4
    indicator_progress_width_px: int = 5
    indicator_center_start_opacity: float = 0.54

    def __post_init__(self) -> None:
        """Reject insets that leave nothing of the indicator to draw."""

        for inset in (self.indicator_disc_inset_px, self.indicator_ring_inset_px, self.indicator_center_inset_px):
            if not 0 <= inset * 2 < self.indicator_size_px:
                raise ValueError("Hot corner indicator insets must be at least 0 and under half the indicator size")
        if not 0.0 <= self.indicator_center_start_opacity <= 1.0:
            raise ValueError("Hot corner indicator center start opacity must be between 0 and 1")
