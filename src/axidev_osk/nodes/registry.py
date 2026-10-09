"""Node kinds: the curated widgets and containers profiles compose.

A node kind declares everything about one widget type in one place: its
bindable properties, its callback fields and events, how its options decode,
how it builds a widget, and how a property value is applied to that widget.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from ..config.profile import NodeConfig, PropertySpec, StyleConfig
from ..config.reader import ConfigReader
from ..messages import DataMap, DataValue, RuntimeEvent
from ..runtime.decoding import non_empty_string_value, require_keys

if TYPE_CHECKING:
    from ..runtime.dispatcher import Dispatcher, Unsubscribe
    from ..runtime.profile_runtime import BindingTracker

NodeBuild = Callable[[NodeConfig, "NodeBuilder"], QWidget]
NodeApply = Callable[[QWidget, str, DataValue], None]


@dataclass(frozen=True, slots=True)
class NodeEventArguments:
    node: str


def node_event(name: str, node_id: str) -> RuntimeEvent:
    return RuntimeEvent(name, {"node": node_id})


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
    decode_options: Callable[[ConfigReader], object] = _no_options

    @property
    def events(self) -> tuple[str, ...]:
        return tuple(self.callbacks.values())


class NodeKindRegistry(Mapping[str, NodeKind]):
    """Registered node kinds, readable by the profile decoder as a mapping."""

    def __init__(self) -> None:
        self._kinds: dict[str, NodeKind] = {}

    def register(self, kind: NodeKind, *, override: bool = False) -> None:
        if kind.name in self._kinds and not override:
            raise ValueError(f"Node kind {kind.name!r} is already registered")
        self._kinds[kind.name] = kind

    def register_events(self, dispatcher: "Dispatcher") -> None:
        """Register every node event name once; all share the ``{node}`` shape."""

        for name in sorted({event for kind in self._kinds.values() for event in kind.events}):
            if not dispatcher.has_event(name):
                dispatcher.register_event(name, decode_node_event)

    def __getitem__(self, name: str) -> NodeKind:
        return self._kinds[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._kinds)

    def __len__(self) -> int:
        return len(self._kinds)


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
                    lambda resolved, name=name: kind.apply(widget, name, resolved),
                )
            )
        widget.destroyed.connect(lambda _object=None: [unbind() for unbind in unbinds])
        return widget

    def emit(self, event_name: str, node_id: str) -> None:
        self._dispatcher.dispatch_event(node_event(event_name, node_id))


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
