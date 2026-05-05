from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy

from ..grid.metrics import DEFAULT_KEYBOARD_METRICS
from .state import KeyStateChange, KeyStateMachine, StateListener

VoidCallback = Callable[[], None]


def format_key_label(label: str, secondary_label: str | None = None) -> str:
    if secondary_label is None:
        return label
    return f"{secondary_label}\n{label}"


def set_key_button_label(button: QPushButton, label: str, secondary_label: str | None = None) -> None:
    button.setText(format_key_label(label, secondary_label))


def refresh_key_button(button: QPushButton, state_machine: KeyStateMachine) -> None:
    button.setProperty("pressed", state_machine.is_pressed)
    button.setProperty("latched", state_machine.is_latched)
    button.setProperty("interactionState", state_machine.state.value)
    button.setChecked(state_machine.is_latched)
    button.style().unpolish(button)
    button.style().polish(button)
    button.update()


def create_key_button(
    label: str,
    *,
    state_machine: KeyStateMachine | None = None,
    latchable: bool = False,
    initial_latched: bool = False,
    on_state_change: StateListener | None = None,
    component_id: str | None = None,
    width: float = 1.0,
    secondary_label: str | None = None,
    key_id: str | None = None,
    io_key: str | None = None,
    profile: str | None = None,
    layout: str | None = None,
    on_press: VoidCallback | None = None,
    on_release: VoidCallback | None = None,
) -> QPushButton:
    button = QPushButton()
    metrics = DEFAULT_KEYBOARD_METRICS
    machine = state_machine or KeyStateMachine(latchable=latchable, initial_latched=initial_latched)
    set_key_button_label(button, label, secondary_label)
    button.setProperty("componentType", "key")
    button.setProperty("componentId", component_id or key_id or label)
    button.setProperty("keyId", key_id or label)
    button.setProperty("ioKey", io_key)
    button.setProperty("profile", profile)
    button.setProperty("layout", layout)
    button.setProperty("keyWidth", width)
    button.setProperty("pressed", machine.is_pressed)
    button.setProperty("latched", machine.is_latched)
    button.setProperty("latchable", machine.latchable)
    button.setProperty("interactionState", machine.state.value)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCheckable(machine.latchable)
    button.setMinimumHeight(metrics.span_height(1))
    button.setMinimumWidth(metrics.span_width(width))
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    button._axidev_key_state_machine = machine  # type: ignore[attr-defined]
    refresh_key_button(button, machine)

    machine.add_listener(lambda _change: refresh_key_button(button, machine))
    if on_state_change is not None:
        machine.add_listener(on_state_change)

    def handle_press() -> None:
        machine.press()
        if on_press is not None:
            on_press()

    def handle_release() -> None:
        machine.release()
        if machine.latchable:
            machine.toggle_latched()
        if on_release is not None:
            on_release()

    button.pressed.connect(handle_press)
    button.released.connect(handle_release)
    return button


def key_button_state_machine(button: QPushButton) -> KeyStateMachine:
    """Return the state machine owned by a key button.

    Args:
        button: Button created by ``create_key_button``.

    Returns:
        The button-owned key interaction state machine.

    Side effects:
        None.
    """

    return button._axidev_key_state_machine  # type: ignore[attr-defined,no-any-return]
