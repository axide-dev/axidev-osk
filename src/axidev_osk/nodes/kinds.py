"""Built-in node kinds: button, label, spacer, grid, box, and stack."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..components.button.widget import Button
from ..config.profile import NodeConfig, PropertySpec
from ..config.reader import ConfigError, ConfigReader
from ..messages import DataValue
from .registry import NodeBuilder, NodeKind, NodeKindRegistry

BUTTON_PRESSED = "button.pressed"
BUTTON_RELEASED = "button.released"

_VISIBLE = {"visible": PropertySpec(bool, True)}


_QT_MAX_SIZE = 16_777_215
_ALIGNMENTS = {
    "left": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    "center": Qt.AlignmentFlag.AlignCenter,
    "right": Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
    "top_left": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
}


@dataclass(frozen=True, slots=True)
class SizeOptions:
    """Pixel size limits; a maximum of 0 means unlimited."""

    min_width: int = 0
    min_height: int = 0
    max_width: int = 0
    max_height: int = 0

    def apply(self, widget: QWidget) -> None:
        widget.setMinimumSize(self.min_width, self.min_height)
        widget.setMaximumSize(self.max_width or _QT_MAX_SIZE, self.max_height or _QT_MAX_SIZE)


@dataclass(frozen=True, slots=True)
class LayoutOptions:
    spacing: int = 0
    margins: tuple[int, int, int, int] = (0, 0, 0, 0)
    direction: str = "vertical"


@dataclass(frozen=True, slots=True)
class LabelOptions:
    word_wrap: bool = False
    align: str = "left"
    size: SizeOptions = SizeOptions()


def register_builtin_nodes(registry: NodeKindRegistry) -> None:
    registry.register(
        NodeKind(
            name="button",
            build=_build_button,
            apply=_apply_button,
            properties={
                "label": PropertySpec(str, ""),
                "active": PropertySpec(bool, False),
                "latched": PropertySpec(bool, False),
                "enabled": PropertySpec(bool, True),
                **_VISIBLE,
            },
            callbacks={"on_press": BUTTON_PRESSED, "on_release": BUTTON_RELEASED},
            decode_options=_decode_size,
        )
    )
    registry.register(
        NodeKind(
            name="label",
            build=_build_label,
            apply=_apply_label,
            properties={"text": PropertySpec(str, ""), **_VISIBLE},
            decode_options=_decode_label,
        )
    )
    registry.register(NodeKind(name="spacer", build=_build_spacer, apply=_apply_common, decode_options=_decode_size))
    registry.register(
        NodeKind(
            name="grid",
            build=_build_grid,
            apply=_apply_common,
            properties=_VISIBLE,
            has_children=True,
            decode_options=_decode_layout,
        )
    )
    registry.register(
        NodeKind(
            name="box",
            build=_build_box,
            apply=_apply_common,
            properties=_VISIBLE,
            has_children=True,
            decode_options=_decode_layout,
        )
    )
    registry.register(
        NodeKind(
            name="stack",
            build=_build_stack,
            apply=_apply_stack,
            properties={"current": PropertySpec(str), **_VISIBLE},
            has_children=True,
        )
    )


def _decode_size(reader: ConfigReader) -> SizeOptions:
    return SizeOptions(
        min_width=reader.integer("min_width", 0, minimum=0),
        min_height=reader.integer("min_height", 0, minimum=0),
        max_width=reader.integer("max_width", 0, minimum=0),
        max_height=reader.integer("max_height", 0, minimum=0),
    )


def _decode_label(reader: ConfigReader) -> LabelOptions:
    return LabelOptions(
        word_wrap=reader.boolean("word_wrap", False),
        align=reader.choice("align", frozenset(_ALIGNMENTS), "left"),
        size=_decode_size(reader),
    )


def _decode_layout(reader: ConfigReader) -> LayoutOptions:
    margins = reader.raw("margins", [0, 0, 0, 0])
    if (
        not isinstance(margins, (list, tuple))
        or len(margins) != 4
        or not all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in margins)
    ):
        raise ConfigError(f"{reader.field_path('margins')} must be [left, top, right, bottom] in pixels")
    return LayoutOptions(
        spacing=reader.integer("spacing", 0, minimum=0),
        margins=(margins[0], margins[1], margins[2], margins[3]),
        direction=reader.choice("direction", frozenset({"vertical", "horizontal"}), "vertical"),
    )


def _apply_common(widget: QWidget, name: str, value: DataValue) -> None:
    if name == "visible":
        widget.setVisible(bool(value))


def _build_button(node: NodeConfig, builder: NodeBuilder) -> QWidget:
    options = node.options
    assert isinstance(options, SizeOptions)
    button = Button()
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    options.apply(button)
    button.setProperty("pressed", False)
    button.setProperty("latched", False)
    button.setProperty("interactionState", "idle")
    button.pressed.connect(lambda: builder.emit(BUTTON_PRESSED, node.id))
    button.released.connect(lambda: builder.emit(BUTTON_RELEASED, node.id))
    return button


def _apply_button(widget: QWidget, name: str, value: DataValue) -> None:
    if name == "label":
        assert isinstance(widget, Button)
        widget.setText("" if value is None else str(value))
        return
    if name == "enabled":
        widget.setEnabled(bool(value))
        return
    if name in {"active", "latched"}:
        widget.setProperty("pressed" if name == "active" else "latched", bool(value))
        pressed = bool(widget.property("pressed"))
        latched = bool(widget.property("latched"))
        state = (
            "latched_pressed" if pressed and latched
            else "pressed" if pressed
            else "latched" if latched
            else "idle"
        )
        widget.setProperty("interactionState", state)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()
        return
    _apply_common(widget, name, value)


def _build_label(node: NodeConfig, builder: NodeBuilder) -> QWidget:
    del builder
    options = node.options
    assert isinstance(options, LabelOptions)
    label = QLabel()
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(options.word_wrap)
    label.setAlignment(_ALIGNMENTS[options.align])
    options.size.apply(label)
    return label


def _apply_label(widget: QWidget, name: str, value: DataValue) -> None:
    if name == "text":
        assert isinstance(widget, QLabel)
        widget.setText("" if value is None else str(value))
        return
    _apply_common(widget, name, value)


def _build_spacer(node: NodeConfig, builder: NodeBuilder) -> QWidget:
    del builder
    options = node.options
    assert isinstance(options, SizeOptions)
    spacer = QWidget()
    spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    options.apply(spacer)
    spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return spacer


def _build_grid(node: NodeConfig, builder: NodeBuilder) -> QWidget:
    options = node.options
    assert isinstance(options, LayoutOptions)
    container = QWidget()
    layout = QGridLayout(container)
    layout.setContentsMargins(*options.margins)
    layout.setHorizontalSpacing(options.spacing)
    layout.setVerticalSpacing(options.spacing)
    rows: set[int] = set()
    columns: set[int] = set()
    for child in node.children:
        cell = child.cell
        if cell is None:
            raise ConfigError(f"Grid {node.id!r} child {child.id!r} needs a cell")
        widget = builder.build(child)
        layout.addWidget(widget, cell.row, cell.column, cell.row_span, cell.column_span)
        rows.update(range(cell.row, cell.row + cell.row_span))
        columns.update(range(cell.column, cell.column + cell.column_span))
    for row in rows:
        layout.setRowStretch(row, 1)
    for column in columns:
        layout.setColumnStretch(column, 1)
    return container


def _build_box(node: NodeConfig, builder: NodeBuilder) -> QWidget:
    options = node.options
    assert isinstance(options, LayoutOptions)
    container = QWidget()
    layout: QBoxLayout = QVBoxLayout(container) if options.direction == "vertical" else QHBoxLayout(container)
    layout.setContentsMargins(*options.margins)
    layout.setSpacing(options.spacing)
    for child in node.children:
        layout.addWidget(builder.build(child), child.stretch)
    return container


def _build_stack(node: NodeConfig, builder: NodeBuilder) -> QWidget:
    stack = QStackedWidget()
    for child in node.children:
        stack.addWidget(builder.build(child))
    return stack


def _apply_stack(widget: QWidget, name: str, value: DataValue) -> None:
    if name == "current":
        assert isinstance(widget, QStackedWidget)
        for index in range(widget.count()):
            page = widget.widget(index)
            if page is not None and page.property("componentId") == value:
                widget.setCurrentWidget(page)
                return
        return
    _apply_common(widget, name, value)
