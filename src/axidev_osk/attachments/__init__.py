"""Attachments: Python-owned feature primitives that profiles attach by reference.

An attachment owns its own loop (dwell timing, pointer glow, corner sensors,
lock-screen supervision). A profile names its fixed target window and its
options; any option may be a binding, and the attachment applies new options
whenever the state they read changes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import MISSING, dataclass, fields
from typing import Protocol, TypeVar

from ..config.models import DwellClickConfig, HotCornerConfig, PointerLocatorConfig
from ..config.reader import ConfigError, ConfigReader
from ..kind_registry import KindRegistry
from ..runtime.app_messages import HOT_CORNERS

CORNERS = frozenset(HOT_CORNERS)

SettingsT = TypeVar("SettingsT")


@dataclass(frozen=True, slots=True)
class HotCornersOptions:
    corners: frozenset[str]
    settings: HotCornerConfig


class AttachmentWindow(Protocol):
    def set_dwell(self, config: DwellClickConfig) -> None: ...

    def set_pointer_locator(self, settings: PointerLocatorConfig) -> None: ...


class HotCornerTarget(Protocol):
    def configure(self, settings: HotCornerConfig, corners: frozenset[str]) -> None: ...

    def clear(self) -> None: ...


class AttachmentHost(Protocol):
    """What an attachment kind may use when it is attached for the running profile."""

    def window(self, window_id: str) -> AttachmentWindow | None: ...

    def keep_dwell(self, window_id: str, config: DwellClickConfig) -> None: ...

    def keep_pointer_locator(self, window_id: str, settings: PointerLocatorConfig) -> None: ...

    def hot_corners(self) -> HotCornerTarget | None: ...

    def set_secure_input_panel(self, window_id: str) -> None: ...


class AttachmentUnavailable(Exception):
    """The running app has no service this attachment kind needs, so the attachment does nothing."""


Apply = Callable[[object], None]


@dataclass(frozen=True, slots=True)
class AttachmentKind:
    """How one attachment kind reads its fixed target window and its options, and attaches to the app.

    ``attach`` receives the host and the target and returns the function that
    applies each new set of options; it raises ``AttachmentUnavailable`` when
    the host lacks what the kind needs. ``limit`` is ``"window"`` when a window
    takes at most one attachment of the kind, ``"profile"`` when a profile
    does, and ``None`` when any number fit.
    """

    name: str
    decode_target: Callable[[ConfigReader], str | None]
    decode_options: Callable[[ConfigReader], object]
    attach: Callable[[AttachmentHost, str | None], Apply]
    limit: str | None = None


AttachmentKindRegistry = KindRegistry[AttachmentKind]


def register_builtin_attachments(registry: AttachmentKindRegistry) -> None:
    registry.register(AttachmentKind("dwell", _window_target, _decode_dwell, _attach_dwell, limit="window"))
    registry.register(AttachmentKind("pointer_locator", _window_target, _decode_pointer_locator, _attach_pointer_locator))
    registry.register(AttachmentKind("hot_corners", _no_target, _decode_hot_corners, _attach_hot_corners, limit="profile"))
    registry.register(
        AttachmentKind("secure_input_panel", _window_target, _no_options, _attach_secure_input_panel, limit="profile")
    )


def _window_target(reader: ConfigReader) -> str:
    return reader.string("window")


def _no_target(reader: ConfigReader) -> None:
    del reader


def _no_options(reader: ConfigReader) -> None:
    del reader


def _settings(reader: ConfigReader, build: Callable[[], SettingsT]) -> SettingsT:
    """Build a settings record, reporting its own range checks with the attachment's path."""

    try:
        return build()
    except ConfigError:
        raise
    except ValueError as exc:
        raise ConfigError(f"{reader.path}: {exc}") from exc


def _defaults(record: type) -> dict[str, object]:
    """Return a settings record's own field defaults, so each default is written once, on the record."""

    return {item.name: item.default for item in fields(record) if item.default is not MISSING}


def _decode_dwell(reader: ConfigReader) -> DwellClickConfig:
    defaults = _defaults(DwellClickConfig)
    return _settings(
        reader,
        lambda: DwellClickConfig(
            enabled=reader.boolean("enabled", defaults["enabled"]),
            delay_ms=reader.integer("delay_ms", defaults["delay_ms"]),
            dead_zone_px=reader.integer("dead_zone_px", defaults["dead_zone_px"]),
            full_speed_px_s=reader.number("full_speed_px_s", defaults["full_speed_px_s"]),
            stop_speed_px_s=reader.number("stop_speed_px_s", defaults["stop_speed_px_s"]),
            maximum_progress_rate=reader.number("maximum_progress_rate", defaults["maximum_progress_rate"]),
            indicator_start_progress=reader.number("indicator_start_progress", defaults["indicator_start_progress"]),
            direction_reversal_progress_factor=reader.number(
                "direction_reversal_progress_factor", defaults["direction_reversal_progress_factor"]
            ),
            direction_reversal_angle_deg=reader.number(
                "direction_reversal_angle_deg", defaults["direction_reversal_angle_deg"]
            ),
            acceleration_exponent_near=reader.number(
                "acceleration_exponent_near", defaults["acceleration_exponent_near"]
            ),
            acceleration_exponent_far=reader.number("acceleration_exponent_far", defaults["acceleration_exponent_far"]),
            poll_interval_ms=reader.integer("poll_interval_ms", defaults["poll_interval_ms"]),
            movement_penalty_px=reader.number("movement_penalty_px", defaults["movement_penalty_px"]),
            distance_curve_full_px=reader.number("distance_curve_full_px", defaults["distance_curve_full_px"]),
            velocity_release_ms=reader.integer("velocity_release_ms", defaults["velocity_release_ms"]),
            indicator_size_px=reader.integer("indicator_size_px", defaults["indicator_size_px"]),
            indicator_min_dot_px=reader.integer("indicator_min_dot_px", defaults["indicator_min_dot_px"]),
            indicator_max_dot_px=reader.integer("indicator_max_dot_px", defaults["indicator_max_dot_px"]),
            indicator_fade_ms=reader.integer("indicator_fade_ms", defaults["indicator_fade_ms"]),
            indicator_opacity=reader.number("indicator_opacity", defaults["indicator_opacity"]),
            indicator_track_opacity=reader.number("indicator_track_opacity", defaults["indicator_track_opacity"]),
        ),
    )


def _decode_pointer_locator(reader: ConfigReader) -> PointerLocatorConfig:
    attachment_id = reader.string("id")
    defaults = _defaults(PointerLocatorConfig)
    return _settings(
        reader,
        lambda: PointerLocatorConfig(
            id=attachment_id,
            radius_percent=reader.number("radius_percent", defaults["radius_percent"]),
            maximum_opacity_percent=reader.number("maximum_opacity_percent", defaults["maximum_opacity_percent"]),
            radius_standard_deviations=reader.number("radius_standard_deviations", defaults["radius_standard_deviations"]),
            poll_interval_ms=reader.integer("poll_interval_ms", defaults["poll_interval_ms"]),
            gap_color=reader.color("gap_color"),
        ),
    )


def _decode_hot_corners(reader: ConfigReader) -> HotCornersOptions:
    corners = frozenset(reader.string_list("corners", sorted(CORNERS)))
    unknown = sorted(corners - CORNERS)
    if unknown:
        raise ConfigError(f"{reader.field_path('corners')} has unknown corners: {', '.join(unknown)}")
    defaults = _defaults(HotCornerConfig)
    return HotCornersOptions(
        corners=corners,
        settings=_settings(reader, lambda: HotCornerConfig(
            indicator_background=reader.color("indicator_background"),
            indicator_track=reader.color("indicator_track"),
            indicator_progress=reader.color("indicator_progress"),
            indicator_center=reader.color("indicator_center"),
            enabled=reader.boolean("enabled", defaults["enabled"]),
            fires_on_rest=reader.boolean("fires_on_rest", defaults["fires_on_rest"]),
            dwell_ms=reader.integer("dwell_ms", defaults["dwell_ms"], minimum=1),
            poll_interval_ms=reader.integer("poll_interval_ms", defaults["poll_interval_ms"], minimum=1),
            corner_size_px=reader.integer("corner_size_px", defaults["corner_size_px"], minimum=1),
            indicator_size_px=reader.integer("indicator_size_px", defaults["indicator_size_px"], minimum=1),
            indicator_margin_px=reader.integer("indicator_margin_px", defaults["indicator_margin_px"], minimum=0),
            indicator_disc_inset_px=reader.integer(
                "indicator_disc_inset_px", defaults["indicator_disc_inset_px"], minimum=0
            ),
            indicator_ring_inset_px=reader.integer(
                "indicator_ring_inset_px", defaults["indicator_ring_inset_px"], minimum=0
            ),
            indicator_center_inset_px=reader.integer(
                "indicator_center_inset_px", defaults["indicator_center_inset_px"], minimum=0
            ),
            indicator_track_width_px=reader.integer(
                "indicator_track_width_px", defaults["indicator_track_width_px"], minimum=0
            ),
            indicator_progress_width_px=reader.integer(
                "indicator_progress_width_px", defaults["indicator_progress_width_px"], minimum=0
            ),
            indicator_center_start_opacity=reader.number(
                "indicator_center_start_opacity", defaults["indicator_center_start_opacity"], minimum=0.0, maximum=1.0
            ),
        )),
    )


def _attach_dwell(host: AttachmentHost, target: str | None) -> Apply:
    window_id = target or ""

    def apply(options: object) -> None:
        assert isinstance(options, DwellClickConfig)
        host.keep_dwell(window_id, options)
        window = host.window(window_id)
        if window is not None:
            window.set_dwell(options)

    return apply


def _attach_pointer_locator(host: AttachmentHost, target: str | None) -> Apply:
    window_id = target or ""

    def apply(options: object) -> None:
        assert isinstance(options, PointerLocatorConfig)
        host.keep_pointer_locator(window_id, options)
        window = host.window(window_id)
        if window is not None:
            window.set_pointer_locator(options)

    return apply


def _attach_hot_corners(host: AttachmentHost, target: str | None) -> Apply:
    del target
    hot_corners = host.hot_corners()
    if hot_corners is None:
        raise AttachmentUnavailable("this app runs without the hot-corner service")

    def apply(options: object) -> None:
        assert isinstance(options, HotCornersOptions)
        hot_corners.configure(options.settings, options.corners)

    return apply


def _attach_secure_input_panel(host: AttachmentHost, target: str | None) -> Apply:
    host.set_secure_input_panel(target or "")
    return lambda _options: None
