from __future__ import annotations

from PySide6.QtWidgets import QFrame, QGridLayout, QPushButton

from ..keyboard_io import AxidevIoKeyboardBackend
from ..layouts.us_iso import build_us_iso_layout
from ..models import KeySpec
from .key_button import create_key_button
from .key_state_machine import KeyInteractionState, KeyStateChange, KeyStateMachine


class KeyboardWidget(QFrame):
    def __init__(self, keyboard_backend: AxidevIoKeyboardBackend) -> None:
        super().__init__()
        self._keyboard_backend = keyboard_backend
        self._latched_keys: dict[str, bool] = {
            "shift": False,
            "caps": False,
            "ctrl": False,
            "alt": False,
            "altgr": False,
            "super": False,
        }
        self._latch_groups: dict[str, list[KeyStateMachine]] = {
            "shift": [],
            "caps": [],
            "ctrl": [],
            "alt": [],
            "altgr": [],
            "super": [],
        }
        self._syncing_latch_keys: set[str] = set()

        self.setObjectName("keyboard")
        self.setFrameShape(QFrame.Shape.NoFrame)

        container = QGridLayout(self)
        container.setContentsMargins(18, 18, 18, 18)
        container.setHorizontalSpacing(4)
        container.setVerticalSpacing(8)

        specs = build_us_iso_layout()
        max_column = 0
        max_row = 0

        for spec in specs:
            button = self._build_key(spec)
            column_span = int(spec.width * 4)
            container.addWidget(button, spec.row, spec.column, spec.height, column_span)
            max_column = max(max_column, spec.column + column_span)
            max_row = max(max_row, spec.row + spec.height)

        for column in range(max_column):
            container.setColumnStretch(column, 1)
            container.setColumnMinimumWidth(column, 10)

        for row in range(max_row):
            container.setRowStretch(row, 1)

    def _build_key(self, spec: KeySpec) -> QPushButton:
        active_press: list[object | None] = [None]
        latched = bool(spec.key_id is not None and self._latched_keys.get(spec.key_id, False))
        state_machine = KeyStateMachine(latchable=spec.latchable, initial_latched=latched)

        def on_press(key_spec: KeySpec = spec) -> None:
            active_press[0] = self._handle_key_press(key_spec)

        def on_release() -> None:
            self._handle_key_release(active_press[0])
            active_press[0] = None

        if spec.latchable and spec.key_id is not None:
            state_machine.add_listener(
                lambda change, key_spec=spec, key_id=spec.key_id, machine=state_machine: self._handle_latch_state_change(
                    key_spec,
                    key_id,
                    machine,
                    change,
                )
            )
            self._latch_groups.setdefault(spec.key_id, []).append(state_machine)

        button = create_key_button(
            spec.label,
            state_machine=state_machine,
            width=spec.width,
            secondary_label=spec.secondary_label,
            key_id=spec.key_id,
            on_press=on_press,
            on_release=on_release,
        )
        if spec.height > 1:
            button.setMinimumHeight((56 * spec.height) + (8 * (spec.height - 1)))

        return button

    def set_latched_state(self, key_id: str, latched: bool) -> None:
        self._latched_keys[key_id] = latched
        if key_id in self._syncing_latch_keys:
            return

        self._syncing_latch_keys.add(key_id)
        try:
            for state_machine in self._latch_groups.get(key_id, []):
                state_machine.set_latched(latched, reason="sync_group")
        finally:
            self._syncing_latch_keys.discard(key_id)

    def _handle_key_press(self, spec: KeySpec) -> object | None:
        return self._keyboard_backend.key_down(spec, self._latched_keys)

    def _handle_key_release(self, active_press: object | None) -> None:
        self._keyboard_backend.key_up(active_press)

    def _handle_latch_state_change(
        self,
        spec: KeySpec,
        key_id: str,
        state_machine: KeyStateMachine,
        change: KeyStateChange,
    ) -> None:
        previously_latched = change.previous in {
            KeyInteractionState.LATCHED,
            KeyInteractionState.LATCHED_PRESSED,
        }
        currently_latched = change.current in {
            KeyInteractionState.LATCHED,
            KeyInteractionState.LATCHED_PRESSED,
        }

        if previously_latched == currently_latched:
            return

        self._latched_keys[key_id] = currently_latched
        if key_id in self._syncing_latch_keys:
            return

        self._keyboard_backend.sync_latched_key(spec, currently_latched)

        self._syncing_latch_keys.add(key_id)
        try:
            for sibling in self._latch_groups.get(key_id, []):
                if sibling is state_machine:
                    continue
                sibling.set_latched(currently_latched, reason="sync_group")
        finally:
            self._syncing_latch_keys.discard(key_id)
