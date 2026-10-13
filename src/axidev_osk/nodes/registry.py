"""Node kinds: the curated widgets and containers profiles compose.

A node kind declares everything about one widget type in one place: its
callback fields and events, how its fixed fields and its values decode, how it
builds a widget, and how a set of values is applied to that widget. Any value
may be a binding; the builder decodes a node's values again whenever the state
they read changes and hands the kind the new values with the previous ones.
A kind may let its children's placement follow state too, the way a canvas
places each child by its ``shape``. The builder also reports the size of a
node built with ``report_size``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QWidget

from ..config.profile import NodeConfig, NodeValues, StyleConfig
from ..config.reader import ConfigReader
from ..kind_registry import KindRegistry
from ..messages import DataMap, DataValue, data_equal
from ..runtime.decoding import non_empty_string_value, require_keys, validated_event
from ..runtime.engine_messages import node_resized
from ..widget_properties import CLASSES, COMPONENT_ID, COMPONENT_TYPE, PASSES_INPUT_BLOCK
from .pointer import PointerReporter

if TYPE_CHECKING:
    from ..runtime.dispatcher import Dispatcher, Unsubscribe
    from ..runtime.profile_runtime import BindingTracker

NodeBuild = Callable[[NodeConfig, "NodeBuilder"], QWidget]
"""Build a node's widget and children from its fixed fields; its values are applied afterwards."""
NodeApply = Callable[[QWidget, object, object | None], None]
"""Apply a kind's options to its widget, given the options applied before or ``None`` the first time."""
PlaceChild = Callable[[QWidget, QWidget, object], None]
"""Place a child widget inside its parent's widget by the child's live placement; called again on each change."""


@dataclass(frozen=True, slots=True)
class NodeEventArguments:
    node: str


def decode_node_event(arguments: DataMap) -> NodeEventArguments:
    require_keys(arguments, ("node",))
    return NodeEventArguments(node=non_empty_string_value(arguments, "node"))


def _no_options(reader: ConfigReader) -> None:
    del reader


@dataclass(frozen=True, slots=True)
class NodeKind:
    """Everything the engine knows about one node kind."""

    name: str
    build: NodeBuild
    apply: NodeApply
    decode_options: Callable[[ConfigReader], object]
    callbacks: Mapping[str, str] = field(default_factory=dict)
    event_decoders: Mapping[str, Callable[[DataMap], object]] = field(default_factory=dict)
    """Decoders for events whose record carries more than ``node``; other events decode as ``{node}``."""
    has_children: bool = False
    decode_structure: Callable[[ConfigReader], object] = _no_options
    decode_child_placement: Callable[[ConfigReader], object] = _no_options
    check_options: Callable[[ConfigReader, object, tuple[str, ...]], None] = lambda reader, options, children: None
    """Reject decoded options that do not fit the node's children, given their IDs.

    It runs at load and on every later decode.
    """
    decode_live_placement: Callable[[ConfigReader], object] | None = None
    """Read a child's placement fields that may follow state; ``place_child`` applies them."""
    place_child: PlaceChild | None = None
    """Place a child by its live placement, before its other values apply and again whenever it changes."""

    def __post_init__(self) -> None:
        if (self.decode_live_placement is None) != (self.place_child is None):
            raise ValueError(f"Node kind {self.name!r} must set both decode_live_placement and place_child, or neither")

    @property
    def events(self) -> tuple[str, ...]:
        return tuple(self.callbacks.values())


class NodeKindRegistry(KindRegistry[NodeKind]):
    """Registered node kinds; each kind's events are registered with the dispatcher as it is added."""

    def __init__(self, dispatcher: "Dispatcher") -> None:
        super().__init__()
        self._dispatcher = dispatcher
        self._events: dict[str, Callable[[DataMap], object]] = {}

    def register(self, kind: NodeKind) -> None:
        """Add a kind and register its events, each with its kind's decoder or the ``{node}`` one."""

        collisions = sorted(
            event for event in kind.events if event not in self._events and self._dispatcher.has_event(event)
        )
        if collisions:
            raise ValueError(f"Node kind {kind.name!r} events are already registered elsewhere: {', '.join(collisions)}")
        super().register(kind)
        for event in kind.events:
            if event not in self._events:
                decoder = kind.event_decoders.get(event, decode_node_event)
                self._dispatcher.register_event(event, decoder)
                self._events[event] = decoder

    def event_decoder(self, event: str) -> Callable[[DataMap], object]:
        return self._events[event]


class NodeBuilder:
    """Build widgets for decoded nodes and keep their values following state."""

    def __init__(
        self,
        kinds: NodeKindRegistry,
        dispatcher: "Dispatcher",
        bindings: "BindingTracker",
    ) -> None:
        self._kinds = kinds
        self._dispatcher = dispatcher
        self._bindings = bindings
        self._unbinds: list[Unsubscribe] | None = None
        self._parents: list[NodeKind] = []

    def build_tree(self, node: NodeConfig) -> tuple[QWidget, list[Unsubscribe]]:
        """Build ``node`` and its children, returning the widget and every binding they made.

        The caller owns the bindings and drops them when it closes, so they
        never decode against another profile's state. When building fails,
        the bindings made so far are dropped before the error is raised.
        """

        unbinds: list[Unsubscribe] = []
        outer = self._unbinds
        self._unbinds = unbinds
        try:
            widget = self.build(node)
        except BaseException:
            for unbind in unbinds:
                unbind()
            raise
        finally:
            self._unbinds = outer
        return widget, unbinds

    def build(self, node: NodeConfig, *, into: QWidget | None = None) -> QWidget:
        """Build one node inside ``build_tree``; node kinds call it for their children.

        A kind with ``place_child`` passes its own widget as ``into``, so the
        builder can place each child there by the child's live placement.
        """

        unbinds = self._unbinds
        if unbinds is None:
            raise RuntimeError("Nodes are built through build_tree, which owns their bindings")
        parent = self._parents[-1] if self._parents else None
        place_child = parent.place_child if parent is not None else None
        if parent is not None and place_child is not None and into is None:
            raise RuntimeError(f"Node kind {parent.name!r} must build its children with into=")
        kind = self._kinds[node.kind]
        self._parents.append(kind)
        try:
            widget = kind.build(node, self)
        finally:
            self._parents.pop()
        widget.setProperty(COMPONENT_TYPE, node.kind)
        widget.setProperty(COMPONENT_ID, node.id)
        if node.passes_input_block:
            widget.setProperty(PASSES_INPUT_BLOCK, True)
        if node.report_size:
            _SizeReporter(widget, node.id, self._dispatcher)
        if node.reports_pointer:
            # Built after the kind, so the reporter also watches the children the kind built.
            PointerReporter(node.id, widget, self._dispatcher)

        def apply(values: NodeValues, previous: NodeValues | None) -> None:
            if place_child is not None and (previous is None or values.placement != previous.placement):
                assert into is not None
                place_child(into, widget, values.placement)
            apply_style(widget, values.style, previous.style if previous is not None else None)
            kind.apply(widget, values.options, previous.options if previous is not None else None)

        unbinds.append(self._bindings.bind(node.values.decode, f"node:{node.id}", apply, fallback=node.values.initial))
        return widget

    def emit(self, event_name: str, node_id: str, **fields: DataValue) -> None:
        """Post a node event; ``fields`` are what its record carries besides ``node``."""

        decoder = self._kinds.event_decoder(event_name)
        self._dispatcher.post(validated_event(event_name, {"node": node_id, **fields}, decoder))


class _SizeReporter(QObject):
    """Post ``node.resized`` whenever a node built with ``report_size`` changes size."""

    def __init__(self, widget: QWidget, node_id: str, dispatcher: "Dispatcher") -> None:
        super().__init__(widget)
        self._node_id = node_id
        self._dispatcher = dispatcher
        widget.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if event.type() == QEvent.Type.Resize and isinstance(watched, QWidget):
            # Posted, so bindings reading the size never run inside this Qt event.
            self._dispatcher.post(node_resized(self._node_id, watched.width(), watched.height()))
        return False


def apply_style(widget: QWidget, style: StyleConfig, previous: StyleConfig | None = None) -> None:
    """Apply profile style hooks that QSS can target, undoing the ones a previous style set."""

    if previous is not None and _same_style(style, previous):
        return
    if style.object_name is not None:
        widget.setObjectName(style.object_name)
    elif previous is not None and previous.object_name is not None:
        widget.setObjectName("")
    if style.classes or (previous is not None and previous.classes):
        widget.setProperty(CLASSES, list(style.classes) if style.classes else None)
    if previous is not None:
        for name in previous.properties:
            if name not in style.properties:
                widget.setProperty(name, None)
    for name, value in style.properties.items():
        widget.setProperty(name, value)
    if style.qss is not None:
        widget.setStyleSheet(style.qss)
    elif previous is not None and previous.qss is not None:
        widget.setStyleSheet("")
    if previous is not None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()


def _same_style(style: StyleConfig, previous: StyleConfig) -> bool:
    """Compare styles the way the binding tracker compares values, so ``True`` is not ``1``."""

    return (
        style.object_name == previous.object_name
        and style.classes == previous.classes
        and style.qss == previous.qss
        and data_equal(style.properties, previous.properties)
    )
