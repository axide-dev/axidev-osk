"""Render-only key button construction and state helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy

from ..grid.metrics import DEFAULT_KEYBOARD_METRICS, KeyboardMetrics

VoidCallback = Callable[[], None]


def format_key_label(label: str, secondary_label: str | None = None) -> str:
    if secondary_label is None:
        return label
    return f"{secondary_label}\n{label}"


def set_key_button_label(
    button: QPushButton,
    label: str,
    secondary_label: str | None = None,
) -> None:
    button.setText(format_key_label(label, secondary_label))


def render_key_button_state(button: QPushButton, state: Mapping[str, object]) -> None:
    """Render a complete runtime-owned state snapshot on one key button."""

    pressed = bool(state.get("pressed", False))
    latched = bool(state.get("latched", False))
    if pressed and latched:
        interaction_state = "latched_pressed"
    elif pressed:
        interaction_state = "pressed"
    elif latched:
        interaction_state = "latched"
    else:
        interaction_state = "idle"
    button.setProperty("pressed", pressed)
    button.setProperty("latched", latched)
    button.setProperty("interactionState", interaction_state)
    button.setChecked(latched)
    button.style().unpolish(button)
    button.style().polish(button)
    button.update()


def create_key_button(
    label: str,
    *,
    component_id: str,
    width: float = 1.0,
    secondary_label: str | None = None,
    profile: str | None = None,
    layout: str | None = None,
    on_press: VoidCallback | None = None,
    on_release: VoidCallback | None = None,
    metrics: KeyboardMetrics | None = None,
) -> QPushButton:
    """Create a visual key button that emits callbacks but owns no state."""

    button = QPushButton()
    cell_metrics = metrics or DEFAULT_KEYBOARD_METRICS
    set_key_button_label(button, label, secondary_label)
    button.setProperty("componentType", "key")
    button.setProperty("componentId", component_id)
    button.setProperty("profile", profile)
    button.setProperty("layout", layout)
    button.setProperty("keyWidth", width)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCheckable(True)
    button.setMinimumHeight(cell_metrics.span_height(1))
    button.setMinimumWidth(cell_metrics.span_width(width))
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    render_key_button_state(button, {})
    if on_press is not None:
        button.pressed.connect(on_press)
    if on_release is not None:
        button.released.connect(on_release)
    return button
