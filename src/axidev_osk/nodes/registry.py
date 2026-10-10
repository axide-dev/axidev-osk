"""Node kinds: the curated widgets and containers profiles compose.

A node kind declares everything about one widget type in one place: its
bindable properties, its callback fields and events, how its options decode,
how it builds a widget, and how a property value is applied to that widget.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from ..config.profile import NodeConfig, PropertySpec, StyleConfig
from ..config.reader import ConfigReader
from ..kind_registry import KindRegistry
from ..messages import DataMap, DataValue, RuntimeEvent
from ..runtime.decoding import non_empty_string_value, require_keys, validated_event

if TYPE_CHECKING:
    from ..runtime.dispatcher import Dispatcher, Unsubscribe
    from ..runtime.profile_runtime import BindingTracker

NodeBuild = Callable[[NodeConfig, "NodeBuilder"], QWidget]
NodeApply = Callable[[QWidget, str, DataValue], None]


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
    properties: Mapping[str, PropertySpec] = field(default_factory=dict)
    callbacks: Mapping[str, str] = field(default_factory=dict)
    has_children: bool = False
    widget_properties: frozenset[str] = frozenset()
    """Widget properties ``build`` and ``apply`` set, which a profile style cannot set."""
    decode_options: Callable[[ConfigReader], object] = _no_options
    decode_child_placement: Callable[[ConfigReader], object] = _no_options

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
    """Build widgets for decoded nodes and keep their bindings live."""

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
        apply_style(widget, node.style)
        unbinds: list["Unsubscribe"] = []
        for name, spec in kind.properties.items():
            if name in node.bindings:
                value = node.bindings[name]
            elif spec.default is not None:
                value = spec.default
            else:
                continue
            unbinds.append(
                self._bindings.bind(
                    value,
                    f"{node.id}.{name}",
                    lambda resolved, name=name, spec=spec: kind.apply(widget, name, _checked(node, name, spec, resolved)),
                )
            )
        widget.destroyed.connect(lambda _object=None: [unbind() for unbind in unbinds])
        return widget

    def emit(self, event_name: str, node_id: str) -> None:
        self._dispatcher.dispatch(node_event(event_name, node_id))


def _checked(node: NodeConfig, name: str, spec: PropertySpec, value: DataValue) -> DataValue:
    """Give a property its default for ``None`` and reject any other value of the wrong type.

    Plain values were checked when the profile was decoded; binding results are
    checked here, so a wrong result becomes ``callback.failed`` instead of a
    silent conversion.
    """

    if value is None:
        return spec.default
    if not isinstance(value, spec.value_type):
        raise TypeError(f"{node.kind} {node.id!r} property {name!r} got {type(value).__name__}")
    return value


def apply_style(widget: QWidget, style: StyleConfig) -> None:
    """Apply profile style hooks that QSS can target."""

    if style.object_name is not None:
        widget.setObjectName(style.object_name)
    if style.classes:
        widget.setProperty("classes", list(style.classes))
    for name, value in style.properties.items():
        widget.setProperty(name, value)
    if style.qss is not None:
        widget.setStyleSheet(style.qss)
