"""Built-in node kinds: button, label, spacer, grid, box, and stack.

Every value a kind reads from its options may be a binding. Fixed fields (a
box's direction, a grid child's cell, a box child's stretch) are read
separately and never change while the widget lives.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..components.button.widget import Button
from ..config.profile import NodeConfig
from ..config.reader import ConfigError, ConfigReader
from .registry import NodeBuilder, NodeKind, NodeKindRegistry

BUTTON_PRESSED = "button.pressed"
BUTTON_RELEASED = "button.released"


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
class ButtonOptions:
    label: str = ""
    active: bool = False
    latched: bool = False
    enabled: bool = True
    visible: bool = True
    size: SizeOptions = SizeOptions()


@dataclass(frozen=True, slots=True)
class LabelOptions:
    text: str = ""
    visible: bool = True
    word_wrap: bool = False
    align: str = "left"
    size: SizeOptions = SizeOptions()


@dataclass(frozen=True, slots=True)
class SpacerOptions:
    visible: bool = True
    size: SizeOptions = SizeOptions()


@dataclass(frozen=True, slots=True)
class LayoutOptions:
    """Values of a grid or box: spacing, margins, and whether it shows."""

    spacing: int = 0
    margins: tuple[int, int, int, int] = (0, 0, 0, 0)
    visible: bool = True


@dataclass(frozen=True, slots=True)
class StackOptions:
    current: str | None = None
    visible: bool = True


@dataclass(frozen=True, slots=True)
class BoxStructure:
    direction: str = "vertical"


@dataclass(frozen=True, slots=True)
class GridCell:
    """Where a grid child sits, read from its ``cell`` field."""

    row: int
    column: int
    row_span: int = 1
    column_span: int = 1


@dataclass(frozen=True, slots=True)
class BoxPlacement:
    """How much spare space a box child takes, read from its ``stretch`` field."""

    stretch: int = 0


def register_builtin_nodes(registry: NodeKindRegistry) -> None:
    registry.register(
        NodeKind(
            name="button",
            build=_build_button,
            apply=_apply_button,
            decode_options=_decode_button,
            callbacks={"on_press": BUTTON_PRESSED, "on_release": BUTTON_RELEASED},
            widget_properties=frozenset({"pressed", "latched", "interactionState"}),
        )
    )
    registry.register(NodeKind(name="label", build=_build_label, apply=_apply_label, decode_options=_decode_label))
    registry.register(NodeKind(name="spacer", build=_build_spacer, apply=_apply_spacer, decode_options=_decode_spacer))
    registry.register(
        NodeKind(
            name="grid",
            build=_build_grid,
            apply=_apply_layout,
            decode_options=_decode_layout,
            has_children=True,
            decode_child_placement=_decode_grid_cell,
        )
    )
    registry.register(
        NodeKind(
            name="box",
            build=_build_box,
            apply=_apply_layout,
            decode_options=_decode_layout,
            has_children=True,
            decode_structure=_decode_box_structure,
            decode_child_placement=_decode_box_placement,
        )
    )
    registry.register(
        NodeKind(
            name="stack",
            build=_build_stack,
            apply=_apply_stack,
            decode_options=_decode_stack,
            has_children=True,
            decode_child_placement=_decode_stack_page,
        )
    )


def _decode_size(reader: ConfigReader) -> SizeOptions:
    return SizeOptions(
        min_width=reader.integer("min_width", 0, minimum=0),
        min_height=reader.integer("min_height", 0, minimum=0),
        max_width=reader.integer("max_width", 0, minimum=0),
        max_height=reader.integer("max_height", 0, minimum=0),
    )


def _visible(reader: ConfigReader) -> bool:
    return reader.boolean("visible", True)


def _decode_button(reader: ConfigReader) -> ButtonOptions:
    return ButtonOptions(
        label=reader.optional_string("label") or "",
        active=reader.boolean("active", False),
        latched=reader.boolean("latched", False),
        enabled=reader.boolean("enabled", True),
        visible=_visible(reader),
        size=_decode_size(reader),
    )


def _decode_label(reader: ConfigReader) -> LabelOptions:
    return LabelOptions(
        text=reader.optional_string("text") or "",
        visible=_visible(reader),
        word_wrap=reader.boolean("word_wrap", False),
        align=reader.choice("align", frozenset(_ALIGNMENTS), "left"),
        size=_decode_size(reader),
    )


def _decode_spacer(reader: ConfigReader) -> SpacerOptions:
    return SpacerOptions(visible=_visible(reader), size=_decode_size(reader))


def _decode_layout(reader: ConfigReader) -> LayoutOptions:
    left, top, right, bottom = reader.integer_list("margins", (0, 0, 0, 0), shape="[left, top, right, bottom] in pixels")
    return LayoutOptions(
        spacing=reader.integer("spacing", 0, minimum=0),
        margins=(left, top, right, bottom),
        visible=_visible(reader),
    )


def _decode_stack(reader: ConfigReader) -> StackOptions:
    return StackOptions(current=reader.optional_string("current"), visible=_visible(reader))


def _decode_box_structure(reader: ConfigReader) -> BoxStructure:
    return BoxStructure(direction=reader.choice("direction", frozenset({"vertical", "horizontal"}), "vertical"))


def _decode_grid_cell(reader: ConfigReader) -> GridCell:
    cell = reader.child("cell")
    return cell.decode(
        lambda fields: GridCell(
            row=fields.integer("row", minimum=0),
            column=fields.integer("column", minimum=0),
            row_span=fields.integer("row_span", 1, minimum=1),
            column_span=fields.integer("column_span", 1, minimum=1),
        )
    )


def _decode_box_placement(reader: ConfigReader) -> BoxPlacement:
    return BoxPlacement(stretch=reader.integer("stretch", 0, minimum=0))


def _decode_stack_page(reader: ConfigReader) -> None:
    """A stack shows its ``current`` page, so its pages cannot set ``visible``."""

    if reader.has("visible"):
        raise ConfigError(f"{reader.field_path('visible')} cannot be set on a stack page; the stack's current chooses the page")


def _apply_visible(widget: QWidget, visible: bool) -> None:
    if not visible:
        widget.hide()
    elif widget.parentWidget() is not None:
        widget.show()
    # A widget without a parent yet must not be shown: it would become its
    # own window. Qt shows it with its parent once it is placed.


def _build_button(node: NodeConfig, builder: NodeBuilder) -> QWidget:
    button = Button()
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    button.pressed.connect(lambda: builder.emit(BUTTON_PRESSED, node.id))
    button.released.connect(lambda: builder.emit(BUTTON_RELEASED, node.id))
    return button


def _apply_button(widget: QWidget, options: object, previous: object | None) -> None:
    assert isinstance(widget, Button) and isinstance(options, ButtonOptions)
    old = previous if isinstance(previous, ButtonOptions) else None
    if old is None or options.size != old.size:
        options.size.apply(widget)
    if old is None or options.label != old.label:
        # Qt reads a single "&" as a shortcut marker; doubling it shows the label as written.
        widget.setText(options.label.replace("&", "&&"))
    if old is None or options.enabled != old.enabled:
        widget.setEnabled(options.enabled)
    if old is None or (options.active, options.latched) != (old.active, old.latched):
        widget.setProperty("pressed", options.active)
        widget.setProperty("latched", options.latched)
        state = (
            "latched_pressed" if options.active and options.latched
            else "pressed" if options.active
            else "latched" if options.latched
            else "idle"
        )
        widget.setProperty("interactionState", state)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()
    if old is None or options.visible != old.visible:
        _apply_visible(widget, options.visible)


def _build_label(node: NodeConfig, builder: NodeBuilder) -> QWidget:
    del node, builder
    label = QLabel()
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def _apply_label(widget: QWidget, options: object, previous: object | None) -> None:
    assert isinstance(widget, QLabel) and isinstance(options, LabelOptions)
    old = previous if isinstance(previous, LabelOptions) else None
    if old is None or options.word_wrap != old.word_wrap:
        widget.setWordWrap(options.word_wrap)
        # A wrapped label must keep the height its lines need at its width.
        vertical = QSizePolicy.Policy.Minimum if options.word_wrap else QSizePolicy.Policy.Preferred
        horizontal = QSizePolicy.Policy.Expanding if options.word_wrap else QSizePolicy.Policy.Preferred
        widget.setSizePolicy(horizontal, vertical)
    if old is None or options.align != old.align:
        widget.setAlignment(_ALIGNMENTS[options.align])
    if old is None or options.size != old.size:
        options.size.apply(widget)
    if old is None or options.text != old.text:
        widget.setText(options.text)
    if old is None or options.visible != old.visible:
        _apply_visible(widget, options.visible)


def _build_spacer(node: NodeConfig, builder: NodeBuilder) -> QWidget:
    del node, builder
    spacer = QWidget()
    spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return spacer


def _apply_spacer(widget: QWidget, options: object, previous: object | None) -> None:
    assert isinstance(options, SpacerOptions)
    old = previous if isinstance(previous, SpacerOptions) else None
    if old is None or options.size != old.size:
        options.size.apply(widget)
    if old is None or options.visible != old.visible:
        _apply_visible(widget, options.visible)


def _build_grid(node: NodeConfig, builder: NodeBuilder) -> QWidget:
    container = QWidget()
    layout = QGridLayout(container)
    rows: set[int] = set()
    columns: set[int] = set()
    for child in node.children:
        cell = child.placement
        assert isinstance(cell, GridCell)
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
    structure = node.structure
    assert isinstance(structure, BoxStructure)
    container = QWidget()
    layout: QBoxLayout = QVBoxLayout(container) if structure.direction == "vertical" else QHBoxLayout(container)
    for child in node.children:
        placement = child.placement
        assert isinstance(placement, BoxPlacement)
        layout.addWidget(builder.build(child), placement.stretch)
    return container


def _apply_layout(widget: QWidget, options: object, previous: object | None) -> None:
    assert isinstance(options, LayoutOptions)
    old = previous if isinstance(previous, LayoutOptions) else None
    layout = widget.layout()
    assert isinstance(layout, QLayout)
    if old is None or options.margins != old.margins:
        layout.setContentsMargins(*options.margins)
    if old is None or options.spacing != old.spacing:
        if isinstance(layout, QGridLayout):
            layout.setHorizontalSpacing(options.spacing)
            layout.setVerticalSpacing(options.spacing)
        else:
            layout.setSpacing(options.spacing)
    if old is None or options.visible != old.visible:
        _apply_visible(widget, options.visible)


def _build_stack(node: NodeConfig, builder: NodeBuilder) -> QWidget:
    stack = QStackedWidget()
    for child in node.children:
        stack.addWidget(builder.build(child))
    return stack


def _apply_stack(widget: QWidget, options: object, previous: object | None) -> None:
    assert isinstance(widget, QStackedWidget) and isinstance(options, StackOptions)
    old = previous if isinstance(previous, StackOptions) else None
    if options.current is not None and (old is None or options.current != old.current):
        for index in range(widget.count()):
            page = widget.widget(index)
            if page is not None and page.property("componentId") == options.current:
                widget.setCurrentWidget(page)
                break
        else:
            raise ValueError(f"Stack {widget.property('componentId')!r} has no page {options.current!r}")
    if old is None or options.visible != old.visible:
        _apply_visible(widget, options.visible)
