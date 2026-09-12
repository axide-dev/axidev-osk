"""Shared stateful button widget and declarative component builder."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import QPushButton, QWidget

from ...config.models import ButtonConfig, ComponentConfig
from ...runtime.context import Context
from ...runtime.registries import ComponentRegistry


class ButtonInteractionState(str, Enum):
    """Combined pressed and latched state of a button."""

    IDLE = "idle"
    PRESSED = "pressed"
    LATCHED = "latched"
    LATCHED_PRESSED = "latched_pressed"

    @property
    def is_active(self) -> bool:
        """Return whether the button is pressed or latched."""

        return self is not ButtonInteractionState.IDLE


class Button(QPushButton):
    """Application button with shared interaction state and pointer behavior."""

    stateChanged = Signal(object, object, str)

    def __init__(
        self,
        label: str = "",
        parent: QWidget | None = None,
        *,
        component_id: str | None = None,
        component_type: str = "button",
        latchable: bool = False,
        initial_latched: bool = False,
    ) -> None:
        super().__init__(label, parent)
        self._latchable = latchable
        self._state = self._compose_state(pressed=False, latched=initial_latched)

        self.setProperty("componentType", component_type)
        self.setProperty("componentId", component_id)
        self.setProperty("latchable", latchable)
        self.setCheckable(latchable)
        self.pressed.connect(self._handle_press)
        self.released.connect(self._handle_release)
        self._refresh_state()

    @property
    def state(self) -> ButtonInteractionState:
        """Return the current interaction state."""

        return self._state

    @property
    def latchable(self) -> bool:
        """Return whether releasing the button toggles its latched state."""

        return self._latchable

    @property
    def is_pressed(self) -> bool:
        """Return whether the button is currently pressed."""

        return self._state in {
            ButtonInteractionState.PRESSED,
            ButtonInteractionState.LATCHED_PRESSED,
        }

    @property
    def is_latched(self) -> bool:
        """Return whether the button is currently latched."""

        return self._state in {
            ButtonInteractionState.LATCHED,
            ButtonInteractionState.LATCHED_PRESSED,
        }

    @property
    def is_active(self) -> bool:
        """Return whether the button is pressed or latched."""

        return self._state.is_active

    def set_label(self, label: str, secondary_label: str | None = None) -> None:
        """Set a primary label with an optional secondary line above it."""

        self.setText(label if secondary_label is None else f"{secondary_label}\n{label}")

    def set_pressed(self, pressed: bool, *, reason: str = "set_pressed") -> None:
        """Set the pressed dimension while preserving the latched state."""

        self._transition_to(
            self._compose_state(pressed=pressed, latched=self.is_latched),
            reason,
        )

    def set_latched(self, latched: bool, *, reason: str = "set_latched") -> None:
        """Set the latched dimension when the button supports latching."""

        if not self._latchable:
            return
        self._transition_to(
            self._compose_state(pressed=self.is_pressed, latched=latched),
            reason,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Treat a right-button press as a left-button press."""

        self._forward_mouse_event(event, super().mousePressEvent)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Preserve left-button drag semantics while the right button is held."""

        self._forward_mouse_event(event, super().mouseMoveEvent)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Treat a right-button release as a left-button release."""

        self._forward_mouse_event(event, super().mouseReleaseEvent)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Treat a right-button double click as a left-button double click."""

        self._forward_mouse_event(event, super().mouseDoubleClickEvent)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Suppress the context-menu event produced by an activating right click."""

        event.accept()

    def _handle_press(self) -> None:
        self.set_pressed(True, reason="press")

    def _handle_release(self) -> None:
        if self._latchable:
            self._transition_to(
                self._compose_state(pressed=False, latched=not self.is_latched),
                "release_and_toggle_latched",
            )
        else:
            self.set_pressed(False, reason="release")

    def _transition_to(self, next_state: ButtonInteractionState, reason: str) -> None:
        if next_state == self._state:
            return
        previous = self._state
        self._state = next_state
        self._refresh_state()
        self.stateChanged.emit(previous, next_state, reason)

    def _refresh_state(self) -> None:
        self.setProperty("pressed", self.is_pressed)
        self.setProperty("latched", self.is_latched)
        self.setProperty("interactionState", self._state.value)
        self.setChecked(self.is_latched)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    @staticmethod
    def _compose_state(*, pressed: bool, latched: bool) -> ButtonInteractionState:
        if pressed and latched:
            return ButtonInteractionState.LATCHED_PRESSED
        if pressed:
            return ButtonInteractionState.PRESSED
        if latched:
            return ButtonInteractionState.LATCHED
        return ButtonInteractionState.IDLE

    @staticmethod
    def _left_mouse_event(event: QMouseEvent) -> QMouseEvent:
        button = event.button()
        buttons = event.buttons()
        if button == Qt.MouseButton.RightButton:
            button = Qt.MouseButton.LeftButton
        if buttons & Qt.MouseButton.RightButton:
            buttons = (buttons & ~Qt.MouseButton.RightButton) | Qt.MouseButton.LeftButton
        return QMouseEvent(
            event.type(),
            event.position(),
            event.globalPosition(),
            button,
            buttons,
            event.modifiers(),
        )

    def _forward_mouse_event(
        self,
        event: QMouseEvent,
        handler: Callable[[QMouseEvent], None],
    ) -> None:
        if event.button() != Qt.MouseButton.RightButton and not (
            event.buttons() & Qt.MouseButton.RightButton
        ):
            handler(event)
            return
        left_event = self._left_mouse_event(event)
        handler(left_event)
        event.setAccepted(left_event.isAccepted())


def register(registry: ComponentRegistry) -> None:
    """Register the generic button component builder."""

    registry.register("button", build_button_component)


def build_button_component(
    config: ComponentConfig,
    context: Context,
    *,
    host: QWidget | None = None,
) -> Button:
    """Build a shared button from declarative configuration."""

    del context
    if not isinstance(config, ButtonConfig):
        raise TypeError(f"Expected ButtonConfig, got {type(config).__name__}")
    button = Button(config.label, host, component_id=config.id)
    button.setProperty("role", config.role)
    if config.object_name is not None:
        button.setObjectName(config.object_name)
    if config.style_sheet is not None:
        button.setStyleSheet(config.style_sheet)
    return button


__all__ = [
    "Button",
    "ButtonInteractionState",
    "build_button_component",
    "register",
]
