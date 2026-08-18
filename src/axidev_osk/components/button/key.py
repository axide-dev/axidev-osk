"""Key button widget construction and label/state helpers.

Key buttons are reusable Qt widgets paired with a ``KeyStateMachine``.
Construction stays in this leaf component; latch wiring, event dispatch,
and durable state ownership are the responsibility of the containing
keyboard grid and the runtime context.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy

from ..grid.metrics import DEFAULT_KEYBOARD_METRICS, KeyboardMetrics
from .state import KeyStateMachine, StateListener

VoidCallback = Callable[[], None]


@dataclass(frozen=True)
class KeyButton:
    """Construction result pairing a key button with its state machine.

    The pair is returned together so callers do not need to fish the
    state machine out of a private widget attribute. Durable ownership
    of the machine belongs to the runtime state store; this dataclass is
    just the construction handoff.
    """

    button: QPushButton
    state_machine: KeyStateMachine


def format_key_label(label: str, secondary_label: str | None = None) -> str:
    """Format a key button label with an optional secondary line above it.

    Args:
        label: Primary label text.
        secondary_label: Optional shifted/secondary glyph rendered above the
            primary label.

    Returns:
        Combined label string, with a newline separating secondary and primary
        when both are present.

    Side effects:
        None.
    """

    if secondary_label is None:
        return label
    return f"{secondary_label}\n{label}"


def set_key_button_label(button: QPushButton, label: str, secondary_label: str | None = None) -> None:
    """Apply a formatted label to an existing key button.

    Args:
        button: Existing key button.
        label: Primary label text.
        secondary_label: Optional secondary glyph rendered above the primary.

    Returns:
        None.

    Side effects:
        Mutates the button's displayed text.
    """

    button.setText(format_key_label(label, secondary_label))


def refresh_key_button(button: QPushButton, state_machine: KeyStateMachine) -> None:
    """Sync a key button's Qt properties with its state machine.

    Args:
        button: Key button created by ``create_key_button``.
        state_machine: The button's interaction state machine.

    Returns:
        None.

    Side effects:
        Updates dynamic Qt properties (``pressed``, ``latched``,
        ``interactionState``), the checked flag, and triggers a style
        repolish so QSS selectors react to the new state.
    """

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
    component_id: str,
    state_machine: KeyStateMachine | None = None,
    latchable: bool = False,
    initial_latched: bool = False,
    on_state_change: StateListener | None = None,
    width: float = 1.0,
    secondary_label: str | None = None,
    key_id: str | None = None,
    io_key: str | None = None,
    profile: str | None = None,
    layout: str | None = None,
    on_press: VoidCallback | None = None,
    on_release: VoidCallback | None = None,
    metrics: KeyboardMetrics | None = None,
) -> KeyButton:
    """Create a configured key button paired with its state machine.

    Args:
        label: Visible primary label.
        state_machine: Optional pre-constructed state machine. When omitted,
            a new one is created using ``latchable`` and ``initial_latched``.
        latchable: Whether the button supports latched/locked behavior.
        initial_latched: Initial latch state when constructing a new machine.
        on_state_change: Optional listener called for every state transition.
        component_id: Required deterministic component ID stored on the Qt widget.
        width: Layout width in keyboard units; controls minimum width and the
            ``keyWidth`` Qt dynamic property.
        secondary_label: Optional shifted glyph rendered above the primary.
        key_id: Modifier identity string (e.g. ``"shift"``).
        io_key: Backend input key name forwarded to the keyboard service.
        profile: Active profile string written to the ``profile`` Qt property.
        layout: Active deterministic layout ID written to the ``layout`` Qt property.
        on_press: Optional callback fired on Qt ``pressed``.
        on_release: Optional callback fired on Qt ``released`` after the
            internal state machine processes the release and toggles latch.
        metrics: Pixel metrics used to size the button. Defaults to
            ``DEFAULT_KEYBOARD_METRICS`` when omitted.

    Returns:
        ``KeyButton`` pairing the constructed ``QPushButton`` with the
        ``KeyStateMachine`` that drives it. Callers are responsible for
        storing the machine wherever durable ownership lives (typically
        the runtime state store, namespaced by component ID).

    Side effects:
        Connects ``pressed``/``released`` signals to internal handlers and
        registers a listener that keeps Qt properties synced.
    """

    button = QPushButton()
    cell_metrics = metrics or DEFAULT_KEYBOARD_METRICS
    machine = state_machine or KeyStateMachine(latchable=latchable, initial_latched=initial_latched)
    set_key_button_label(button, label, secondary_label)
    button.setProperty("componentType", "key")
    button.setProperty("componentId", component_id)
    button.setProperty("keyId", key_id)
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
    button.setMinimumHeight(cell_metrics.span_height(1))
    button.setMinimumWidth(cell_metrics.span_width(width))
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    refresh_key_button(button, machine)

    machine.add_listener(lambda _change: refresh_key_button(button, machine))
    if on_state_change is not None:
        machine.add_listener(on_state_change)

    def handle_press() -> None:
        machine.press()
        if on_press is not None:
            on_press()

    def handle_release() -> None:
        if machine.latchable:
            machine.release_and_toggle_latched()
        else:
            machine.release()
        if on_release is not None:
            on_release()

    button.pressed.connect(handle_press)
    button.released.connect(handle_release)
    return KeyButton(button=button, state_machine=machine)
