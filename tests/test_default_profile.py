"""Parity tests: the default profile must reproduce the original built-in keyboard.

``EXPECTED_GRID`` and ``EXPECTED_OUTPUTS`` were measured from the original
engine-built keyboard widget before it was deleted. Each grid row is
(row, column, row span, column span, minimum width, minimum height, legend).
"""

from __future__ import annotations

import unittest

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QGridLayout, QPushButton

from axidev_osk.attachments.runtime import AttachmentRuntime
from axidev_osk.config.models import DwellClickConfig, PointerLocatorConfig
from axidev_osk.messages import RuntimeEvent
from axidev_osk.nodes import BUTTON_PRESSED, BUTTON_RELEASED
from axidev_osk.python_defaults.default_profile import KEYBOARD_OPACITY, build_default_config
from axidev_osk.python_defaults.axidev_osk.std.windows import GHOST_OPACITY
from axidev_osk.runtime.app_messages import window_close_requested
from axidev_osk.runtime.engine_messages import input_key, keyboard_status_changed, window_state_changed
from support import (
    RecordingBackend,
    build_window,
    make_test_engine,
    nodes_by_id,
    qt_app,
    record_app_actions,
    start_test_profile,
    wait_until,
)

_MODIFIERS = {"ShiftLeft", "ShiftRight", "CtrlLeft", "CtrlRight", "SuperLeft", "SuperRight", "AltLeft", "AltRight"}
_PROMPTS = ("quit-prompt", "permission-prompt", "permission-logout", "permission-terminal-opened", "permission-no-terminal")


def _keyboard_shown() -> RuntimeEvent:
    """What the engine reports once the keyboard window is on screen."""

    return window_state_changed("keyboard", visible=True, minimized=False, x=0, y=0, width=900, height=320)


class DefaultProfileHarness:
    def __init__(self, test: unittest.TestCase) -> None:
        qt_app()
        self.backend = RecordingBackend()
        self.engine = make_test_engine(self.backend)
        self.actions = record_app_actions(self.engine.dispatcher)
        self.attachments = AttachmentRuntime(self.engine.bindings, self.engine.attachments, window_lookup=lambda _id: None)
        self.profile = start_test_profile(self.engine, build_default_config())
        self.attachments.start(self.profile)
        self.window = build_window(test, self.profile.window("keyboard"), self.engine)
        self.nodes = nodes_by_id(self.window)

    def press(self, node_id: str) -> None:
        self.engine.dispatcher.dispatch(RuntimeEvent(BUTTON_PRESSED, {"node": node_id, "button": "left"}))

    def release(self, node_id: str) -> None:
        self.engine.dispatcher.dispatch(RuntimeEvent(BUTTON_RELEASED, {"node": node_id, "button": "left"}))

    def tap(self, node_id: str) -> None:
        self.press(node_id)
        self.release(node_id)

    def emit(self, *messages: RuntimeEvent) -> None:
        self.engine.dispatcher.dispatch(*messages)

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
        harness = DefaultProfileHarness(self)
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

    def test_every_key_glows_the_original_locator_color(self) -> None:
        harness = DefaultProfileHarness(self)
        harness.window.show()
        buttons = [widget for widget in harness.nodes.values() if isinstance(widget, QPushButton)]

        wait_until(lambda: all(button.property("locatorColor") for button in buttons))

        colors = {str(button.property("componentId")): button.property("locatorColor") for button in buttons}
        self.assertEqual(colors, EXPECTED_LOCATOR_COLORS)

    def test_every_key_sends_the_original_output(self) -> None:
        harness = DefaultProfileHarness(self)

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


class ConfigParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = make_test_engine(RecordingBackend()).decoder().decode_root(build_default_config())

    def _attachment(self, attachment_id: str) -> tuple[str | None, object]:
        attachment = next(attachment for attachment in self.profile.attachments if attachment.id == attachment_id)
        return attachment.target, attachment.values.initial

    def test_dwell_starts_disabled_with_the_original_tuning(self) -> None:
        window, settings = self._attachment("keyboard-dwell")
        assert isinstance(settings, DwellClickConfig)

        self.assertEqual(window, "keyboard")
        self.assertEqual(
            (
                settings.enabled,
                settings.delay_ms,
                settings.dead_zone_px,
                settings.full_speed_px_s,
                settings.stop_speed_px_s,
                settings.maximum_progress_rate,
                settings.indicator_start_progress,
                settings.direction_reversal_progress_factor,
                settings.movement_penalty_px,
                settings.distance_curve_full_px,
                settings.velocity_release_ms,
            ),
            (False, 200, 10, 20, 240, 1.75, 0.25, 0.5, 15, 200, 100),
        )

    def test_pointer_locator_glows_the_keyboard_with_the_original_settings(self) -> None:
        window, settings = self._attachment("keyboard-locator")
        assert isinstance(settings, PointerLocatorConfig)

        self.assertEqual(window, "keyboard")
        self.assertEqual(
            (settings.radius_percent, settings.maximum_opacity_percent, settings.radius_standard_deviations),
            (30, 60, 3),
        )

    def test_keyboard_is_translucent_and_prompts_are_opaque(self) -> None:
        self.assertEqual(self.profile.window("keyboard").values.initial.opacity, KEYBOARD_OPACITY)
        self.assertEqual({self.profile.window(window_id).values.initial.opacity for window_id in _PROMPTS}, {1.0})

    def test_permission_prompt_has_one_setup_action(self) -> None:
        node_ids = [node.id for node in self.profile.window("permission-prompt").content.walk()]

        self.assertEqual(node_ids.count("permission-prompt:open_terminal"), 1)

    def test_every_window_handles_its_own_close(self) -> None:
        self.assertEqual([window.id for window in self.profile.windows if window.values.initial.default_close], [])


class BehaviorParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = DefaultProfileHarness(self)

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

    def test_paired_modifiers_share_a_latch_like_the_original(self) -> None:
        harness = self.harness
        harness.tap("key:ShiftLeft")
        self.assertTrue(harness.nodes["key:ShiftRight"].property("latched"))
        harness.tap("key:ShiftRight")
        harness.tap("key:AltLeft")
        harness.tap("key:AltRight")

        self.assertEqual(
            harness.backend.sent,
            [
                ("down", "ShiftLeft", (), True),
                ("up", "ShiftLeft"),
                ("down", "AltLeft", (), True),
                ("down", "AltRight", (), True),
            ],
        )

    def test_caps_lights_from_the_system_and_flips_letters_only(self) -> None:
        harness = self.harness
        harness.emit(input_key("CapsLock", None, ("CapsLock",), True))

        self.assertTrue(harness.nodes["key:CapsLock"].property("latched"))
        self.assertEqual(harness.nodes["key:Q"].text(), "Q")  # type: ignore[attr-defined]
        self.assertEqual(harness.nodes["key:1"].text(), "1")  # type: ignore[attr-defined]

    def test_ghost_fades_and_restores_the_keyboard(self) -> None:
        harness = self.harness
        press = QEvent(QEvent.Type.MouseButtonPress)
        harness.press("ghost")

        self.assertIs(harness.engine.profile.state.get(("std", "ghosted", "keyboard")), True)
        self.assertAlmostEqual(harness.window.windowOpacity(), GHOST_OPACITY, delta=0.005)
        blocker = harness.window._input_blocker
        assert blocker is not None
        self.assertTrue(blocker.eventFilter(harness.nodes["key:A"], press))
        self.assertFalse(blocker.eventFilter(harness.nodes["ghost"], press))
        self.assertFalse(harness.nodes["ghost"].property("latched"))

        harness.press("ghost")

        self.assertAlmostEqual(harness.window.windowOpacity(), KEYBOARD_OPACITY, delta=0.005)
        self.assertIsNone(harness.window._input_blocker)
        self.assertEqual(harness.actions, [])

    def test_dwell_key_toggles_the_dwell_attachment(self) -> None:
        harness = self.harness
        enabled = ("settings", "dwell", "enabled")

        harness.tap("dwell")
        self.assertIs(harness.engine.profile.state.get(enabled), True)
        self.assertTrue(harness.nodes["dwell"].property("latched"))
        harness.tap("dwell")

        self.assertIs(harness.engine.profile.state.get(enabled), False)
        self.assertFalse(harness.nodes["dwell"].property("latched"))

    def test_hot_corner_toggles_the_keyboard(self) -> None:
        harness = self.harness
        harness.emit(_keyboard_shown())

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

    def test_second_launch_shows_the_keyboard(self) -> None:
        harness = self.harness
        harness.emit(RuntimeEvent("app.activated", {}))

        self.assertEqual(harness.actions, [("window.show", {"window": "keyboard"})])

    def test_second_launch_brings_a_ghosted_keyboard_back(self) -> None:
        harness = self.harness
        harness.emit(_keyboard_shown())
        harness.press("ghost")
        harness.emit(RuntimeEvent("app.activated", {}))

        self.assertIsNone(harness.engine.profile.state.get(("std", "ghosted", "keyboard")))
        self.assertAlmostEqual(harness.window.windowOpacity(), KEYBOARD_OPACITY, delta=0.005)
        self.assertEqual(harness.actions, [("window.show", {"window": "keyboard"})])

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


EXPECTED_LOCATOR_COLORS = {
    'key:Escape': '#b32d00',
    'key:F1': '#0059b3',
    'key:F2': '#ff0000',
    'key:F3': '#00d4ff',
    'key:F4': '#b32d00',
    'key:F5': '#0059b3',
    'key:F6': '#ff0000',
    'key:F7': '#002bff',
    'key:F8': '#ff8000',
    'key:F9': '#1e00b3',
    'key:F10': '#b38600',
    'key:F11': '#002bff',
    'key:F12': '#ff8000',
    'dwell': '#00d4ff',
    'key:PrintScreen': '#b3002d',
    'key:ScrollLock': '#0059b3',
    'key:Pause': '#ff0000',
    'key:`': '#00ff80',
    'key:1': '#ff8000',
    'key:2': '#1e00b3',
    'key:3': '#b38600',
    'key:4': '#002bff',
    'key:5': '#ff8000',
    'key:6': '#00d4ff',
    'key:7': '#b38600',
    'key:8': '#0059b3',
    'key:9': '#b32d00',
    'key:0': '#00d4ff',
    'key:-': '#ff0000',
    'key:=': '#0059b3',
    'key:Backspace': '#b32d00',
    'key:Insert': '#00ff80',
    'key:Home': '#ff0080',
    'key:PageUp': '#00b395',
    'key:Tab': '#ff0080',
    'key:Q': '#00b395',
    'key:W': '#b3002d',
    'key:E': '#00ff80',
    'key:R': '#ff0080',
    'key:T': '#00b395',
    'key:Y': '#b3002d',
    'key:U': '#00ff80',
    'key:I': '#ff0080',
    'key:O': '#00b395',
    'key:P': '#b3002d',
    'key:[': '#00ff80',
    'key:]': '#ff0080',
    'ghost': '#00b395',
    'key:Delete': '#ff8000',
    'key:End': '#00d4ff',
    'key:PageDown': '#b32d00',
    'key:CapsLock': '#0059b3',
    'key:A': '#b32d00',
    'key:S': '#00d4ff',
    'key:D': '#ff0000',
    'key:F': '#0059b3',
    'key:G': '#b32d00',
    'key:H': '#002bff',
    'key:J': '#ff0000',
    'key:K': '#1e00b3',
    'key:L': '#b38600',
    'key:;': '#002bff',
    "key:'": '#ff8000',
    'key:Enter': '#1e00b3',
    'key:ShiftLeft': '#ff0000',
    'key:\\': '#1e00b3',
    'key:Z': '#b38600',
    'key:X': '#002bff',
    'key:C': '#ff8000',
    'key:V': '#1e00b3',
    'key:B': '#b38600',
    'key:N': '#00d4ff',
    'key:M': '#ff8000',
    'key:,': '#0059b3',
    'key:.': '#b32d00',
    'key:/': '#00d4ff',
    'key:ShiftRight': '#ff0000',
    'key:Up': '#00ff80',
    'key:CtrlLeft': '#00b395',
    'key:SuperLeft': '#b3002d',
    'key:AltLeft': '#00ff80',
    'key:Space': '#ff0080',
    'key:AltRight': '#00ff80',
    'key:SuperRight': '#b3002d',
    'key:Menu': '#00b395',
    'key:CtrlRight': '#ff0080',
    'key:Left': '#00d4ff',
    'key:Down': '#b3002d',
    'key:Right': '#00b395',
}
"""Each button's glow color, measured from the original keyboard's engine-computed pattern."""


if __name__ == "__main__":
    unittest.main()
