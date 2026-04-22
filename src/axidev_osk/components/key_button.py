from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy

from .key_state_machine import KeyStateMachine

VoidCallback = Callable[[], None]


def format_key_label(label: str, secondary_label: str | None = None) -> str:
    if secondary_label is None:
        return label
    return f"{secondary_label}\n{label}"


def set_key_button_label(button: QPushButton, label: str, secondary_label: str | None = None) -> None:
    button.setText(format_key_label(label, secondary_label))


def refresh_key_button(button: QPushButton, state_machine: KeyStateMachine) -> None:
    button.setProperty("latched", state_machine.is_latched)
    button.setProperty("interactionState", state_machine.state.value)
    button.setChecked(state_machine.is_latched)
    button.style().unpolish(button)
    button.style().polish(button)
    button.update()


def create_key_button(
    label: str,
    *,
    state_machine: KeyStateMachine,
    width: float = 1.0,
    secondary_label: str | None = None,
    key_id: str | None = None,
    on_press: VoidCallback | None = None,
    on_release: VoidCallback | None = None,
) -> QPushButton:
    button = QPushButton()
    set_key_button_label(button, label, secondary_label)
    button.setProperty("keyId", key_id or label)
    button.setProperty("keyWidth", width)
    button.setProperty("latched", state_machine.is_latched)
    button.setProperty("latchable", state_machine.latchable)
    button.setProperty("interactionState", state_machine.state.value)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCheckable(state_machine.latchable)
    button.setMinimumHeight(56)
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    refresh_key_button(button, state_machine)

    state_machine.add_listener(lambda _change: refresh_key_button(button, state_machine))

    def handle_press() -> None:
        state_machine.press()
        if on_press is not None:
            on_press()

    def handle_release() -> None:
        state_machine.release()
        if state_machine.latchable:
            state_machine.toggle_latched()
        if on_release is not None:
            if state_machine.latchable:
                QTimer.singleShot(0, on_release)
            else:
                on_release()

    button.pressed.connect(handle_press)
    button.released.connect(handle_release)
    return button
