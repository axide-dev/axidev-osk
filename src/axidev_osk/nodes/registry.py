"""Node kinds: the curated widgets and containers profiles compose.

A node kind declares everything about one widget type in one place: its
callback fields and events, how its fixed fields and its values decode, how it
builds a widget, and how a set of values is applied to that widget. Any value
may be a binding; the builder decodes a node's values again whenever the state
they read changes and hands the kind the new values with the previous ones.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from ..config.profile import NodeConfig, NodeValues, StyleConfig
from ..config.reader import ConfigReader
from ..kind_registry import KindRegistry
from ..messages import DataMap, RuntimeEvent
from ..runtime.decoding import non_empty_string_value, require_keys, validated_event

if TYPE_CHECKING:
    from ..runtime.dispatcher import Dispatcher
    from ..runtime.profile_runtime import BindingTracker

NodeBuild = Callable[[NodeConfig, "NodeBuilder"], QWidget]
"""Build a node's widget and children from its fixed fields; its values are applied afterwards."""
NodeApply = Callable[[QWidget, object, object | None], None]
"""Apply a kind's options to its widget, given the options applied before or ``None`` the first time."""


@dataclass(frozen=True, slots=True)
class NodeEventArguments:
    node: str


def node_event(name: str, node_id: str) -> RuntimeEvent:
    return validated_event(name, {"node": node_id}, decode_node_event)


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
    has_children: bool = False
    widget_properties: frozenset[str] = frozenset()
    """Widget properties ``build`` and ``apply`` set, which a profile style cannot set."""
    decode_structure: Callable[[ConfigReader], object] = _no_options
    decode_child_placement: Callable[[ConfigReader], object] = _no_options
    check_options: Callable[[ConfigReader, object, tuple[str, ...]], None] = lambda reader, options, children: None
    """Reject decoded options that do not fit the node's children, given their IDs."""

    @property
    def events(self) -> tuple[str, ...]:
        return tuple(self.callbacks.values())


class NodeKindRegistry(KindRegistry[NodeKind]):
    """Registered node kinds; each kind's events are registered with the dispatcher as it is added."""

    def __init__(self, dispatcher: "Dispatcher") -> None:
        super().__init__()
        self._dispatcher = dispatcher
        self._events: set[str] = set()

    def register(self, kind: NodeKind) -> None:
        """Add a kind and register its events; every node event shares the ``{node}`` shape."""

        collisions = sorted(
            event for event in kind.events if event not in self._events and self._dispatcher.has_event(event)
        )
        if collisions:
            raise ValueError(f"Node kind {kind.name!r} events are already registered elsewhere: {', '.join(collisions)}")
        super().register(kind)
        for event in kind.events:
            if event not in self._events:
                self._dispatcher.register_event(event, decode_node_event)
                self._events.add(event)


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

    def build(self, node: NodeConfig) -> QWidget:
        kind = self._kinds[node.kind]
        widget = kind.build(node, self)
        widget.setProperty("componentType", node.kind)
        widget.setProperty("componentId", node.id)
        if node.passes_input_block:
            widget.setProperty("passesInputBlock", True)

        def apply(values: NodeValues, previous: NodeValues | None) -> None:
            apply_style(widget, values.style, previous.style if previous is not None else None)
            kind.apply(widget, values.options, previous.options if previous is not None else None)

        unbind = self._bindings.bind(node.values.decode, f"node:{node.id}", apply, fallback=node.values.initial)
        widget.destroyed.connect(lambda _object=None: unbind())
        return widget

    def emit(self, event_name: str, node_id: str) -> None:
        self._dispatcher.dispatch(node_event(event_name, node_id))


def apply_style(widget: QWidget, style: StyleConfig, previous: StyleConfig | None = None) -> None:
    """Apply profile style hooks that QSS can target, undoing the ones a previous style set."""

    if previous is not None and style == previous:
        return
    if style.object_name is not None:
        widget.setObjectName(style.object_name)
    elif previous is not None and previous.object_name is not None:
        widget.setObjectName("")
    if style.classes or (previous is not None and previous.classes):
        widget.setProperty("classes", list(style.classes) if style.classes else None)
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
