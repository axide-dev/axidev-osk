"""Button component registration and primitives."""

from .builder import build_button_component, register
from .key import create_key_button, key_button_state_machine
from .state import KeyInteractionState, KeyStateChange, KeyStateMachine

__all__ = [
    "KeyInteractionState",
    "KeyStateChange",
    "KeyStateMachine",
    "build_button_component",
    "create_key_button",
    "key_button_state_machine",
    "register",
]
