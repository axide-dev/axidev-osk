"""Visual keyboard grid built from layout config and runtime snapshots."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QPushButton, QWidget

from ...config.models import GridConfig, KeyConfig, LayoutConfig, SpacerConfig
from ...messages import MessageResult
from ...models import KeyVisual, SpacerVisual
from ...runtime.context import Context
from ...runtime.events import (
    STATE_CHANGED,
    StateChangedArguments,
    component_pressed,
    component_released,
)
from ...runtime.source import SourcePath
from ..button.key import create_key_button, render_key_button_state, set_key_button_label
from .metrics import KeyboardMetrics

Unsubscribe = Callable[[], None]
GridVisual = KeyVisual | SpacerVisual


class _KeyStateBridge(QObject):
    state_changed = Signal(object, object)


class KeyboardWidget(QFrame):
    """Place visual keys and render state owned by the main runtime."""

    def __init__(
        self,
        *,
        layout_config: LayoutConfig,
        context: Context,
        source_path: SourcePath,
        metrics: KeyboardMetrics | None = None,
    ) -> None:
        super().__init__()
        self._metrics = metrics or KeyboardMetrics()
        self._context = context
        self._layout_config = layout_config
        self._source_path = source_path
        self._layout_path = source_path.child("layout", layout_config.id)
        self._active_state_tags = self._read_layout_tags()
        self._buttons_by_source: dict[SourcePath, QPushButton] = {}
        self._buttons_by_visual: list[tuple[QPushButton, KeyVisual]] = []
        self._state_bridge = _KeyStateBridge(self)
        self._event_unsubscribes: list[Unsubscribe] = []

        self.setObjectName("keyboard")
        self.setProperty("componentType", "grid")
        self.setProperty("componentId", source_path.segments[-1].id)
        self.setProperty("layout", layout_config.id)
        self.setProperty("layoutName", layout_config.name)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._subscribe_to_runtime_state()

        container = QGridLayout(self)
        container.setContentsMargins(0, 0, 0, 0)
        container.setHorizontalSpacing(self._metrics.grid_gap_px)
        container.setVerticalSpacing(self._metrics.grid_gap_px)
        for grid in layout_config.grids:
            body_column_count = self._add_grid(container, grid)
            for column in range(body_column_count):
                container.setColumnStretch(column, 1)
            for row in range(grid.body_row_count):
                container.setRowStretch(row, 1)

        self._refresh_key_legends()
        self.destroyed.connect(lambda _object=None: self._unsubscribe_from_runtime_state())

    @property
    def key_metrics(self) -> KeyboardMetrics:
        return self._metrics

    def build_key_from_config(
        self,
        config: KeyConfig,
        context: Context,
        source_path: SourcePath,
    ) -> QPushButton:
        del context
        visual = config.visual
        display = visual.resolve_display(self._active_state_tags)
        button = create_key_button(
            display.label,
            component_id=config.id,
            width=visual.width,
            secondary_label=display.secondary_label,
            profile=self._context.config.active_profile_id,
            layout=self._layout_config.id,
            on_press=lambda: self._context.dispatcher.dispatch_event(
                component_pressed(source_path)
            ),
            on_release=lambda: self._context.dispatcher.dispatch_event(
                component_released(source_path)
            ),
            metrics=self._metrics,
        )
        if visual.height > 1:
            button.setMinimumHeight(self._metrics.span_height(visual.height))
        render_key_button_state(button, self._context.behaviors.state_snapshot(source_path))
        self._buttons_by_source[source_path] = button
        self._buttons_by_visual.append((button, visual))
        return button

    def _add_grid(self, container: QGridLayout, grid: GridConfig) -> int:
        grid_path = self._layout_path.child("grid", grid.id)
        function_components = [component for component in grid.components if component.visual.row == 0]
        body_components = [component for component in grid.components if component.visual.row > 0]
        body_column_map = self._build_dense_column_map(
            [component.visual for component in body_components]
        )
        body_column_count = len(body_column_map)
        self._add_function_row(
            container,
            function_components,
            grid_path=grid_path,
            nav_start_column=grid.nav_start_column,
            body_column_map=body_column_map,
        )
        self._add_body_grid(container, body_components, grid_path)
        return body_column_count

    def _build_dense_column_map(self, visuals: list[GridVisual]) -> dict[int, int]:
        occupied_columns: set[int] = set()
        for visual in visuals:
            column_span = int(visual.width * 4)
            occupied_columns.update(range(visual.column, visual.column + column_span))
        return {
            column: dense_index
            for dense_index, column in enumerate(sorted(occupied_columns))
        }

    def _add_function_row(
        self,
        container: QGridLayout,
        components: list[KeyConfig | SpacerConfig],
        *,
        grid_path: SourcePath,
        nav_start_column: int,
        body_column_map: dict[int, int],
    ) -> None:
        left_block = [
            component.visual
            for component in components
            if component.visual.column < nav_start_column
        ]
        left_column_map = self._build_dense_column_map(left_block)
        for component in components:
            visual = component.visual
            column_span = int(visual.width * 4)
            dense_column = (
                body_column_map[visual.column]
                if visual.column >= nav_start_column
                else left_column_map[visual.column]
            )
            container.addWidget(
                self._build_item(component, grid_path),
                0,
                dense_column,
                visual.height,
                column_span,
            )

    def _add_body_grid(
        self,
        container: QGridLayout,
        components: list[KeyConfig | SpacerConfig],
        grid_path: SourcePath,
    ) -> None:
        column_map = self._build_dense_column_map(
            [component.visual for component in components]
        )
        for component in components:
            visual = component.visual
            container.addWidget(
                self._build_item(component, grid_path),
                visual.row,
                column_map[visual.column],
                visual.height,
                int(visual.width * 4),
            )

    def _build_item(
        self,
        component: KeyConfig | SpacerConfig,
        grid_path: SourcePath,
    ) -> QWidget:
        widget = self._context.components.build(
            component,
            self._context,
            source_path=grid_path.child("component", component.id),
            host=self,
        )
        widget.setParent(self)
        return widget

    def _subscribe_to_runtime_state(self) -> None:
        self._state_bridge.state_changed.connect(self._apply_state_change)
        self._event_unsubscribes = [
            self._context.dispatcher.add_event_handler(STATE_CHANGED, self._receive_state_change),
        ]

    def _unsubscribe_from_runtime_state(self) -> None:
        for unsubscribe in self._event_unsubscribes:
            unsubscribe()
        self._event_unsubscribes.clear()

    def _receive_state_change(self, event: StateChangedArguments) -> MessageResult:
        self._state_bridge.state_changed.emit(event.source, event.state)
        return []

    def _apply_state_change(self, source: object, state: object) -> None:
        if not isinstance(source, SourcePath) or not isinstance(state, dict):
            return
        if source == self._layout_path:
            tags = state.get("state_tags", [])
            if isinstance(tags, list):
                self._active_state_tags = frozenset(
                    item for item in tags if isinstance(item, str)
                )
                self._refresh_key_legends()
            return
        button = self._buttons_by_source.get(source)
        if button is not None:
            render_key_button_state(button, state)

    def _read_layout_tags(self) -> frozenset[str]:
        state = self._context.behaviors.state_snapshot(self._layout_path)
        tags = state.get("state_tags", [])
        if not isinstance(tags, list):
            return frozenset()
        return frozenset(item for item in tags if isinstance(item, str))

    def _refresh_key_legends(self) -> None:
        for button, visual in self._buttons_by_visual:
            display = visual.resolve_display(self._active_state_tags)
            set_key_button_label(button, display.label, display.secondary_label)
