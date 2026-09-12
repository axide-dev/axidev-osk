"""Keyboard grid widget that builds key buttons from declarative layout config."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QSizePolicy, QWidget

from ...config.models import GridConfig, KeyConfig, LayoutConfig
from ...models import KeySpec
from ...runtime.commands import KeyboardKeyDown, KeyboardRegisterKeySpec, KeyboardKeyUp, KeyboardSyncLatchedKey, StateSet
from ...runtime.context import Context
from ...runtime.diagnostics import keyboard_debug_enabled
from ...runtime.events import BackendKeyRegistered, BackendKeyStateChanged, ComponentPressed, ComponentReleased, ComponentStateChanged, KeyLatchChanged
from ...runtime.identity import component_state_namespace, keyboard_key_states_namespace, keyboard_latches_namespace, window_state_namespace
from ..button import Button, ButtonInteractionState
from .metrics import KeyboardMetrics

Unsubscribe = Callable[[], None]

_logger = logging.getLogger(__name__)


class _KeyStateBridge(QObject):
    """Qt signal relay used to marshal backend key-state callbacks into the GUI thread."""

    key_state_changed = Signal(str, str, bool, bool)
    key_latch_changed = Signal(str, str, bool)
    key_registered = Signal(str, str, object)


class KeyboardWidget(QFrame):
    """Keyboard grid component built from declarative layout data.

    The widget is a reusable composition primitive: it accepts a ``LayoutConfig``
    and uses the runtime ``Context`` (when present) to dispatch commands and
    events through the central runtime instead of calling backend services
    directly.

    A ``KeyboardWidget`` does not know about any specific bundled layout. Callers
    that want the default Axidev US ISO layout must build a ``LayoutConfig`` via
    the bundled config layer (``config.defaults``) and pass it in.
    """

    def __init__(
        self,
        *,
        layout_config: LayoutConfig,
        context: Context,
        metrics: KeyboardMetrics | None = None,
    ) -> None:
        """Construct a keyboard grid populated from layout data.

        Args:
            layout_config: Declarative layout describing grids, keys, and
                spacers. Required so the widget never embeds a default layout.
            context: Runtime context that owns the keyboard service,
                dispatcher, and state store. All backend interaction and
                event dispatch flow through it. Tests should build a
                context via ``axidev_osk.runtime.testing.make_test_context``.
            metrics: Pixel metrics applied to keys in this grid. When
                omitted, defaults to ``KeyboardMetrics()``.

        Returns:
            None.

        Side effects:
            Builds child widgets and subscribes to the keyboard service for
            live key state changes.
        """

        super().__init__()
        self._metrics = metrics or KeyboardMetrics()
        self._context = context
        self._layout_config = layout_config
        self._latch_groups: dict[str, list[Button]] = {
            "shift": [],
            "caps": [],
            "ctrl": [],
            "alt": [],
            "altgr": [],
            "super": [],
        }
        self._syncing_latch_keys: set[str] = set()
        self._hold_visual_modifiers: set[str] = set()
        self._buttons_by_spec: list[tuple[Button, KeySpec]] = []
        self._buttons_by_component_id: dict[str, Button] = {}
        self._buttons_by_key_id: dict[str, list[Button]] = {}
        self._key_state_bridge = _KeyStateBridge(self)
        self._event_unsubscribe: Unsubscribe | None = None

        self.setObjectName("keyboard")
        self.setProperty("componentType", "grid")
        self.setProperty("componentId", self._layout_config.id)
        self.setProperty("layout", self._layout_config.id)
        self.setProperty("layoutName", self._layout_config.name)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._subscribe_to_runtime_key_state()

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
        self.destroyed.connect(lambda _object=None: self._unsubscribe_from_runtime_key_state())

    @property
    def key_metrics(self) -> KeyboardMetrics:
        """Return metrics inherited by child key and spacer builders."""

        return self._metrics

    def _add_grid(self, container: QGridLayout, grid: GridConfig) -> int:
        """Place a single grid's components into the Qt container.

        Args:
            container: Target ``QGridLayout``.
            grid: Grid DTO containing keys/spacers and metadata.

        Returns:
            The number of dense body columns produced; used by the caller to
            apply column stretch.

        Side effects:
            Adds child widgets to the container.
        """

        function_components = [component for component in grid.components if component.spec.row == 0]
        body_components = [component for component in grid.components if component.spec.row > 0]
        body_column_map = self._build_dense_column_map([component.spec for component in body_components])
        body_column_count = self._count_occupied_columns([component.spec for component in body_components])
        self._add_function_row(
            container,
            function_components,
            nav_start_column=grid.nav_start_column,
            body_column_map=body_column_map,
        )
        self._add_body_grid(container, body_components)
        return body_column_count

    def _build_dense_column_map(self, specs: list[KeySpec]) -> dict[int, int]:
        """Compute dense column indices for a sparse component column layout.

        Args:
            specs: Specs whose ``column`` and ``width`` define occupied cells.

        Returns:
            Mapping from sparse column index to dense column index.

        Side effects:
            None.
        """

        occupied_columns: set[int] = set()
        for spec in specs:
            column_span = int(spec.width * 4)
            occupied_columns.update(range(spec.column, spec.column + column_span))
        return {
            column: dense_index for dense_index, column in enumerate(sorted(occupied_columns))
        }

    def _count_occupied_columns(self, specs: list[KeySpec]) -> int:
        """Count how many dense columns the supplied specs occupy."""

        return len(self._build_dense_column_map(specs))

    def _add_function_row(
        self,
        container: QGridLayout,
        components: list[KeyConfig],
        *,
        nav_start_column: int,
        body_column_map: dict[int, int],
    ) -> None:
        """Place row-0 (function row) components.

        Args:
            container: Target Qt grid layout.
            components: Function-row components to place.
            nav_start_column: Sparse column where the navigation block begins.
            body_column_map: Dense column map produced from the body rows; the
                navigation block is aligned against the body so the function
                row sits visually correctly above it.

        Returns:
            None.

        Side effects:
            Adds child widgets to the container.
        """

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
        """Place body-row components using a dense column map."""

        column_map = self._build_dense_column_map([component.spec for component in components])
        for component in components:
            spec = component.spec
            column_span = int(spec.width * 4)
            dense_column = column_map[spec.column]
            container.addWidget(self._build_item(component), spec.row, dense_column, spec.height, column_span)

    def _build_item(self, component: KeyConfig) -> QWidget:
        """Build one child widget for the grid via the component registry.

        The keyboard widget passes itself as the explicit ``host`` so the
        key builder can wire latch state through this grid.

        Args:
            component: Key or spacer config to materialize.

        Returns:
            Constructed Qt widget reparented to this grid.

        Side effects:
            Reparents the widget under this grid.
        """

        widget = self._context.components.build(component, self._context, host=self)
        widget.setParent(self)
        return widget

    def build_key_from_config(self, config: KeyConfig, context: Context) -> Button:
        """Build a key button from config inside this grid's latch wiring.

        Args:
            config: Key component config.
            context: Unused; accepted for symmetry with builder signatures.

        Returns:
            Constructed key button.

        Side effects:
            Registers the new button with this grid's latch and listener
            bookkeeping.
        """

        del context
        return self._build_key(config.spec, component_id=config.id)

    def _build_key(self, spec: KeySpec, *, component_id: str) -> Button:
        """Construct a single key button and wire it into the grid's state.

        Args:
            spec: Keyboard key spec describing label, modifiers, and layout
                placement.
            component_id: Deterministic ID for the resulting key.

        Returns:
            The constructed shared ``Button``.

        Side effects:
            Registers the button's state machine in latch groups and listener
            tables so live key state can drive its visual state.
        """

        if spec.action is not None and spec.action.kind == "set-dwell-enabled":
            target_config = next(
                window
                for window in self._context.config.windows
                if window.id == spec.action.target_window_id
            )
            latched = bool(
                self._context.state.get(
                    window_state_namespace(target_config.id),
                    "dwell_enabled",
                    target_config.dwell_click.enabled,
                )
            )
        else:
            latched = bool(
                spec.key_id is not None
                and self._context.state.get(
                    self._latch_namespace(),
                    spec.key_id,
                    False,
                )
            )
        state_key = self._state_key_for_spec(spec)

        def on_press(key_spec: KeySpec = spec) -> None:
            self._handle_key_press(component_id, key_spec)

        def on_release(key_spec: KeySpec = spec) -> None:
            self._handle_key_release(component_id, key_spec)

        def on_state_change(
            previous: ButtonInteractionState,
            current: ButtonInteractionState,
            reason: str,
            key_spec: KeySpec = spec,
            key_id: str | None = spec.key_id,
        ) -> None:
            if key_id is None and key_spec.action is None:
                return
            self._handle_latch_state_change(
                component_id,
                key_spec,
                key_id,
                button,
                previous,
                current,
                reason,
            )

        display = spec.resolve_display(self._active_display_modifiers())
        button = Button(
            display.label,
            component_id=component_id,
            component_type="key",
            latchable=spec.latchable,
            initial_latched=latched,
        )
        button.set_label(display.label, display.secondary_label)
        button.setProperty("keyId", spec.key_id)
        button.setProperty("ioKey", spec.io_key)
        button.setProperty("profile", "default")
        button.setProperty("layout", self._layout_config.id)
        button.setProperty("keyWidth", spec.width)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setMinimumHeight(self._metrics.span_height(1))
        button.setMinimumWidth(self._metrics.span_width(spec.width))
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if spec.latchable and (spec.key_id is not None or spec.action is not None):
            button.stateChanged.connect(on_state_change)
        button.pressed.connect(on_press)
        button.released.connect(on_release)
        if state_key is not None:
            self._buttons_by_key_id.setdefault(state_key, []).append(button)
            snapshot = self._context.state.get(self._key_states_namespace(), state_key, {})
            if isinstance(snapshot, dict):
                button.set_pressed(bool(snapshot.get("pressed", False)), reason="store_snapshot")
            if spec.key_id is not None:
                button.set_latched(bool(self._context.state.get(self._latch_namespace(), spec.key_id, False)), reason="store_snapshot")
        if spec.latchable and spec.key_id is not None:
            if spec.holds_when_latched:
                self._hold_visual_modifiers.add(spec.key_id)
            self._latch_groups.setdefault(spec.key_id, []).append(button)
        if spec.height > 1:
            button.setMinimumHeight(self._metrics.span_height(spec.height))

        self._buttons_by_spec.append((button, spec))
        self._buttons_by_component_id[component_id] = button
        if spec.action is None:
            self._dispatch_command(KeyboardRegisterKeySpec(self._layout_config.id, component_id, spec))
        return button

    def _handle_key_press(self, component_id: str, spec: KeySpec) -> None:
        """Dispatch a press event/command through the runtime."""

        self._dispatch_event(ComponentPressed(component_id=component_id, key_spec=spec))
        if spec.action is None and not spec.holds_when_latched:
            self._context.dispatcher.dispatch_command(KeyboardKeyDown(self._layout_config.id, spec, component_id))

    def _handle_key_release(self, component_id: str, spec: KeySpec) -> None:
        """Dispatch a release event/command through the runtime."""

        self._dispatch_event(ComponentReleased(component_id=component_id))
        if spec.action is None and not spec.holds_when_latched:
            self._context.dispatcher.dispatch_command(KeyboardKeyUp(self._layout_config.id, spec, component_id))

    def _handle_key_registered(self, layout_id: str, component_id: str, io_key_name: object) -> None:
        """Apply backend registration metadata returned through runtime events."""

        if layout_id != self._layout_config.id or not isinstance(io_key_name, str):
            return
        button = self._buttons_by_component_id.get(component_id)
        if button is not None:
            button.setProperty("ioKeyName", io_key_name)

    def _handle_backend_key_state_change(self, layout_id: str, key_id: str, pressed: bool, latched: bool) -> None:
        """Apply a backend key state change to all matching button state machines."""

        if layout_id != self._layout_config.id:
            return
        for button in self._buttons_by_key_id.get(key_id, []):
            button.set_pressed(pressed and not latched, reason="listener")
            button.set_latched(latched, reason="listener")

    def _handle_key_latch_change(self, layout_id: str, key_id: str, latched: bool) -> None:
        """Apply a latch state change from the runtime store."""

        if layout_id != self._layout_config.id:
            return
        self._syncing_latch_keys.add(key_id)
        try:
            for button in self._latch_groups.get(key_id, []):
                button.set_latched(latched, reason="store_event")
        finally:
            self._syncing_latch_keys.discard(key_id)
        self._refresh_key_legends()

    def _subscribe_to_runtime_key_state(self) -> None:
        """Subscribe the grid to runtime key state events via signal bridges."""

        self._key_state_bridge.key_state_changed.connect(self._handle_backend_key_state_change)
        self._key_state_bridge.key_latch_changed.connect(self._handle_key_latch_change)
        self._key_state_bridge.key_registered.connect(self._handle_key_registered)

        def handle_event(event: object) -> None:
            if isinstance(event, BackendKeyRegistered):
                self._key_state_bridge.key_registered.emit(event.layout_id, event.component_id, event.io_key_name)
            elif isinstance(event, BackendKeyStateChanged):
                self._key_state_bridge.key_state_changed.emit(event.layout_id, event.key_id, event.pressed, event.latched)
            elif isinstance(event, KeyLatchChanged):
                self._key_state_bridge.key_latch_changed.emit(event.layout_id, event.key_id, event.latched)

        self._event_unsubscribe = self._context.dispatcher.add_event_handler(handle_event)

    def _unsubscribe_from_runtime_key_state(self) -> None:
        """Detach runtime event handling when the widget is destroyed."""

        if self._event_unsubscribe is None:
            return
        self._event_unsubscribe()
        self._event_unsubscribe = None

    def _handle_latch_state_change(
        self,
        component_id: str,
        spec: KeySpec,
        key_id: str | None,
        button: Button,
        previous: ButtonInteractionState,
        current: ButtonInteractionState,
        reason: str,
    ) -> None:
        """Update grid-wide latch state when a button transitions latch state.

        Args:
            component_id: Stable key component ID.
            spec: Key spec being toggled.
            key_id: Modifier identity string for the key.
            button: Button that initiated the change.
            previous: Interaction state before the change.
            current: Interaction state after the change.
            reason: Source of the state transition.
        Returns:
            None.

        Side effects:
            Updates latched-key registry, dispatches state events/commands,
            and synchronizes sibling latch buttons in the same group.
        """

        if reason in {"sync_group", "store_snapshot", "store_event", "listener"}:
            if spec.holds_when_latched:
                self._refresh_key_legends()
            return

        if spec.holds_when_latched and keyboard_debug_enabled():
            _logger.info(
                "keyboard modifier state: component_id=%r, key_id=%r, reason=%r, previous=%r, current=%r",
                component_id,
                key_id,
                reason,
                previous.value,
                current.value,
            )

        previously_latched = previous in {
            ButtonInteractionState.LATCHED,
            ButtonInteractionState.LATCHED_PRESSED,
        }
        currently_latched = current in {
            ButtonInteractionState.LATCHED,
            ButtonInteractionState.LATCHED_PRESSED,
        }

        if spec.action is not None:
            if previously_latched != currently_latched:
                self._dispatch_event(
                    ComponentStateChanged(
                        component_id=component_id,
                        key_id=None,
                        latched=currently_latched,
                        key_spec=spec,
                    )
                )
            return

        if key_id is None:
            return
        if previously_latched != currently_latched:
            self._dispatch_event(
                ComponentStateChanged(
                    component_id=component_id,
                    key_id=key_id,
                    latched=currently_latched,
                )
            )
            self._dispatch_command(StateSet(namespace=component_state_namespace(component_id), key="latched", value=currently_latched))
            if key_id not in self._syncing_latch_keys:
                self._dispatch_command(KeyboardSyncLatchedKey(self._layout_config.id, spec, currently_latched, component_id))

                self._syncing_latch_keys.add(key_id)
                try:
                    for sibling in self._latch_groups.get(key_id, []):
                        if sibling is button:
                            continue
                        sibling.set_latched(currently_latched, reason="sync_group")
                finally:
                    self._syncing_latch_keys.discard(key_id)

        if spec.holds_when_latched:
            if not previous.is_active and current.is_active:
                self._dispatch_command(KeyboardKeyDown(self._layout_config.id, spec, component_id))
            elif previous.is_active and not current.is_active:
                self._dispatch_command(KeyboardKeyUp(self._layout_config.id, spec, component_id))

        if previously_latched != currently_latched or spec.holds_when_latched:
            self._refresh_key_legends()

    def _active_display_modifiers(self) -> frozenset[str]:
        """Return the set of modifier IDs that should affect key display."""

        active = {key_id for key_id in self._latch_groups if self._context.state.get(self._latch_namespace(), key_id, False)}
        for key_id in self._hold_visual_modifiers:
            if any(machine.is_pressed for machine in self._latch_groups.get(key_id, [])):
                active.add(key_id)
        return frozenset(active)

    def _refresh_key_legends(self) -> None:
        """Recompute every button's primary/secondary label from active modifiers."""

        active_modifiers = self._active_display_modifiers()
        for button, spec in self._buttons_by_spec:
            display = spec.resolve_display(active_modifiers)
            button.set_label(display.label, display.secondary_label)

    def _dispatch_event(self, event: object) -> None:
        """Forward an event to the runtime dispatcher."""

        self._context.dispatcher.dispatch_event(event)  # type: ignore[arg-type]

    def _dispatch_command(self, command: object) -> None:
        """Forward a fire-and-forget command to the runtime dispatcher."""

        self._context.dispatcher.dispatch_command(command)  # type: ignore[arg-type]

    def _state_key_for_spec(self, spec: KeySpec) -> str | None:
        if spec.action is not None:
            return None
        return spec.io_key or spec.label or spec.key_id

    def _latch_namespace(self) -> str:
        return keyboard_latches_namespace(self._layout_config.id)

    def _key_states_namespace(self) -> str:
        return keyboard_key_states_namespace(self._layout_config.id)
