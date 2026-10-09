"""Attachments: Python-owned feature primitives that profiles attach by reference.

An attachment owns its own loop (dwell timing, pointer glow, corner sensors,
lock-screen supervision). A profile only names its target and options, then
talks to it through actions, events, and observed state.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from ..config.models import DwellClickConfig, HotCornerConfig, PointerLocatorConfig
from ..config.reader import ConfigError, ConfigReader
from ..kind_registry import KindRegistry

CORNERS = frozenset({"top_left", "top_right", "bottom_left", "bottom_right"})

SettingsT = TypeVar("SettingsT")


@dataclass(frozen=True, slots=True)
class DwellOptions:
    window: str
    settings: DwellClickConfig


@dataclass(frozen=True, slots=True)
class PointerLocatorOptions:
    window: str
    settings: PointerLocatorConfig


@dataclass(frozen=True, slots=True)
class HotCornersOptions:
    corners: frozenset[str]
    settings: HotCornerConfig


@dataclass(frozen=True, slots=True)
class SecureInputPanelOptions:
    window: str


@dataclass(frozen=True, slots=True)
class AttachmentKind:
    name: str
    decode_options: Callable[[ConfigReader], object]


AttachmentKindRegistry = KindRegistry[AttachmentKind]


def register_builtin_attachments(registry: AttachmentKindRegistry) -> None:
    registry.register(AttachmentKind("dwell", _decode_dwell))
    registry.register(AttachmentKind("pointer_locator", _decode_pointer_locator))
    registry.register(AttachmentKind("hot_corners", _decode_hot_corners))
    registry.register(AttachmentKind("secure_input_panel", _decode_secure_input_panel))


def _settings(reader: ConfigReader, build: Callable[[], SettingsT]) -> SettingsT:
    """Build a settings record, reporting its own range checks with the attachment's path."""

    try:
        return build()
    except ConfigError:
        raise
    except ValueError as exc:
        raise ConfigError(f"{reader.path}: {exc}") from exc


def _decode_dwell(reader: ConfigReader) -> DwellOptions:
    defaults = DwellClickConfig()
    settings = _settings(
        reader,
        lambda: DwellClickConfig(
            enabled=reader.boolean("enabled", defaults.enabled),
            delay_ms=reader.integer("delay_ms", defaults.delay_ms),
            dead_zone_px=reader.integer("dead_zone_px", defaults.dead_zone_px),
            full_speed_px_s=reader.number("full_speed_px_s", defaults.full_speed_px_s),
            stop_speed_px_s=reader.number("stop_speed_px_s", defaults.stop_speed_px_s),
            maximum_progress_rate=reader.number("maximum_progress_rate", defaults.maximum_progress_rate),
            indicator_start_progress=reader.number("indicator_start_progress", defaults.indicator_start_progress),
            direction_reversal_progress_factor=reader.number(
                "direction_reversal_progress_factor",
                defaults.direction_reversal_progress_factor,
            ),
            movement_penalty_px=reader.number("movement_penalty_px", defaults.movement_penalty_px),
            distance_curve_full_px=reader.number("distance_curve_full_px", defaults.distance_curve_full_px),
            velocity_release_ms=reader.integer("velocity_release_ms", defaults.velocity_release_ms),
        ),
    )
    return DwellOptions(window=reader.string("window"), settings=settings)


def _decode_pointer_locator(reader: ConfigReader) -> PointerLocatorOptions:
    attachment_id = reader.string("id")
    settings = _settings(
        reader,
        lambda: PointerLocatorConfig(
            id=attachment_id,
            radius_percent=reader.number("radius_percent", 30.0),
            maximum_opacity_percent=reader.number("maximum_opacity_percent", 60.0),
            radius_standard_deviations=reader.number("radius_standard_deviations", 3.0),
        ),
    )
    return PointerLocatorOptions(window=reader.string("window"), settings=settings)


def _decode_hot_corners(reader: ConfigReader) -> HotCornersOptions:
    corners = frozenset(reader.string_list("corners", sorted(CORNERS)))
    unknown = sorted(corners - CORNERS)
    if unknown:
        raise ConfigError(f"{reader.field_path('corners')} has unknown corners: {', '.join(unknown)}")
    defaults = HotCornerConfig()
    return HotCornersOptions(
        corners=corners,
        settings=HotCornerConfig(
            dwell_ms=reader.integer("dwell_ms", defaults.dwell_ms, minimum=1),
            poll_interval_ms=reader.integer("poll_interval_ms", defaults.poll_interval_ms, minimum=1),
            corner_size_px=reader.integer("corner_size_px", defaults.corner_size_px, minimum=1),
            indicator_size_px=reader.integer("indicator_size_px", defaults.indicator_size_px, minimum=1),
            indicator_margin_px=reader.integer("indicator_margin_px", defaults.indicator_margin_px, minimum=0),
            indicator_background=reader.color("indicator_background", defaults.indicator_background),
            indicator_track=reader.color("indicator_track", defaults.indicator_track),
            indicator_progress=reader.color("indicator_progress", defaults.indicator_progress),
            indicator_center=reader.color("indicator_center", defaults.indicator_center),
        ),
    )


def _decode_secure_input_panel(reader: ConfigReader) -> SecureInputPanelOptions:
    return SecureInputPanelOptions(window=reader.string("window"))
