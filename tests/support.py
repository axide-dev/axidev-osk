"""Shared test doubles: the Qt application, a recording keyboard backend, an overlay, and app-action recorders."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QApplication

from axidev_osk.messages import DataMap, MessageResult
from axidev_osk.runtime.app_messages import (
    APP_QUIT,
    LINUX_OPEN_PERMISSION_SETUP,
    WINDOW_BLOCK_INPUT,
    WINDOW_CLOSE,
    WINDOW_HIDE,
    WINDOW_SET_OPACITY,
    WINDOW_SHOW,
    WINDOW_UNBLOCK_INPUT,
    decode_app_quit,
    decode_window,
    decode_window_block_input,
    decode_window_set_opacity,
)
from axidev_osk.runtime.decoding import decode_empty
from axidev_osk.runtime.dispatcher import Dispatcher
from axidev_osk.services.keyboard.io import KeyPressHandle

_APP_ACTIONS: dict[str, Callable[[DataMap], object]] = {
    WINDOW_SHOW: decode_window,
    WINDOW_HIDE: decode_window,
    WINDOW_CLOSE: decode_window,
    WINDOW_SET_OPACITY: decode_window_set_opacity,
    WINDOW_BLOCK_INPUT: decode_window_block_input,
    WINDOW_UNBLOCK_INPUT: decode_window,
    APP_QUIT: decode_app_quit,
    LINUX_OPEN_PERMISSION_SETUP: decode_empty,
}


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
        self._canonical = canonical

    def initialize(self) -> bool:
        self.initialized += 1
        return self.ready

    def shutdown(self) -> None:
        return None

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

    uses_custom_chrome = False

    def handle_show(self) -> bool:
        return True

    def move_by(self, dx: int, dy: int) -> None:
        del dx, dy

    def resize_by(self, dx: int, dy: int) -> None:
        del dx, dy


def record_app_actions(dispatcher: Dispatcher) -> list[tuple[str, DataMap]]:
    """Register the window and app actions with their real decoders and record each one instead of running it.

    ``ApplicationRuntime`` owns these actions; profile tests built on
    ``make_test_context`` record them to check what a profile asks for.
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
