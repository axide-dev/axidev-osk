"""Qt's mouse buttons mapped onto the names events give them, so profiles never see Qt's values."""

from __future__ import annotations

from PySide6.QtCore import Qt

from ..runtime.names import MOUSE_BUTTON_NAMES, OTHER_BUTTON

MOUSE_BUTTONS: dict[Qt.MouseButton, str] = dict(
    zip(
        (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.RightButton,
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.BackButton,
            Qt.MouseButton.ForwardButton,
        ),
        MOUSE_BUTTON_NAMES,
        strict=True,
    )
)
"""Each Qt mouse button an event reports, by the name it reports it with."""

BUTTONS_BY_NAME = {name: button for button, name in MOUSE_BUTTONS.items()}


def mouse_button_name(button: Qt.MouseButton) -> str:
    return MOUSE_BUTTONS.get(button, OTHER_BUTTON)
