"""Temporary hot-corner subsystem isolated from window and keyboard logic."""

from .controller import (
    HiddenWindowState,
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
    "HiddenWindowState",
    "HotCornerConfig",
    "HotCornerIndicator",
    "HotCornerOverlayController",
    "HotCornerSensorHandle",
    "HotCornerSensorWindow",
    "HotCornerWindowToggleController",
    "ScreenCorner",
    "configure_hot_corner_overlay",
]
