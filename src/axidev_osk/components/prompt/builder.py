"""Prompt component builder."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ...config.models import ButtonConfig, ComponentConfig, PromptConfig
from ...runtime.context import Context
from ...runtime.events import PromptResolved
from ...runtime.identity import stable_id
from ...runtime.registries import ComponentRegistry

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


def register(registry: ComponentRegistry) -> None:
    """Register the prompt component builder.

    Args:
        registry: Component registry owned by the runtime context.

    Returns:
        None.

    Side effects:
        Mutates the registry.
    """

    registry.register("prompt", build_prompt_component)


def build_prompt_component(
    config: ComponentConfig,
    context: Context,
    *,
    host: QWidget | None = None,
) -> QWidget:
    """Build a prompt component.

    Args:
        config: Prompt component config.
        context: Runtime context, used to dispatch ``PromptResolved`` events.
        host: Unused; accepted for registry signature parity.

    Returns:
        Constructed prompt root widget containing message, optional hint, and
        action buttons.

    Side effects:
        Wires button click signals to dispatch ``PromptResolved``. Prompt
        window lifecycle remains owned by the runtime prompt flow.
    """

    del host
    if not isinstance(config, PromptConfig):
        raise TypeError(f"Expected PromptConfig, got {type(config).__name__}")
    widget = QWidget()
    widget.setProperty("componentType", "prompt")
    widget.setProperty("componentId", config.id)
    layout = QVBoxLayout(widget)

    message_row = QHBoxLayout()
    message_row.setSpacing(14)
    glyph_label = QLabel(config.prompt_glyph, widget)
    glyph_label.setFixedSize(40, 40)
    glyph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge_bg = "#d83a3a" if config.danger else "#ffd866"
    badge_fg = "#fff5f5" if config.danger else "#1a1a1a"
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
    message_label = QLabel(config.message, widget)
    message_label.setTextFormat(Qt.TextFormat.PlainText)
    message_label.setWordWrap(True)
    message_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    message_label.setStyleSheet("QLabel { margin: 0px; padding: 0px; }")
    message_row.addWidget(message_label, 1)
    layout.addLayout(message_row)

    if config.hint:
        hint_label = QLabel(config.hint, widget)
        hint_label.setTextFormat(Qt.TextFormat.PlainText)
        hint_label.setWordWrap(True)
        hint_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        hint_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        hint_label.setStyleSheet(
            "QLabel {"
            "  color: rgba(220, 220, 220, 0.65);"
            "  font-size: 14px;"
            "  font-style: italic;"
            "  margin: 0px;"
            "  padding: 2px 2px;"
            "  border-left: 2px solid rgba(180, 180, 180, 0.35);"
            "}"
        )
        layout.addWidget(hint_label)

    buttons = QHBoxLayout()
    buttons.setSpacing(8)
    for button_config in config.buttons:
        button = context.components.build(button_config, context, host=widget)
        if not isinstance(button, QPushButton):
            raise TypeError("Prompt button builder must return QPushButton")
        button.clicked.connect(lambda _checked=False, item=button_config: _resolve_prompt(widget, context, config.id, item))
        buttons.addWidget(button)
    layout.addLayout(buttons)
    return widget


def prompt_button_config(parent_id: str, *, role: str, label: str) -> ButtonConfig:
    """Create a prompt button config preserving existing styles.

    Args:
        parent_id: Stable ID of the parent prompt component.
        role: Semantic role string (e.g. ``"accepted"`` or ``"rejected"``).
        label: Visible button text (the role glyph is prepended automatically).

    Returns:
        Constructed ``ButtonConfig`` with role-appropriate styling preserved
        from the legacy confirmation window.

    Side effects:
        None.
    """

    object_name = "confirmAcceptButton" if role == "accepted" else "confirmRejectButton"
    glyph = "✔" if role == "accepted" else "✖"
    style_sheet = _ACCEPT_BUTTON_QSS if role == "accepted" else _REJECT_BUTTON_QSS
    return ButtonConfig(
        id=stable_id(parent_id, "button", role, stable_override=f"{parent_id}:button:{role}"),
        label=f"{glyph}  {label}",
        role=role,
        object_name=object_name,
        style_sheet=style_sheet,
    )


def _resolve_prompt(window_child: QWidget, context: Context, prompt_id: str, button: ButtonConfig) -> None:
    """Dispatch the prompt resolution event.

    Args:
        window_child: Any widget inside the prompt window; accepted so signal
            wiring can keep a stable signature without owning window lifecycle.
        context: Runtime context used to dispatch the event.
        prompt_id: Stable ID of the resolving prompt component.
        button: Button config describing which action was clicked.

    Returns:
        None.

    Side effects:
        Dispatches ``PromptResolved``.
    """

    del window_child
    context.dispatcher.dispatch_event(PromptResolved(prompt_id=prompt_id, result=button.role))
