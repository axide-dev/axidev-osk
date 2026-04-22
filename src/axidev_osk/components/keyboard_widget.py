from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QPushButton, QSizePolicy, QWidget

from ..keyboard_io import AxidevIoKeyboardBackend
from ..layouts.us_iso import NAV_START, build_us_iso_layout
from ..models import KeySpec
from .key_button import create_key_button, set_key_button_label
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
        self._hold_visual_modifiers: set[str] = set()
        self._buttons_by_spec: list[tuple[QPushButton, KeySpec]] = []

        self.setObjectName("keyboard")
        self.setFrameShape(QFrame.Shape.NoFrame)

        container = QGridLayout(self)
        container.setContentsMargins(0, 0, 0, 0)
        container.setHorizontalSpacing(6)
        container.setVerticalSpacing(6)

        specs = build_us_iso_layout()
        function_row_specs = [spec for spec in specs if spec.row == 0]
        body_specs = [spec for spec in specs if spec.row > 0]
        body_column_map = self._build_dense_column_map(body_specs)
        body_column_count = self._count_occupied_columns(body_specs)
        self._add_function_row(
            container,
            function_row_specs,
            body_column_map=body_column_map,
        )
        self._add_body_grid(container, body_specs)

        for column in range(body_column_count):
            container.setColumnStretch(column, 1)

        for row in range(6):
            container.setRowStretch(row, 1)

        self._refresh_key_legends()

    def _build_dense_column_map(self, specs: list[KeySpec]) -> dict[int, int]:
        occupied_columns: set[int] = set()
        for spec in specs:
            column_span = int(spec.width * 4)
            occupied_columns.update(range(spec.column, spec.column + column_span))
        return {
            column: dense_index for dense_index, column in enumerate(sorted(occupied_columns))
        }

    def _count_occupied_columns(self, specs: list[KeySpec]) -> int:
        return len(self._build_dense_column_map(specs))

    def _add_function_row(
        self,
        container: QGridLayout,
        specs: list[KeySpec],
        *,
        body_column_map: dict[int, int],
    ) -> None:
        left_block_specs = [spec for spec in specs if spec.column < NAV_START]
        left_column_map = self._build_dense_column_map(left_block_specs)

        for spec in specs:
            column_span = int(spec.width * 4)
            dense_column = (
                body_column_map[spec.column]
                if spec.column >= NAV_START
                else left_column_map[spec.column]
            )
            container.addWidget(self._build_item(spec), 0, dense_column, spec.height, column_span)

    def _add_body_grid(self, container: QGridLayout, specs: list[KeySpec]) -> None:
        column_map = self._build_dense_column_map(specs)
        for spec in specs:
            column_span = int(spec.width * 4)
            dense_column = column_map[spec.column]
            container.addWidget(self._build_item(spec), spec.row, dense_column, spec.height, column_span)

    def _build_item(self, spec: KeySpec) -> QWidget:
        if spec.is_spacer:
            spacer = QWidget(self)
            spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            spacer.setMinimumWidth(max(56, round(56 * spec.width)))
            spacer.setMinimumHeight((56 * spec.height) + (6 * (spec.height - 1)))
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            return spacer
        return self._build_key(spec)

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
            if spec.holds_when_latched:
                self._hold_visual_modifiers.add(spec.key_id)
            state_machine.add_listener(
                lambda change, key_spec=spec, key_id=spec.key_id, machine=state_machine, press_ref=active_press: self._handle_latch_state_change(
                    key_spec,
                    key_id,
                    machine,
                    change,
                    press_ref,
                )
            )
            self._latch_groups.setdefault(spec.key_id, []).append(state_machine)

        display = spec.resolve_display(self._active_display_modifiers())
        button = create_key_button(
            display.label,
            state_machine=state_machine,
            width=spec.width,
            secondary_label=display.secondary_label,
            key_id=spec.key_id,
            on_press=on_press,
            on_release=on_release,
        )
        if spec.height > 1:
            button.setMinimumHeight((56 * spec.height) + (6 * (spec.height - 1)))

        self._buttons_by_spec.append((button, spec))
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
        self._refresh_key_legends()

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
        active_press: list[object | None],
    ) -> None:
        if spec.holds_when_latched and change.reason != "release":
            self._refresh_key_legends()

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

        active_press[0] = self._keyboard_backend.sync_latched_key(
            spec,
            currently_latched,
            active_press[0],
        )

        self._syncing_latch_keys.add(key_id)
        try:
            for sibling in self._latch_groups.get(key_id, []):
                if sibling is state_machine:
                    continue
                sibling.set_latched(currently_latched, reason="sync_group")
        finally:
            self._syncing_latch_keys.discard(key_id)

        self._refresh_key_legends()

    def _active_display_modifiers(self) -> frozenset[str]:
        active = {key_id for key_id, latched in self._latched_keys.items() if latched}
        for key_id in self._hold_visual_modifiers:
            if any(machine.is_pressed for machine in self._latch_groups.get(key_id, [])):
                active.add(key_id)
        return frozenset(active)

    def _refresh_key_legends(self) -> None:
        active_modifiers = self._active_display_modifiers()
        for button, spec in self._buttons_by_spec:
            display = spec.resolve_display(active_modifiers)
            set_key_button_label(button, display.label, display.secondary_label)
