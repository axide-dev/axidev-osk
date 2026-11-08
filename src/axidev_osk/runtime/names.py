"""The fixed names events use for screen corners and mouse buttons.

Message definitions, widgets, services, and attachments all import them from
here, so none of them depends on another for a name, and nothing here needs Qt.
"""

from __future__ import annotations

from enum import Enum


class ScreenCorner(str, Enum):
    """The screen corners a ``hot_corners`` attachment watches and ``hot_corner.triggered`` names."""

    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


HOT_CORNERS = tuple(corner.value for corner in ScreenCorner)

MOUSE_BUTTON_NAMES = ("left", "right", "middle", "back", "forward")
"""Each mouse button an event names; the widgets map Qt's buttons onto these."""

OTHER_BUTTON = "other"
"""The name an event gives a mouse button ``MOUSE_BUTTON_NAMES`` does not list."""
