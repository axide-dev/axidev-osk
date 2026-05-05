"""Surface builders for keyboard and prompt window content."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..components.keyboard_widget import KeyboardWidget
from ..config.models import ButtonConfig, SurfaceConfig
from ..runtime.context import Context
from ..runtime.events import PromptResolved
from ..runtime.registries import SurfaceRegistry

_ACCEPT_BUTTON_QSS = """
QPushButton#confirmAcceptButton {
    background-color: rgba(38, 132, 70, 0.25);
    border: 1px solid rgba(80, 200, 120, 0.85);
    color: #d8ffe3;
}
QPushButton#confirmAcceptButton:hover {
    background-color: rgba(56, 168, 90, 0.45);
    border-color: rgba(120, 230, 150, 1.0);
}
QPushButton#confirmAcceptButton:pressed {
    background-color: rgba(30, 110, 58, 0.85);
}
"""

_REJECT_BUTTON_QSS = """
QPushButton#confirmRejectButton {
    background-color: rgba(160, 40, 50, 0.25);
    border: 1px solid rgba(220, 90, 100, 0.85);
    color: #ffe1e3;
}
QPushButton#confirmRejectButton:hover {
    background-color: rgba(190, 60, 70, 0.45);
    border-color: rgba(240, 130, 140, 1.0);
}
QPushButton#confirmRejectButton:pressed {
    background-color: rgba(140, 30, 40, 0.85);
}
"""


def register_surfaces(registry: SurfaceRegistry) -> None:
    """Register bundled surface builders.

    Args:
        registry: Surface registry owned by the runtime context.

    Returns:
        None.

    Side effects:
        Mutates the registry.
    """

    registry.register("keyboard", build_keyboard_surface)
    registry.register("prompt", build_prompt_surface)


def build_keyboard_surface(config: SurfaceConfig, context: Context) -> QWidget:
    """Build the default keyboard root surface.

    Args:
        config: Keyboard surface config.
        context: Runtime context.

    Returns:
        Root surface widget.

    Side effects:
        Builds a keyboard widget and optional backend status footer.
    """

    if config.layout is None:
        raise ValueError("Keyboard surface requires a layout config")
    central = _root_surface(config)
    layout = QVBoxLayout(central)
    layout.setContentsMargins(*config.margins)
    layout.setSpacing(config.spacing)
    keyboard_widget = KeyboardWidget(layout_config=config.layout, context=context)
    layout.addWidget(keyboard_widget)
    if not context.keyboard.ready:
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(8)
        status_label = QLabel(context.keyboard.status_text, central)
        status_label.setObjectName("statusLabel")
        status_label.setWordWrap(True)
        footer.addWidget(status_label, 1)
        layout.addLayout(footer)
    return central


def build_prompt_surface(config: SurfaceConfig, context: Context) -> QWidget:
    """Build a confirmation prompt root surface.

    Args:
        config: Prompt surface config.
        context: Runtime context.

    Returns:
        Root prompt widget.

    Side effects:
        Connects button clicks to prompt result events and window hiding.
    """

    if config.prompt is None:
        raise ValueError("Prompt surface requires prompt config")
    prompt = config.prompt
    central = _root_surface(config)
    layout = QVBoxLayout(central)
    layout.setContentsMargins(*config.margins)
    layout.setSpacing(config.spacing)

    message_row = QHBoxLayout()
    message_row.setContentsMargins(0, 0, 0, 0)
    message_row.setSpacing(14)
    glyph_label = QLabel(prompt.prompt_glyph, central)
    glyph_label.setFixedSize(40, 40)
    glyph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge_bg = "#d83a3a" if prompt.danger else "#ffd866"
    badge_fg = "#fff5f5" if prompt.danger else "#1a1a1a"
    glyph_label.setStyleSheet(
        "QLabel {"
        f"  background-color: {badge_bg};"
        f"  color: {badge_fg};"
        "  border-radius: 20px;"
        "  font-size: 22px;"
        "  font-weight: 900;"
        "}"
    )
    message_row.addWidget(glyph_label, 0, Qt.AlignmentFlag.AlignVCenter)
    message_label = QLabel(prompt.message, central)
    message_label.setWordWrap(True)
    message_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    message_row.addWidget(message_label, 1)
    layout.addLayout(message_row)

    if prompt.hint:
        hint_label = QLabel(prompt.hint, central)
        hint_label.setWordWrap(True)
        hint_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        hint_label.setStyleSheet(
            "QLabel {"
            "  color: rgba(220, 220, 220, 0.65);"
            "  font-size: 11px;"
            "  font-style: italic;"
            "  padding: 6px 8px;"
            "  border-left: 2px solid rgba(180, 180, 180, 0.35);"
            "}"
        )
        layout.addWidget(hint_label)

    buttons = QHBoxLayout()
    buttons.setContentsMargins(0, 0, 0, 0)
    buttons.setSpacing(10)
    buttons.addStretch(1)
    for button_config in prompt.buttons:
        button = context.components.build(button_config, context)
        if not isinstance(button, QPushButton):
            raise TypeError("Prompt button builder must return QPushButton")
        button.clicked.connect(lambda _checked=False, item=button_config: _resolve_prompt(central, context, prompt.id, item))
        buttons.addWidget(button)
    layout.addLayout(buttons)
    return central


def prompt_button_config(parent_id: str, *, role: str, label: str) -> ButtonConfig:
    """Create a prompt button config preserving existing styles.

    Args:
        parent_id: Prompt ID used to derive the button ID.
        role: Prompt role, usually ``accepted`` or ``rejected``.
        label: Visible button text.

    Returns:
        Button config with existing object names and QSS.

    Side effects:
        None.
    """

    object_name = "confirmAcceptButton" if role == "accepted" else "confirmRejectButton"
    glyph = "✔" if role == "accepted" else "✖"
    style_sheet = _ACCEPT_BUTTON_QSS if role == "accepted" else _REJECT_BUTTON_QSS
    return ButtonConfig(
        id=f"{parent_id}:button:{role}",
        label=f"{glyph}  {label}",
        role=role,
        object_name=object_name,
        style_sheet=style_sheet,
    )


def _root_surface(config: SurfaceConfig) -> QWidget:
    central = QWidget()
    central.setObjectName("rootSurface")
    central.setProperty("componentType", "surface")
    central.setProperty("componentId", config.id)
    central.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    return central


def _resolve_prompt(window_child: QWidget, context: Context, prompt_id: str, button: ButtonConfig) -> None:
    result = "accepted" if button.role == "accepted" else "rejected"
    context.dispatcher.dispatch_event(PromptResolved(prompt_id=prompt_id, result=result))
    window = window_child.window()
    window.hide()
