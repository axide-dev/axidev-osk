from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from typing import ClassVar, Iterator

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QPushButton, QWidget

from ...config.models import GridConfig, KeyConfig, LayoutConfig
from ...config.defaults.us_iso import build_us_iso_layout_config
from ...models import KeySpec
from ...runtime.commands import KeyboardKeyDown, KeyboardKeyUp, KeyboardSyncLatchedKey, StateSet
from ...runtime.context import Context
from ...runtime.events import ComponentPressed, ComponentReleased, ComponentStateChanged
from ...services.keyboard import KeyboardService
from ..button.key import create_key_button, key_button_state_machine, set_key_button_label
from ..button.state import KeyInteractionState, KeyStateChange, KeyStateMachine
from .metrics import DEFAULT_KEYBOARD_METRICS

Unsubscribe = Callable[[], None]


class _KeyStateBridge(QObject):
    key_state_changed = Signal(str, bool)


class KeyboardWidget(QFrame):
    """Keyboard grid component built from declarative layout data."""

    _current_builder: ClassVar["KeyboardWidget | None"] = None

    def __init__(
        self,
        keyboard: object | None = None,
        *,
        layout_config: LayoutConfig | None = None,
        context: Context | None = None,
    ) -> None:
        super().__init__()
        self._metrics = DEFAULT_KEYBOARD_METRICS
        self._context = context
        self._keyboard = keyboard or (context.keyboard if context is not None else None)
        if self._keyboard is None:
            raise ValueError("KeyboardWidget requires a keyboard service or runtime context")
        self._layout_config = layout_config or build_us_iso_layout_config()
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
        self._state_machines_by_key_name: dict[str, list[KeyStateMachine]] = {}
        self._key_state_bridge = _KeyStateBridge(self)
        self._key_state_unsubscribe: Unsubscribe | None = None

        self.setObjectName("keyboard")
        self.setProperty("componentType", "grid")
        self.setProperty("componentId", self._layout_config.id)
        self.setProperty("layout", self._layout_config.name)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._subscribe_to_backend_key_state()

        container = QGridLayout(self)
        container.setContentsMargins(0, 0, 0, 0)
        container.setHorizontalSpacing(self._metrics.grid_gap_px)
        container.setVerticalSpacing(self._metrics.grid_gap_px)

        for grid in self._layout_config.grids:
            body_column_count = self._add_grid(container, grid)

            for column in range(body_column_count):
                container.setColumnStretch(column, 1)

            for row in range(grid.body_row_count):
                container.setRowStretch(row, 1)

        self._refresh_key_legends()
        self.destroyed.connect(lambda _object=None: self._unsubscribe_from_backend_key_state())

    @classmethod
    def current_builder(cls) -> "KeyboardWidget | None":
        """Return the keyboard widget currently building registry components."""

        return cls._current_builder

    @contextmanager
    def _builder_scope(self) -> Iterator[None]:
        previous = type(self)._current_builder
        type(self)._current_builder = self
        try:
            yield
        finally:
            type(self)._current_builder = previous

    def _add_grid(self, container: QGridLayout, grid: GridConfig) -> int:
        function_components = [component for component in grid.components if component.spec.row == 0]
        body_components = [component for component in grid.components if component.spec.row > 0]
        body_column_map = self._build_dense_column_map([component.spec for component in body_components])
        body_column_count = self._count_occupied_columns([component.spec for component in body_components])
        with self._builder_scope():
            self._add_function_row(
                container,
                function_components,
                nav_start_column=grid.nav_start_column,
                body_column_map=body_column_map,
            )
            self._add_body_grid(container, body_components)
        return body_column_count

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
        components: list[KeyConfig],
        *,
        nav_start_column: int,
        body_column_map: dict[int, int],
    ) -> None:
        left_block_specs = [component.spec for component in components if component.spec.column < nav_start_column]
        left_column_map = self._build_dense_column_map(left_block_specs)

        for component in components:
            spec = component.spec
            column_span = int(spec.width * 4)
            dense_column = (
                body_column_map[spec.column]
                if spec.column >= nav_start_column
                else left_column_map[spec.column]
            )
            container.addWidget(self._build_item(component), 0, dense_column, spec.height, column_span)

    def _add_body_grid(self, container: QGridLayout, components: list[KeyConfig]) -> None:
        column_map = self._build_dense_column_map([component.spec for component in components])
        for component in components:
            spec = component.spec
            column_span = int(spec.width * 4)
            dense_column = column_map[spec.column]
            container.addWidget(self._build_item(component), spec.row, dense_column, spec.height, column_span)

    def _build_item(self, component: KeyConfig) -> QWidget:
        if self._context is not None:
            widget = self._context.components.build(component, self._context)
        else:
            widget = self.build_key_from_config(component, None)
        widget.setParent(self)
        return widget

    def build_key_from_config(self, config: KeyConfig, context: Context | None) -> QPushButton:
        """Build a key button from config inside the keyboard builder scope."""

        del context
        return self._build_key(config.spec, component_id=config.id)

    def _build_key(self, spec: KeySpec, *, component_id: str) -> QPushButton:
        active_press: list[object | None] = [None]
        latched = bool(spec.key_id is not None and self._latched_keys.get(spec.key_id, False))
        state_machine: KeyStateMachine | None = None
        listened_key_name = self._listened_key_name(spec)

        def on_press(key_spec: KeySpec = spec) -> None:
            active_press[0] = self._handle_key_press(component_id, key_spec)

        def on_release() -> None:
            self._handle_key_release(component_id, active_press[0])
            active_press[0] = None

        def on_state_change(
            change: KeyStateChange,
            key_spec: KeySpec = spec,
            key_id: str | None = spec.key_id,
            press_ref: list[object | None] = active_press,
        ) -> None:
            if key_id is None:
                return
            self._handle_latch_state_change(
                component_id,
                key_spec,
                key_id,
                key_button_state_machine(button),
                change,
                press_ref,
            )

        display = spec.resolve_display(self._active_display_modifiers())
        button = create_key_button(
            display.label,
            latchable=spec.latchable,
            initial_latched=latched,
            on_state_change=on_state_change if spec.latchable and spec.key_id is not None else None,
            component_id=component_id,
            width=spec.width,
            secondary_label=display.secondary_label,
            key_id=spec.key_id,
            io_key=spec.io_key,
            profile="default",
            layout=self._layout_config.name,
            on_press=on_press,
            on_release=on_release,
        )
        state_machine = key_button_state_machine(button)
        if listened_key_name is not None:
            self._state_machines_by_key_name.setdefault(listened_key_name, []).append(state_machine)
            if self._keyboard.is_key_down(listened_key_name):
                state_machine.set_pressed(True, reason="listener_snapshot")
        if spec.latchable and spec.key_id is not None:
            if spec.holds_when_latched:
                self._hold_visual_modifiers.add(spec.key_id)
            self._latch_groups.setdefault(spec.key_id, []).append(state_machine)
        if listened_key_name is not None:
            button.setProperty("ioKeyName", listened_key_name)
        if spec.height > 1:
            button.setMinimumHeight(self._metrics.span_height(spec.height))

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

    def _handle_key_press(self, component_id: str, spec: KeySpec) -> object | None:
        self._dispatch_event(ComponentPressed(component_id=component_id, key_spec=spec))
        if self._context is not None:
            return self._context.dispatcher.dispatch_command(KeyboardKeyDown(spec, dict(self._latched_keys)))
        return self._keyboard.key_down(spec, self._latched_keys)

    def _handle_key_release(self, component_id: str, active_press: object | None) -> None:
        self._dispatch_event(ComponentReleased(component_id=component_id, active_press=active_press))
        if self._context is not None:
            self._context.dispatcher.dispatch_command(KeyboardKeyUp(active_press))
            return
        self._keyboard.key_up(active_press)

    def _handle_backend_key_state_change(self, key_name: str, pressed: bool) -> None:
        for state_machine in self._state_machines_by_key_name.get(key_name, []):
            state_machine.set_pressed(pressed, reason="listener")

    def _listened_key_name(self, spec: KeySpec) -> str | None:
        return self._keyboard.key_name_for_spec(spec)

    def _subscribe_to_backend_key_state(self) -> None:
        self._key_state_bridge.key_state_changed.connect(self._handle_backend_key_state_change)
        self._key_state_unsubscribe = self._keyboard.add_key_state_listener(
            self._key_state_bridge.key_state_changed.emit
        )

    def _unsubscribe_from_backend_key_state(self) -> None:
        if self._key_state_unsubscribe is None:
            return
        self._key_state_unsubscribe()
        self._key_state_unsubscribe = None

    def _handle_latch_state_change(
        self,
        component_id: str,
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
        self._dispatch_event(ComponentStateChanged(component_id=component_id, key_id=key_id, latched=currently_latched))
        self._dispatch_command(StateSet(namespace=f"component:{component_id}", key="latched", value=currently_latched))
        if key_id in self._syncing_latch_keys:
            return

        command = KeyboardSyncLatchedKey(spec, currently_latched, active_press[0])
        if self._context is not None:
            active_press[0] = self._context.dispatcher.dispatch_command(command)
        else:
            active_press[0] = self._keyboard.sync_latched_key(spec, currently_latched, active_press[0])

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

    def _dispatch_event(self, event: object) -> None:
        if self._context is not None:
            self._context.dispatcher.dispatch_event(event)  # type: ignore[arg-type]

    def _dispatch_command(self, command: object) -> object | None:
        if self._context is None:
            return None
        return self._context.dispatcher.dispatch_command(command)  # type: ignore[arg-type]
