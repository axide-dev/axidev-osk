"""Platform-encapsulated overlay window helpers."""

from .always_on_top import (
    OVERLAY_BACKEND_ENV,
    OVERLAY_DEBUG_ENV,
    AlwaysOnTopWindowConfig,
    AlwaysOnTopWindowController,
    OverlayBackend,
    OverlayPlacement,
    PlainWindowController,
    configure_always_on_top_window,
    configure_plain_window,
    create_always_on_top_window,
    prepare_always_on_top_window_environment,
)

__all__ = [
    "OVERLAY_BACKEND_ENV",
    "OVERLAY_DEBUG_ENV",
    "AlwaysOnTopWindowConfig",
    "AlwaysOnTopWindowController",
    "OverlayBackend",
    "OverlayPlacement",
    "PlainWindowController",
    "configure_always_on_top_window",
    "configure_plain_window",
    "create_always_on_top_window",
    "prepare_always_on_top_window_environment",
]
