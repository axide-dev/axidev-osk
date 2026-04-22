"""Application shell modules."""

from .overlay_window import (
    AlwaysOnTopWindowConfig,
    OverlayBackend,
    OverlayPlacement,
    configure_always_on_top_window,
    create_always_on_top_window,
    prepare_always_on_top_window_environment,
)
from .window_chrome import (
    OverlayChromeWidgets,
    OverlayResizeHandle,
    OverlayTitleBar,
    install_overlay_chrome,
)

__all__ = [
    "AlwaysOnTopWindowConfig",
    "OverlayBackend",
    "OverlayChromeWidgets",
    "OverlayPlacement",
    "OverlayResizeHandle",
    "OverlayTitleBar",
    "configure_always_on_top_window",
    "create_always_on_top_window",
    "install_overlay_chrome",
    "prepare_always_on_top_window_environment",
]
