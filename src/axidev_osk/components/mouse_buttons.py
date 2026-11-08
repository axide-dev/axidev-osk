"""The names events give to mouse buttons, so profiles never see Qt's values."""

from __future__ import annotations

from PySide6.QtCore import Qt

MOUSE_BUTTONS = {
    Qt.MouseButton.LeftButton: "left",
    Qt.MouseButton.RightButton: "right",
    Qt.MouseButton.MiddleButton: "middle",
    Qt.MouseButton.BackButton: "back",
    Qt.MouseButton.ForwardButton: "forward",
}
"""Each Qt mouse button an event reports, by the name it reports it with."""

BUTTONS_BY_NAME = {name: button for button, name in MOUSE_BUTTONS.items()}

OTHER_BUTTON = "other"
"""The name of a mouse button ``MOUSE_BUTTONS`` does not list."""


def mouse_button_name(button: Qt.MouseButton) -> str:
    return MOUSE_BUTTONS.get(button, OTHER_BUTTON)
