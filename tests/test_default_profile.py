"""Parity tests: the default profile must reproduce the original built-in keyboard.

``EXPECTED_GRID`` and ``EXPECTED_OUTPUTS`` were measured from the original
engine-built keyboard widget before it was deleted. Each grid row is
(row, column, row span, column span, minimum width, minimum height, legend).
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QGridLayout, QPushButton, QWidget

from axidev_osk.messages import DataMap, MessageResult, RuntimeEvent
from axidev_osk.nodes import BUTTON_PRESSED, BUTTON_RELEASED
from axidev_osk.python_defaults.default_profile import build_default_config
from axidev_osk.runtime.engine_messages import input_key, keyboard_status_changed
from axidev_osk.runtime.events import window_close_requested
from axidev_osk.runtime.testing import make_test_context
from axidev_osk.windows.builder import build_profile_window

_MODIFIERS = {"ShiftLeft", "ShiftRight", "CtrlLeft", "CtrlRight", "SuperLeft", "SuperRight", "AltLeft", "AltRight"}
_RECORDED_ACTIONS = (
    "window.show",
    "window.hide",
    "window.set_opacity",
    "window.block_input",
    "window.unblock_input",
    "dwell.set_enabled",
    "app.quit",
    "linux.open_permission_setup",
)


class RecordingBackend:
    ready = True
    status_text = "ready"
    needs_permission_setup = False
    permission_setup_text = ""

    def __init__(self) -> None:
        self.sent: list[tuple[object, ...]] = []

    def add_observation_listener(self, listener):
        del listener
        return lambda: None

    def add_key_state_listener(self, listener):
        del listener
        return lambda: None

    def add_modifier_state_listener(self, listener):
        del listener
        return lambda: None

    def canonical_key(self, key: str) -> str:
        return key

    def press(self, key: str, mods: tuple[str, ...], repeat: bool) -> object:
        self.sent.append(("down", key, mods, repeat))
        return SimpleNamespace(key_name=key)

    def key_up(self, handle: object) -> None:
        self.sent.append(("up", getattr(handle, "key_name", None)))


class FakeOverlay:
    uses_custom_chrome = False

    def handle_show(self) -> bool:
        return True


class DefaultProfileHarness:
    def __init__(self) -> None:
        if QApplication.instance() is None:
            QApplication([])
        self.backend = RecordingBackend()
        self.context = make_test_context(self.backend)
        self.engine = self.context.engine
        self.actions: list[tuple[str, DataMap]] = []
        for name in _RECORDED_ACTIONS:
            self.context.dispatcher.register_action(
                name,
                lambda arguments: arguments,
                lambda arguments, name=name: self._record(name, arguments),
                override=True,
            )
        self.profile = self.engine.decoder().decode_root(build_default_config()).profile
        self.engine.profile.start(self.profile)
        with patch("axidev_osk.windows.builder.configure_always_on_top_window", return_value=FakeOverlay()):
            self.window = build_profile_window(self.profile.window("keyboard"), self.context)
        self.nodes = {
            child.property("componentId"): child
            for child in self.window.findChildren(QWidget)
            if child.property("componentId") is not None
        }

    def _record(self, name: str, arguments: DataMap) -> MessageResult:
        self.actions.append((name, arguments))
        return []

    def press(self, node_id: str) -> None:
        self.context.dispatcher.dispatch_event(RuntimeEvent(BUTTON_PRESSED, {"node": node_id}))

    def release(self, node_id: str) -> None:
        self.context.dispatcher.dispatch_event(RuntimeEvent(BUTTON_RELEASED, {"node": node_id}))

    def tap(self, node_id: str) -> None:
        self.press(node_id)
        self.release(node_id)

    def emit(self, event: RuntimeEvent) -> None:
        self.context.dispatcher.dispatch_event(event)

    def key_ids(self) -> list[str]:
        grid = self.nodes["keyboard-grid"]
        layout = grid.layout()
        assert isinstance(layout, QGridLayout)
        ids: list[tuple[tuple[int, int], str]] = []
        for index in range(layout.count()):
            widget = layout.itemAt(index).widget()  # type: ignore[union-attr]
            row, column, _row_span, _column_span = layout.getItemPosition(index)
            ids.append(((row, column), str(widget.property("componentId"))))
        return [node_id for _position, node_id in sorted(ids)]


class LayoutParityTests(unittest.TestCase):
    def test_grid_matches_the_original_keyboard_exactly(self) -> None:
        harness = DefaultProfileHarness()
        layout = harness.nodes["keyboard-grid"].layout()
        assert isinstance(layout, QGridLayout)
        measured = []
        for index in range(layout.count()):
            widget = layout.itemAt(index).widget()  # type: ignore[union-attr]
            assert isinstance(widget, QPushButton)
            row, column, row_span, column_span = layout.getItemPosition(index)
            measured.append((row, column, row_span, column_span, widget.minimumWidth(), widget.minimumHeight(), widget.text()))

        self.assertEqual(sorted(measured), EXPECTED_GRID)
        self.assertEqual(sum(1 for column in range(layout.columnCount()) if layout.columnStretch(column)), 72)
        self.assertEqual(sum(1 for row in range(layout.rowCount()) if layout.rowStretch(row)), 6)

    def test_every_key_sends_the_original_output(self) -> None:
        harness = DefaultProfileHarness()

        for node_id in harness.key_ids():
            if node_id in {"ghost", "dwell"}:
                continue
            harness.tap(node_id)
            if node_id.removeprefix("key:") in _MODIFIERS:
                harness.tap(node_id)

        downs = [entry for entry in harness.backend.sent if entry[0] == "down"]
        self.assertEqual(sorted(entry[1] for entry in downs), sorted(EXPECTED_OUTPUTS))
        self.assertTrue(all(entry[2] == () for entry in downs))
        self.assertEqual({entry[1] for entry in downs if not entry[3]}, {"CapsLock"})


class BehaviorParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = DefaultProfileHarness()

    def test_modifiers_hold_their_key_until_tapped_again_and_legends_follow(self) -> None:
        harness = self.harness
        harness.tap("key:ShiftLeft")
        harness.emit(input_key("ShiftLeft", None, ("Shift",), True))

        self.assertEqual(harness.backend.sent, [("down", "ShiftLeft", (), True)])
        self.assertTrue(harness.nodes["key:ShiftLeft"].property("latched"))
        self.assertEqual(harness.nodes["key:A"].text(), "A")  # type: ignore[attr-defined]
        self.assertEqual(harness.nodes["key:1"].text(), "!")  # type: ignore[attr-defined]

        harness.tap("key:ShiftLeft")
        harness.emit(input_key("ShiftLeft", None, (), False))

        self.assertEqual(harness.backend.sent[-1], ("up", "ShiftLeft"))
        self.assertEqual(harness.nodes["key:A"].text(), "a")  # type: ignore[attr-defined]

    def test_caps_lights_from_the_system_and_flips_letters_only(self) -> None:
        harness = self.harness
        harness.emit(input_key("CapsLock", None, ("CapsLock",), True))

        self.assertTrue(harness.nodes["key:CapsLock"].property("latched"))
        self.assertEqual(harness.nodes["key:Q"].text(), "Q")  # type: ignore[attr-defined]
        self.assertEqual(harness.nodes["key:1"].text(), "1")  # type: ignore[attr-defined]

    def test_ghost_fades_and_restores_the_keyboard(self) -> None:
        harness = self.harness
        harness.press("ghost")
        harness.press("ghost")

        self.assertEqual(
            harness.actions,
            [
                ("window.set_opacity", {"window": "keyboard", "opacity": 0.01}),
                ("window.block_input", {"window": "keyboard", "except": ["ghost"]}),
                ("window.set_opacity", {"window": "keyboard", "opacity": 0.85}),
                ("window.unblock_input", {"window": "keyboard"}),
            ],
        )

    def test_dwell_key_toggles_the_dwell_attachment(self) -> None:
        harness = self.harness
        harness.tap("dwell")
        harness.engine.profile.set_observed(("dwell", "keyboard-dwell", "enabled"), True)
        harness.emit(RuntimeEvent("state.changed", {"path": ["dwell", "keyboard-dwell", "enabled"]}))
        harness.tap("dwell")

        self.assertEqual(
            harness.actions,
            [
                ("dwell.set_enabled", {"dwell": "keyboard-dwell", "enabled": True}),
                ("dwell.set_enabled", {"dwell": "keyboard-dwell", "enabled": False}),
            ],
        )
        self.assertTrue(harness.nodes["dwell"].property("latched"))

    def test_hot_corner_toggles_the_keyboard(self) -> None:
        harness = self.harness
        harness.engine.profile.set_observed(("windows", "keyboard", "visible"), True)

        harness.emit(RuntimeEvent("hot_corner.triggered", {"corner": "top_left"}))

        self.assertEqual(harness.actions, [("window.hide", {"window": "keyboard"})])

    def test_closing_the_keyboard_asks_before_quitting(self) -> None:
        harness = self.harness
        harness.emit(window_close_requested("keyboard"))
        harness.release("quit-prompt:no")
        harness.emit(RuntimeEvent("app.quit_requested", {"reason": "signal"}))
        harness.release("quit-prompt:yes")

        self.assertEqual(
            harness.actions,
            [
                ("window.show", {"window": "quit-prompt"}),
                ("window.hide", {"window": "quit-prompt"}),
                ("window.show", {"window": "quit-prompt"}),
                ("app.quit", {"exit_code": 0}),
            ],
        )

    def test_permission_flow_offers_terminal_setup(self) -> None:
        harness = self.harness
        harness.emit(RuntimeEvent("keyboard.permission_required", {}))
        harness.release("permission-prompt:open_terminal")
        harness.emit(RuntimeEvent("linux.permission_setup_opened", {"opened": False}))

        self.assertEqual(
            harness.actions,
            [
                ("window.show", {"window": "permission-prompt"}),
                ("window.hide", {"window": "permission-prompt"}),
                ("linux.open_permission_setup", {}),
                ("window.show", {"window": "permission-no-terminal"}),
            ],
        )

    def test_status_label_shows_only_while_keyboard_output_is_unavailable(self) -> None:
        harness = self.harness
        status = harness.nodes["keyboard-status"]

        harness.emit(keyboard_status_changed(False, "axidev_io is not available", True, "run setup"))
        self.assertEqual(status.text(), "axidev_io is not available")  # type: ignore[attr-defined]
        self.assertFalse(status.isHidden())

        harness.emit(keyboard_status_changed(True, "ready", False, ""))
        self.assertTrue(status.isHidden())


EXPECTED_GRID = [
    (0, 0, 1, 4, 48, 48, 'Esc'),
    (0, 4, 1, 4, 48, 48, 'F1'),
    (0, 8, 1, 4, 48, 48, 'F2'),
    (0, 12, 1, 4, 48, 48, 'F3'),
    (0, 16, 1, 4, 48, 48, 'F4'),
    (0, 20, 1, 4, 48, 48, 'F5'),
    (0, 24, 1, 4, 48, 48, 'F6'),
    (0, 28, 1, 4, 48, 48, 'F7'),
    (0, 32, 1, 4, 48, 48, 'F8'),
    (0, 36, 1, 4, 48, 48, 'F9'),
    (0, 40, 1, 4, 48, 48, 'F10'),
    (0, 44, 1, 4, 48, 48, 'F11'),
    (0, 48, 1, 4, 48, 48, 'F12'),
    (0, 52, 1, 4, 48, 48, 'Dwell'),
    (0, 60, 1, 4, 48, 48, 'PrtSc'),
    (0, 64, 1, 4, 48, 48, 'ScrLk'),
    (0, 68, 1, 4, 48, 48, 'Pause'),
    (1, 0, 1, 4, 48, 48, '`'),
    (1, 4, 1, 4, 48, 48, '1'),
    (1, 8, 1, 4, 48, 48, '2'),
    (1, 12, 1, 4, 48, 48, '3'),
    (1, 16, 1, 4, 48, 48, '4'),
    (1, 20, 1, 4, 48, 48, '5'),
    (1, 24, 1, 4, 48, 48, '6'),
    (1, 28, 1, 4, 48, 48, '7'),
    (1, 32, 1, 4, 48, 48, '8'),
    (1, 36, 1, 4, 48, 48, '9'),
    (1, 40, 1, 4, 48, 48, '0'),
    (1, 44, 1, 4, 48, 48, '-'),
    (1, 48, 1, 4, 48, 48, '='),
    (1, 52, 1, 8, 96, 48, 'Backspace'),
    (1, 60, 1, 4, 48, 48, 'Ins'),
    (1, 64, 1, 4, 48, 48, 'Home'),
    (1, 68, 1, 4, 48, 48, 'PgUp'),
    (2, 0, 1, 6, 72, 48, 'Tab'),
    (2, 6, 1, 4, 48, 48, 'q'),
    (2, 10, 1, 4, 48, 48, 'w'),
    (2, 14, 1, 4, 48, 48, 'e'),
    (2, 18, 1, 4, 48, 48, 'r'),
    (2, 22, 1, 4, 48, 48, 't'),
    (2, 26, 1, 4, 48, 48, 'y'),
    (2, 30, 1, 4, 48, 48, 'u'),
    (2, 34, 1, 4, 48, 48, 'i'),
    (2, 38, 1, 4, 48, 48, 'o'),
    (2, 42, 1, 4, 48, 48, 'p'),
    (2, 46, 1, 4, 48, 48, '['),
    (2, 50, 1, 4, 48, 48, ']'),
    (2, 54, 1, 4, 48, 48, 'Ghost'),
    (2, 60, 1, 4, 48, 48, 'Del'),
    (2, 64, 1, 4, 48, 48, 'End'),
    (2, 68, 1, 4, 48, 48, 'PgDn'),
    (3, 0, 1, 7, 84, 48, 'Caps'),
    (3, 7, 1, 4, 48, 48, 'a'),
    (3, 11, 1, 4, 48, 48, 's'),
    (3, 15, 1, 4, 48, 48, 'd'),
    (3, 19, 1, 4, 48, 48, 'f'),
    (3, 23, 1, 4, 48, 48, 'g'),
    (3, 27, 1, 4, 48, 48, 'h'),
    (3, 31, 1, 4, 48, 48, 'j'),
    (3, 35, 1, 4, 48, 48, 'k'),
    (3, 39, 1, 4, 48, 48, 'l'),
    (3, 43, 1, 4, 48, 48, ';'),
    (3, 47, 1, 4, 48, 48, "'"),
    (3, 51, 1, 9, 108, 48, 'Enter'),
    (4, 0, 1, 5, 60, 48, 'Shift'),
    (4, 5, 1, 4, 48, 48, '\\'),
    (4, 9, 1, 4, 48, 48, 'z'),
    (4, 13, 1, 4, 48, 48, 'x'),
    (4, 17, 1, 4, 48, 48, 'c'),
    (4, 21, 1, 4, 48, 48, 'v'),
    (4, 25, 1, 4, 48, 48, 'b'),
    (4, 29, 1, 4, 48, 48, 'n'),
    (4, 33, 1, 4, 48, 48, 'm'),
    (4, 37, 1, 4, 48, 48, ','),
    (4, 41, 1, 4, 48, 48, '.'),
    (4, 45, 1, 4, 48, 48, '/'),
    (4, 49, 1, 11, 132, 48, 'Shift'),
    (4, 64, 1, 4, 48, 48, '↑'),
    (5, 0, 1, 5, 60, 48, 'Ctrl'),
    (5, 5, 1, 5, 60, 48, 'Super'),
    (5, 10, 1, 5, 60, 48, 'Alt'),
    (5, 15, 1, 25, 300, 48, 'Space'),
    (5, 40, 1, 5, 60, 48, 'AltGr'),
    (5, 45, 1, 5, 60, 48, 'Super'),
    (5, 50, 1, 5, 60, 48, 'Menu'),
    (5, 55, 1, 5, 60, 48, 'Ctrl'),
    (5, 60, 1, 4, 48, 48, '←'),
    (5, 64, 1, 4, 48, 48, '↓'),
    (5, 68, 1, 4, 48, 48, '→'),
]

EXPECTED_OUTPUTS = ['Escape', 'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12', 'PrintScreen', 'ScrollLock', 'Pause', '`', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '=', 'Backspace', 'Insert', 'Home', 'PageUp', 'Tab', 'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', '[', ']', 'Delete', 'End', 'PageDown', 'CapsLock', 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ';', "'", 'Enter', 'ShiftLeft', '\\', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', '/', 'ShiftRight', 'Up', 'CtrlLeft', 'SuperLeft', 'AltLeft', 'Space', 'AltRight', 'SuperRight', 'Menu', 'CtrlRight', 'Left', 'Down', 'Right']


if __name__ == "__main__":
    unittest.main()
