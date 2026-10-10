"""Test helpers for building a real runtime context around a fake keyboard backend.

Tests get the production dispatcher, engine, node kinds, and attachment kinds,
so they exercise the same queue and state paths the app uses. Only the
keyboard backend and spawned processes are replaced.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from ..config.profile import ProfileConfig
from ..services.keyboard import KeyboardService
from .context import Context
from .dispatcher import Dispatcher
from .engine import build_engine


class RecordingProcesses:
    """Process effects that record spawn requests instead of starting programs."""

    def __init__(self) -> None:
        self.spawned: list[tuple[tuple[str, ...], str, bool]] = []

    def spawn(self, argv: tuple[str, ...], tag: str, detached: bool) -> None:
        self.spawned.append((argv, tag, detached))


def make_test_context(keyboard_backend: Any) -> Context:
    """Build a runtime ``Context`` wrapping a test keyboard backend.

    The dispatcher has every built-in event, the engine actions, node kinds,
    and attachment kinds registered; the window and app actions belong to
    ``ApplicationRuntime``.
    """

    return make_keyboard_test_context(keyboard_backend)[0]


def make_keyboard_test_context(keyboard_backend: Any) -> tuple[Context, KeyboardService]:
    """Build a test ``Context`` and return the keyboard service its engine sends key effects to.

    The service is bound to the context but not started, so tests decide when
    output initializes.
    """

    dispatcher = Dispatcher()
    keyboard = KeyboardService(cast(Any, keyboard_backend))
    engine = build_engine(dispatcher, keyboard=keyboard, processes=RecordingProcesses())
    context = Context(dispatcher=dispatcher, engine=engine)
    keyboard.bind_context(context)
    return context, keyboard


def start_test_profile(context: Context, root_config: Mapping[str, Any]) -> ProfileConfig:
    """Decode ``root_config`` with the context's engine and start its active profile."""

    profile = context.engine.decoder().decode_root(root_config)
    context.engine.profile.start(profile)
    return profile
