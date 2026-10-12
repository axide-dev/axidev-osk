"""Test helpers for building a real engine around a fake keyboard backend.

Tests get the production dispatcher, engine, node kinds, and attachment kinds,
so they exercise the same queue and state paths the app uses. Only the
keyboard backend and spawned processes are replaced.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from ..config.profile import ProfileConfig
from ..services.keyboard import KeyboardService
from .dispatcher import Dispatcher
from .engine import Engine, build_engine
from .qt_wake import QtDispatcherWake


class RecordingProcesses:
    """Process effects that record spawn requests instead of starting programs."""

    def __init__(self) -> None:
        self.spawned: list[tuple[tuple[str, ...], str, bool]] = []

    def spawn(self, argv: tuple[str, ...], tag: str, detached: bool) -> None:
        self.spawned.append((argv, tag, detached))


def make_test_engine(keyboard_backend: Any) -> Engine:
    """Build an engine whose keyboard service wraps a test keyboard backend.

    The dispatcher has every built-in event, the engine actions, node kinds,
    and attachment kinds registered; the window and app actions belong to
    ``ApplicationRuntime``.
    """

    return make_keyboard_test_engine(keyboard_backend)[0]


def make_keyboard_test_engine(keyboard_backend: Any) -> tuple[Engine, KeyboardService]:
    """Build a test engine and return the keyboard service it sends key effects to.

    The service is bound to the dispatcher but not started, so tests decide
    when output initializes.
    """

    dispatcher = Dispatcher()
    # Kept alive by the dispatcher's wake callback, like the app's own wake.
    QtDispatcherWake(dispatcher)
    keyboard = KeyboardService(cast(Any, keyboard_backend))
    engine = build_engine(dispatcher, keyboard=keyboard, processes=RecordingProcesses())
    keyboard.bind_dispatcher(dispatcher)
    return engine, keyboard


def start_test_profile(engine: Engine, root_config: Mapping[str, Any]) -> ProfileConfig:
    """Decode ``root_config`` with ``engine`` and start its active profile."""

    profile = engine.decoder().decode_root(root_config)
    engine.profile.start(profile)
    return profile
