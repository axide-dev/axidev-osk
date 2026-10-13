"""Pointer reports from nodes built with ``reports_pointer``.

Such a node posts ``node.pointer_pressed`` when a press starts anywhere inside
it, children included, then ``node.pointer_moved`` for every movement until
the release, then ``node.pointer_released``, even when the pointer leaves the
node meanwhile. Each event carries the node ID and the pointer position in
the node's own pixels, so a profile can follow a swipe across a grid of keys.
A press and its release also carry the mouse button (``left``, ``right``,
``middle``, ...); while one button holds the press, the others are not
reported, and only that button's release ends it.
Reporting never takes the event away: the children under the pointer still
get their presses and clicks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from ..components.mouse_buttons import mouse_button_name
from ..messages import DataMap, RuntimeEvent
from ..runtime.decoding import non_empty_string_value, number_value, require_keys, validated_event

if TYPE_CHECKING:
    from ..runtime.dispatcher import Dispatcher

NODE_POINTER_PRESSED = "node.pointer_pressed"
NODE_POINTER_MOVED = "node.pointer_moved"
NODE_POINTER_RELEASED = "node.pointer_released"

_EVENTS = {
    QEvent.Type.MouseButtonPress: NODE_POINTER_PRESSED,
    # Qt sends a double click in place of the second press.
    QEvent.Type.MouseButtonDblClick: NODE_POINTER_PRESSED,
    QEvent.Type.MouseMove: NODE_POINTER_MOVED,
    QEvent.Type.MouseButtonRelease: NODE_POINTER_RELEASED,
}


@dataclass(frozen=True, slots=True)
class NodePointerArguments:
    node: str
    x: float
    y: float


def decode_node_pointer(arguments: DataMap) -> NodePointerArguments:
    require_keys(arguments, ("node", "x", "y"))
    return NodePointerArguments(
        node=non_empty_string_value(arguments, "node"),
        x=number_value(arguments, "x"),
        y=number_value(arguments, "y"),
    )


@dataclass(frozen=True, slots=True)
class NodePointerPressArguments:
    node: str
    x: float
    y: float
    button: str


def decode_node_pointer_press(arguments: DataMap) -> NodePointerPressArguments:
    require_keys(arguments, ("node", "x", "y", "button"))
    return NodePointerPressArguments(
        node=non_empty_string_value(arguments, "node"),
        x=number_value(arguments, "x"),
        y=number_value(arguments, "y"),
        button=non_empty_string_value(arguments, "button"),
    )


def node_pointer(name: str, node_id: str, x: float, y: float, button: str | None = None) -> RuntimeEvent:
    if button is None:
        return validated_event(name, {"node": node_id, "x": x, "y": y}, decode_node_pointer)
    return validated_event(name, {"node": node_id, "x": x, "y": y, "button": button}, decode_node_pointer_press)


def register_pointer_events(dispatcher: Dispatcher) -> None:
    dispatcher.register_event(NODE_POINTER_PRESSED, decode_node_pointer_press)
    dispatcher.register_event(NODE_POINTER_MOVED, decode_node_pointer)
    dispatcher.register_event(NODE_POINTER_RELEASED, decode_node_pointer_press)


class PointerReporter(QObject):
    """Watch one node's widget and its descendants, and post its pointer events."""

    def __init__(self, node_id: str, widget: QWidget, dispatcher: Dispatcher) -> None:
        super().__init__(widget)
        self._node_id = node_id
        self._widget = widget
        self._dispatcher = dispatcher
        self._button: str | None = None
        self._last: tuple[QEvent.Type, int, float, float] | None = None
        for watched in (widget, *widget.findChildren(QWidget)):
            watched.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        name = _EVENTS.get(event.type())
        if name is None or not isinstance(event, QMouseEvent):
            return False
        if name == NODE_POINTER_MOVED and self._button is None:
            return False
        point = self._widget.mapFromGlobal(event.globalPosition())
        # A child that ignores an event passes it on to its parent, which this filter also watches.
        seen = (event.type(), event.timestamp(), point.x(), point.y())
        if seen == self._last:
            return False
        self._last = seen
        button = mouse_button_name(event.button())
        if name == NODE_POINTER_MOVED:
            self._dispatcher.post(node_pointer(name, self._node_id, point.x(), point.y()))
            return False
        if name == NODE_POINTER_PRESSED:
            if self._button is not None:
                return False
            self._button = button
        elif button != self._button:
            return False
        else:
            self._button = None
        self._dispatcher.post(node_pointer(name, self._node_id, point.x(), point.y(), button))
        return False
