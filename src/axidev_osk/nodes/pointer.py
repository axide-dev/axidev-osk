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

A node built with ``reports_hover`` posts ``node.pointer_hovered`` for every
movement over it while no mouse button is held, with the position in the
node's pixels and on the screen, and ``node.pointer_left`` when the pointer
leaves it. A profile can build its own dwell from these and ``window.click``.
A node built with ``reports_wheel`` posts ``node.wheel`` for each turn of the
mouse wheel over it, in wheel steps, where one notch is 1. Both fire often, so
each is reported only for nodes that opt in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QWidget

from ..components.mouse_buttons import MOUSE_BUTTONS, OTHER_BUTTON, mouse_button_name
from ..messages import DataMap, RuntimeEvent
from ..runtime.decoding import int_value, non_empty_string_value, number_value, require_keys, validated_event
from ..runtime.event_fields import profile_node, samples

if TYPE_CHECKING:
    from ..runtime.dispatcher import Dispatcher

NODE_POINTER_PRESSED = "node.pointer_pressed"
NODE_POINTER_MOVED = "node.pointer_moved"
NODE_POINTER_RELEASED = "node.pointer_released"
NODE_POINTER_HOVERED = "node.pointer_hovered"
NODE_POINTER_LEFT = "node.pointer_left"
NODE_WHEEL = "node.wheel"

_WHEEL_STEP = 120
"""Qt's angle delta for one wheel notch, in eighths of a degree."""

_EVENTS = {
    QEvent.Type.MouseButtonPress: NODE_POINTER_PRESSED,
    # Qt sends a double click in place of the second press.
    QEvent.Type.MouseButtonDblClick: NODE_POINTER_PRESSED,
    QEvent.Type.MouseMove: NODE_POINTER_MOVED,
    QEvent.Type.MouseButtonRelease: NODE_POINTER_RELEASED,
}


@dataclass(frozen=True, slots=True)
class NodePointerArguments:
    node: str = profile_node()
    x: float = samples(0.0)
    y: float = samples(0.0)


def decode_node_pointer(arguments: DataMap) -> NodePointerArguments:
    require_keys(arguments, ("node", "x", "y"))
    return NodePointerArguments(
        node=non_empty_string_value(arguments, "node"),
        x=number_value(arguments, "x"),
        y=number_value(arguments, "y"),
    )


@dataclass(frozen=True, slots=True)
class NodePointerPressArguments:
    node: str = profile_node()
    x: float = samples(0.0)
    y: float = samples(0.0)
    button: str = samples(*MOUSE_BUTTONS.values(), OTHER_BUTTON)


def decode_node_pointer_press(arguments: DataMap) -> NodePointerPressArguments:
    require_keys(arguments, ("node", "x", "y", "button"))
    return NodePointerPressArguments(
        node=non_empty_string_value(arguments, "node"),
        x=number_value(arguments, "x"),
        y=number_value(arguments, "y"),
        button=non_empty_string_value(arguments, "button"),
    )


@dataclass(frozen=True, slots=True)
class NodeHoverArguments:
    node: str = profile_node()
    x: float = samples(0.0)
    y: float = samples(0.0)
    screen_x: int = samples(0)
    screen_y: int = samples(0)


def decode_node_hover(arguments: DataMap) -> NodeHoverArguments:
    require_keys(arguments, ("node", "x", "y", "screen_x", "screen_y"))
    return NodeHoverArguments(
        node=non_empty_string_value(arguments, "node"),
        x=number_value(arguments, "x"),
        y=number_value(arguments, "y"),
        screen_x=int_value(arguments, "screen_x"),
        screen_y=int_value(arguments, "screen_y"),
    )


@dataclass(frozen=True, slots=True)
class NodeArguments:
    node: str = profile_node()


def decode_node(arguments: DataMap) -> NodeArguments:
    require_keys(arguments, ("node",))
    return NodeArguments(node=non_empty_string_value(arguments, "node"))


@dataclass(frozen=True, slots=True)
class NodeWheelArguments:
    node: str = profile_node()
    dx: float = samples(0.0)
    dy: float = samples(1.0)


def decode_node_wheel(arguments: DataMap) -> NodeWheelArguments:
    require_keys(arguments, ("node", "dx", "dy"))
    return NodeWheelArguments(
        node=non_empty_string_value(arguments, "node"),
        dx=number_value(arguments, "dx"),
        dy=number_value(arguments, "dy"),
    )


def node_pointer(name: str, node_id: str, x: float, y: float, button: str | None = None) -> RuntimeEvent:
    if button is None:
        return validated_event(name, {"node": node_id, "x": x, "y": y}, decode_node_pointer)
    return validated_event(name, {"node": node_id, "x": x, "y": y, "button": button}, decode_node_pointer_press)


def register_pointer_events(dispatcher: Dispatcher) -> None:
    dispatcher.register_event(NODE_POINTER_PRESSED, decode_node_pointer_press)
    dispatcher.register_event(NODE_POINTER_MOVED, decode_node_pointer)
    dispatcher.register_event(NODE_POINTER_RELEASED, decode_node_pointer_press)
    dispatcher.register_event(NODE_POINTER_HOVERED, decode_node_hover)
    dispatcher.register_event(NODE_POINTER_LEFT, decode_node)
    dispatcher.register_event(NODE_WHEEL, decode_node_wheel)


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


class HoverReporter(QObject):
    """Watch one node's widget and its descendants, and post its hover movements and its leaving."""

    def __init__(self, node_id: str, widget: QWidget, dispatcher: Dispatcher) -> None:
        super().__init__(widget)
        self._node_id = node_id
        self._widget = widget
        self._dispatcher = dispatcher
        self._last: tuple[int, float, float] | None = None
        for watched in (widget, *widget.findChildren(QWidget)):
            # Qt reports movement without a held button only to widgets that track the mouse.
            watched.setMouseTracking(True)
            watched.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Leave and watched is self._widget:
            self._dispatcher.post(validated_event(NODE_POINTER_LEFT, {"node": self._node_id}, decode_node))
            return False
        if event.type() != QEvent.Type.MouseMove or not isinstance(event, QMouseEvent) or event.buttons():
            return False
        point = self._widget.mapFromGlobal(event.globalPosition())
        # A child that ignores an event passes it on to its parent, which this filter also watches.
        seen = (event.timestamp(), point.x(), point.y())
        if seen == self._last:
            return False
        self._last = seen
        screen = event.globalPosition().toPoint()
        arguments = {
            "node": self._node_id,
            "x": point.x(),
            "y": point.y(),
            "screen_x": screen.x(),
            "screen_y": screen.y(),
        }
        self._dispatcher.post(validated_event(NODE_POINTER_HOVERED, arguments, decode_node_hover))
        return False


class WheelReporter(QObject):
    """Watch one node's widget and its descendants, and post each wheel turn over them."""

    def __init__(self, node_id: str, widget: QWidget, dispatcher: Dispatcher) -> None:
        super().__init__(widget)
        self._node_id = node_id
        self._dispatcher = dispatcher
        self._last: tuple[int, int, int] | None = None
        for watched in (widget, *widget.findChildren(QWidget)):
            watched.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.Wheel or not isinstance(event, QWheelEvent):
            return False
        delta = event.angleDelta()
        seen = (event.timestamp(), delta.x(), delta.y())
        if seen == self._last:
            return False
        self._last = seen
        arguments = {"node": self._node_id, "dx": delta.x() / _WHEEL_STEP, "dy": delta.y() / _WHEEL_STEP}
        self._dispatcher.post(validated_event(NODE_WHEEL, arguments, decode_node_wheel))
        return False
