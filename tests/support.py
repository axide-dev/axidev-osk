"""Shared test doubles and helpers: the Qt application, a recording keyboard backend, an overlay, window building, app-action recorders, and a real engine around a fake keyboard backend."""

from __future__ import annotations

import unittest
from collections.abc import Callable, Mapping
from typing import Any, cast
from unittest.mock import patch

from PySide6.QtCore import QDeadlineTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from axidev_osk.attachments.runtime import WindowAttachments
from axidev_osk.config.models import HotCornerConfig
from axidev_osk.config.profile import ProfileConfig, WindowConfig
from axidev_osk.messages import DataMap, MessageResult
from axidev_osk.runtime.app_messages import (
    APP_QUIT,
    LINUX_OPEN_PERMISSION_SETUP,
    WINDOW_CLICK,
    WINDOW_CLOSE,
    WINDOW_HIDE,
    WINDOW_MOVE_BY,
    WINDOW_RESIZE_BY,
    WINDOW_SHOW,
    decode_app_quit,
    decode_window,
    decode_window_click,
    decode_window_delta,
)
from axidev_osk.runtime.decoding import decode_empty
from axidev_osk.runtime.dispatcher import Dispatcher
from axidev_osk.runtime.engine import Engine, build_engine
from axidev_osk.runtime.qt_wake import QtDispatcherWake
from axidev_osk.services.keyboard import KeyboardService
from axidev_osk.services.keyboard.io import KeyPressHandle
from axidev_osk.windows.builder import RuntimeWindow, build_profile_window

_APP_ACTIONS: dict[str, Callable[[DataMap], object]] = {
    WINDOW_SHOW: decode_window,
    WINDOW_HIDE: decode_window,
    WINDOW_CLOSE: decode_window,
    WINDOW_MOVE_BY: decode_window_delta,
    WINDOW_RESIZE_BY: decode_window_delta,
    WINDOW_CLICK: decode_window_click,
    APP_QUIT: decode_app_quit,
    LINUX_OPEN_PERMISSION_SETUP: decode_empty,
}


HOT_CORNER_COLORS = {
    "indicator_background": "#000000",
    "indicator_track": "#808080",
    "indicator_progress": "#FFFFFF",
    "indicator_center": "#404040",
}
"""Indicator colors for tests; profiles always give their own."""


def hot_corner_config(**fields: Any) -> HotCornerConfig:
    return HotCornerConfig(**HOT_CORNER_COLORS, **fields)


def wait_until(condition: Callable[[], object], timeout_ms: int = 2000) -> None:
    """Process Qt events until ``condition`` holds; a fixed wait loses a click whose timer fires late on a busy machine."""

    deadline = QDeadlineTimer(timeout_ms)
    while not condition():
        if deadline.hasExpired():
            raise AssertionError(f"condition not met within {timeout_ms} ms")
        QTest.qWait(10)


def qt_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication)
    return app


class RecordingBackend:
    """A keyboard backend with the real adapter's surface that records what it sends."""

    ready = True
    status_text = "ready"
    needs_permission_setup = False
    permission_setup_text = ""

    def __init__(self, canonical: Callable[[str], str] = lambda key: key) -> None:
        self.sent: list[tuple[object, ...]] = []
        self.observers: list[Callable[[object], None]] = []
        self.initialized = 0
        self.shutdowns = 0
        self._canonical = canonical

    def initialize(self) -> bool:
        self.initialized += 1
        return self.ready

    def shutdown(self) -> None:
        self.shutdowns += 1

    def stop_listening(self) -> None:
        self.sent.append(("stop_listening",))

    def observe(self, observation: object) -> None:
        """Deliver a key observation to every listener, as the listener thread does."""

        for listener in tuple(self.observers):
            listener(observation)

    def add_observation_listener(self, listener: Callable[[object], None]) -> Callable[[], None]:
        self.observers.append(listener)
        return lambda: self.observers.remove(listener)

    def canonical_key(self, key: str) -> str:
        return self._canonical(key)

    def press(self, key: str, mods: tuple[str, ...], repeat: bool) -> KeyPressHandle:
        self.sent.append(("down", key, mods, repeat))
        return KeyPressHandle(key_name=key, mods=mods, repeats=repeat)

    def key_up(self, press: KeyPressHandle) -> None:
        self.sent.append(("up", press.key_name))

    def tap(self, key: str, mods: tuple[str, ...]) -> None:
        self.sent.append(("tap", key, mods))

    def type_text(self, text: str) -> None:
        self.sent.append(("type", text))


class FakeOverlay:
    """An overlay controller that does nothing platform-specific."""

    def __init__(self, *, uses_custom_chrome: bool = False, uses_runtime_pointer_drag: bool = False) -> None:
        self.uses_custom_chrome = uses_custom_chrome
        self.uses_runtime_pointer_drag = uses_runtime_pointer_drag

    def handle_show(self) -> bool:
        return True

    def position(self) -> tuple[int, int]:
        return (0, 0)

    def move_by(self, dx: int, dy: int) -> None:
        del dx, dy

    def restore_position(self, x: int, y: int) -> None:
        del x, y

    def keep_on_screen(self) -> None:
        return None

    def resize_by(self, dx: int, dy: int) -> None:
        del dx, dy


def build_window(
    test: unittest.TestCase,
    config: WindowConfig,
    engine: Engine,
    *,
    attachments: WindowAttachments | None = None,
    overlay: object | None = None,
) -> RuntimeWindow:
    """Build a profile window with a fake overlay; the window is deleted when ``test`` ends."""

    with patch("axidev_osk.windows.builder.configure_always_on_top_window", return_value=overlay or FakeOverlay()):
        window = build_profile_window(config, engine, attachments=attachments)
    test.addCleanup(window.deleteLater)
    return window


def nodes_by_id(root: QWidget) -> dict[str, QWidget]:
    """Every widget built for a node under ``root``, by node ID."""

    return {
        str(child.property("componentId")): child
        for child in root.findChildren(QWidget)
        if child.property("componentId") is not None
    }


def find_node(root: QWidget, node_id: str) -> QWidget:
    widget = nodes_by_id(root).get(node_id)
    if widget is None:
        raise AssertionError(f"node {node_id!r} not found")
    return widget


def record_app_actions(dispatcher: Dispatcher) -> list[tuple[str, DataMap]]:
    """Register the window and app actions with their real decoders and record each one instead of running it.

    ``ApplicationRuntime`` owns these actions; profile tests built on
    ``make_test_engine`` record them to check what a profile asks for.
    """

    recorded: list[tuple[str, DataMap]] = []

    def recorder(name: str, decoder: Callable[[DataMap], object]) -> tuple[Callable[[DataMap], DataMap], Callable[[DataMap], MessageResult]]:
        def decode(arguments: DataMap) -> DataMap:
            decoder(arguments)
            return arguments

        def record(arguments: DataMap) -> MessageResult:
            recorded.append((name, arguments))
            return []

        return decode, record

    for name, decoder in _APP_ACTIONS.items():
        decode, record = recorder(name, decoder)
        dispatcher.register_action(name, decode, record)
    return recorded


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

    profile = engine.decoder().decode_config(root_config).active
    engine.profile.start(profile)
    return profile


def has_pending(dispatcher: Dispatcher) -> bool:
    """Whether any message is waiting in the dispatcher's queue, inbox, or idle actions."""

    with dispatcher._inbox_lock:
        return bool(dispatcher._queue or dispatcher._inbox or dispatcher._idle)
