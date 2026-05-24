"""Temporary hot-corner subsystem isolated from window and keyboard logic."""

from .controller import (
    HotCornerConfig,
    HotCornerIndicator,
    HotCornerOverlayController,
    HotCornerSensorHandle,
    HotCornerSensorWindow,
    HotCornerWindowToggleController,
    ScreenCorner,
    configure_hot_corner_overlay,
)

__all__ = [
    "HotCornerConfig",
    "HotCornerIndicator",
    "HotCornerOverlayController",
    "HotCornerSensorHandle",
    "HotCornerSensorWindow",
    "HotCornerWindowToggleController",
    "ScreenCorner",
    "configure_hot_corner_overlay",
]
