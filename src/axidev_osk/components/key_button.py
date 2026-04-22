from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy

VoidCallback = Callable[[], None]


def format_key_label(label: str, secondary_label: str | None = None) -> str:
    if secondary_label is None:
        return label
    return f"{secondary_label}\n{label}"


def refresh_key_button(button: QPushButton, latched: bool) -> None:
    button.setProperty("latched", latched)
    button.setChecked(latched)
    button.style().unpolish(button)
    button.style().polish(button)
    button.update()


def create_key_button(
    label: str,
    *,
    width: float = 1.0,
    secondary_label: str | None = None,
    key_id: str | None = None,
    latchable: bool = False,
    latched: bool = False,
    on_press: VoidCallback | None = None,
    on_latch: VoidCallback | None = None,
    on_unlatch: VoidCallback | None = None,
) -> QPushButton:
    button = QPushButton(format_key_label(label, secondary_label))
    button.setProperty("keyId", key_id or label)
    button.setProperty("keyWidth", width)
    button.setProperty("latched", latched)
    button.setProperty("latchable", latchable)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCheckable(latchable)
    button.setMinimumHeight(56)
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    refresh_key_button(button, latched)

    def handle_click() -> None:
        if latchable:
            next_latched = not bool(button.property("latched"))
            refresh_key_button(button, next_latched)
            if next_latched:
                if on_latch is not None:
                    on_latch()
            elif on_unlatch is not None:
                on_unlatch()

        if on_press is not None:
            on_press()

    button.clicked.connect(handle_click)
    return button
