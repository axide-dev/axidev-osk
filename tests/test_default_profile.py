"""Parity tests: the default profile must reproduce the original built-in keyboard.

``EXPECTED_GRID`` and ``EXPECTED_OUTPUTS`` were measured from the original
engine-built keyboard widget before it was deleted. Each grid row is
(row, column, row span, column span, minimum width, minimum height, legend).
The minimum sizes were later scaled down on purpose to a 32 px key unit;
the cells, legends, and outputs are still the original measurements.
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
from axidev_osk.runtime.profile_runtime import state_set
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

_MODIFIERS = {"LFSH", "RTSH", "LCTL", "RCTL", "LWIN", "RWIN", "LALT", "RALT"}
_PROMPTS = ("quit-prompt", "permission-prompt", "permission-logout", "permission-terminal-opened", "permission-no-terminal")


def _keyboard_shown() -> RuntimeEvent:
    """What the engine reports once the keyboard window is on screen."""

    return window_state_changed(
        "keyboard", visible=True, minimized=False, x=0, y=0, width=900, height=320, content_width=900, content_height=320
    )


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
        buttons = [harness.nodes[node_id] for node_id in EXPECTED_LOCATOR_COLORS]

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
        self.profile = make_test_engine(RecordingBackend()).decoder().decode_config(build_default_config()).active

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
        harness.tap("key:LFSH")
        harness.emit(input_key("ShiftLeft", None, ("Shift",), True))

        self.assertEqual(harness.backend.sent, [("down", "ShiftLeft", (), True)])
        self.assertTrue(harness.nodes["key:LFSH"].property("latched"))
        self.assertEqual(harness.nodes["key:AC01"].text(), "A")  # type: ignore[attr-defined]
        self.assertEqual(harness.nodes["key:AE01"].text(), "!")  # type: ignore[attr-defined]

        harness.tap("key:LFSH")
        harness.emit(input_key("ShiftLeft", None, (), False))

        self.assertEqual(harness.backend.sent[-1], ("up", "ShiftLeft"))
        self.assertEqual(harness.nodes["key:AC01"].text(), "a")  # type: ignore[attr-defined]

    def test_paired_modifiers_share_a_latch_like_the_original(self) -> None:
        harness = self.harness
        harness.tap("key:LFSH")
        self.assertTrue(harness.nodes["key:RTSH"].property("latched"))
        harness.tap("key:RTSH")
        harness.tap("key:LALT")
        harness.tap("key:RALT")

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

        self.assertTrue(harness.nodes["key:CAPS"].property("latched"))
        self.assertEqual(harness.nodes["key:AD01"].text(), "Q")  # type: ignore[attr-defined]
        self.assertEqual(harness.nodes["key:AE01"].text(), "1")  # type: ignore[attr-defined]

    def test_ghost_fades_and_restores_the_keyboard(self) -> None:
        harness = self.harness
        press = QEvent(QEvent.Type.MouseButtonPress)
        harness.press("ghost")

        self.assertIs(harness.engine.profile.state.get(("std", "ghosted", "keyboard")), True)
        self.assertAlmostEqual(harness.window.windowOpacity(), GHOST_OPACITY, delta=0.005)
        blocker = harness.window._input_blocker
        assert blocker is not None
        self.assertTrue(blocker.eventFilter(harness.nodes["key:AC01"], press))
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

    def test_settings_strip_drives_opacity_and_the_dwell_attachment(self) -> None:
        harness = self.harness

        self.assertTrue(harness.nodes["keyboard:strip:controls"].isHidden())
        harness.tap("keyboard:strip:toggle")
        self.assertFalse(harness.nodes["keyboard:strip:controls"].isHidden())

        harness.tap("keyboard:opacity:down")
        self.assertAlmostEqual(harness.window.windowOpacity(), KEYBOARD_OPACITY - 0.05, delta=0.005)

        harness.tap("keyboard:dwell-menu")
        self.assertFalse(harness.nodes["keyboard:dwell-menu:panel"].isHidden())
        harness.tap("keyboard:dwell-enabled")
        dwell = harness.attachments.for_window("keyboard").dwell
        assert dwell is not None
        self.assertTrue(dwell.enabled)
        self.assertTrue(harness.nodes["dwell"].property("latched"))

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


class LayoutSwitchTests(unittest.TestCase):
    def test_both_keyboards_follow_the_layout_setting_to_dvorak(self) -> None:
        for profile_name, node_id in (("default", "key:AD01"), ("wheel", "wheel:slice:9")):
            with self.subTest(profile_name):
                qt_app()
                backend = RecordingBackend()
                engine = make_test_engine(backend)
                config = build_default_config()
                config["active_profile"] = profile_name
                window = build_window(self, start_test_profile(engine, config).window("keyboard"), engine)
                engine.dispatcher.dispatch(state_set("settings.layout", "dvorak"))
                if profile_name == "wheel":
                    # Slice 9 opens the top letter row; its first key sits on the left, slice 7.
                    engine.dispatcher.dispatch(RuntimeEvent(BUTTON_RELEASED, {"node": node_id, "button": "left"}))
                    node_id = "wheel:slice:7"
                key = nodes_by_id(window)[node_id]

                self.assertEqual(key.text(), "'")  # type: ignore[attr-defined]
                engine.dispatcher.dispatch(RuntimeEvent(BUTTON_PRESSED, {"node": node_id, "button": "left"}))
                engine.dispatcher.dispatch(RuntimeEvent(BUTTON_RELEASED, {"node": node_id, "button": "left"}))
                self.assertEqual(backend.sent, [("down", "'", (), True), ("up", "'")])


EXPECTED_GRID = [
    (0, 0, 1, 4, 32, 32, 'Esc'),
    (0, 4, 1, 4, 32, 32, 'F1'),
    (0, 8, 1, 4, 32, 32, 'F2'),
    (0, 12, 1, 4, 32, 32, 'F3'),
    (0, 16, 1, 4, 32, 32, 'F4'),
    (0, 20, 1, 4, 32, 32, 'F5'),
    (0, 24, 1, 4, 32, 32, 'F6'),
    (0, 28, 1, 4, 32, 32, 'F7'),
    (0, 32, 1, 4, 32, 32, 'F8'),
    (0, 36, 1, 4, 32, 32, 'F9'),
    (0, 40, 1, 4, 32, 32, 'F10'),
    (0, 44, 1, 4, 32, 32, 'F11'),
    (0, 48, 1, 4, 32, 32, 'F12'),
    (0, 52, 1, 4, 32, 32, 'Dwell'),
    (0, 60, 1, 4, 32, 32, 'PrtSc'),
    (0, 64, 1, 4, 32, 32, 'ScrLk'),
    (0, 68, 1, 4, 32, 32, 'Pause'),
    (1, 0, 1, 4, 32, 32, '`'),
    (1, 4, 1, 4, 32, 32, '1'),
    (1, 8, 1, 4, 32, 32, '2'),
    (1, 12, 1, 4, 32, 32, '3'),
    (1, 16, 1, 4, 32, 32, '4'),
    (1, 20, 1, 4, 32, 32, '5'),
    (1, 24, 1, 4, 32, 32, '6'),
    (1, 28, 1, 4, 32, 32, '7'),
    (1, 32, 1, 4, 32, 32, '8'),
    (1, 36, 1, 4, 32, 32, '9'),
    (1, 40, 1, 4, 32, 32, '0'),
    (1, 44, 1, 4, 32, 32, '-'),
    (1, 48, 1, 4, 32, 32, '='),
    (1, 52, 1, 8, 64, 32, 'Backspace'),
    (1, 60, 1, 4, 32, 32, 'Ins'),
    (1, 64, 1, 4, 32, 32, 'Home'),
    (1, 68, 1, 4, 32, 32, 'PgUp'),
    (2, 0, 1, 6, 48, 32, 'Tab'),
    (2, 6, 1, 4, 32, 32, 'q'),
    (2, 10, 1, 4, 32, 32, 'w'),
    (2, 14, 1, 4, 32, 32, 'e'),
    (2, 18, 1, 4, 32, 32, 'r'),
    (2, 22, 1, 4, 32, 32, 't'),
    (2, 26, 1, 4, 32, 32, 'y'),
    (2, 30, 1, 4, 32, 32, 'u'),
    (2, 34, 1, 4, 32, 32, 'i'),
    (2, 38, 1, 4, 32, 32, 'o'),
    (2, 42, 1, 4, 32, 32, 'p'),
    (2, 46, 1, 4, 32, 32, '['),
    (2, 50, 1, 4, 32, 32, ']'),
    (2, 54, 1, 4, 32, 32, 'Ghost'),
    (2, 60, 1, 4, 32, 32, 'Del'),
    (2, 64, 1, 4, 32, 32, 'End'),
    (2, 68, 1, 4, 32, 32, 'PgDn'),
    (3, 0, 1, 7, 56, 32, 'Caps'),
    (3, 7, 1, 4, 32, 32, 'a'),
    (3, 11, 1, 4, 32, 32, 's'),
    (3, 15, 1, 4, 32, 32, 'd'),
    (3, 19, 1, 4, 32, 32, 'f'),
    (3, 23, 1, 4, 32, 32, 'g'),
    (3, 27, 1, 4, 32, 32, 'h'),
    (3, 31, 1, 4, 32, 32, 'j'),
    (3, 35, 1, 4, 32, 32, 'k'),
    (3, 39, 1, 4, 32, 32, 'l'),
    (3, 43, 1, 4, 32, 32, ';'),
    (3, 47, 1, 4, 32, 32, "'"),
    (3, 51, 1, 9, 72, 32, 'Enter'),
    (4, 0, 1, 5, 40, 32, 'Shift'),
    (4, 5, 1, 4, 32, 32, '\\'),
    (4, 9, 1, 4, 32, 32, 'z'),
    (4, 13, 1, 4, 32, 32, 'x'),
    (4, 17, 1, 4, 32, 32, 'c'),
    (4, 21, 1, 4, 32, 32, 'v'),
    (4, 25, 1, 4, 32, 32, 'b'),
    (4, 29, 1, 4, 32, 32, 'n'),
    (4, 33, 1, 4, 32, 32, 'm'),
    (4, 37, 1, 4, 32, 32, ','),
    (4, 41, 1, 4, 32, 32, '.'),
    (4, 45, 1, 4, 32, 32, '/'),
    (4, 49, 1, 11, 88, 32, 'Shift'),
    (4, 64, 1, 4, 32, 32, '↑'),
    (5, 0, 1, 5, 40, 32, 'Ctrl'),
    (5, 5, 1, 5, 40, 32, 'Super'),
    (5, 10, 1, 5, 40, 32, 'Alt'),
    (5, 15, 1, 25, 200, 32, 'Space'),
    (5, 40, 1, 5, 40, 32, 'AltGr'),
    (5, 45, 1, 5, 40, 32, 'Super'),
    (5, 50, 1, 5, 40, 32, 'Menu'),
    (5, 55, 1, 5, 40, 32, 'Ctrl'),
    (5, 60, 1, 4, 32, 32, '←'),
    (5, 64, 1, 4, 32, 32, '↓'),
    (5, 68, 1, 4, 32, 32, '→'),
]

EXPECTED_OUTPUTS = ['Escape', 'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12', 'PrintScreen', 'ScrollLock', 'Pause', '`', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '=', 'Backspace', 'Insert', 'Home', 'PageUp', 'Tab', 'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', '[', ']', 'Delete', 'End', 'PageDown', 'CapsLock', 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ';', "'", 'Enter', 'ShiftLeft', '\\', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', '/', 'ShiftRight', 'Up', 'CtrlLeft', 'SuperLeft', 'AltLeft', 'Space', 'AltRight', 'SuperRight', 'Menu', 'CtrlRight', 'Left', 'Down', 'Right']


EXPECTED_LOCATOR_COLORS = {
    'key:ESC': '#b32d00',
    'key:FK01': '#0059b3',
    'key:FK02': '#ff0000',
    'key:FK03': '#00d4ff',
    'key:FK04': '#b32d00',
    'key:FK05': '#0059b3',
    'key:FK06': '#ff0000',
    'key:FK07': '#002bff',
    'key:FK08': '#ff8000',
    'key:FK09': '#1e00b3',
    'key:FK10': '#b38600',
    'key:FK11': '#002bff',
    'key:FK12': '#ff8000',
    'dwell': '#00d4ff',
    'key:PRSC': '#ff0080',
    'key:SCLK': '#0059b3',
    'key:PAUS': '#b32d00',
    'key:TLDE': '#00ff80',
    'key:AE01': '#ff8000',
    'key:AE02': '#1e00b3',
    'key:AE03': '#b38600',
    'key:AE04': '#002bff',
    'key:AE05': '#ff8000',
    'key:AE06': '#00d4ff',
    'key:AE07': '#b38600',
    'key:AE08': '#0059b3',
    'key:AE09': '#b32d00',
    'key:AE10': '#00d4ff',
    'key:AE11': '#ff0000',
    'key:AE12': '#0059b3',
    'key:BKSP': '#b32d00',
    'key:INS': '#00ff80',
    'key:HOME': '#ff0000',
    'key:PGUP': '#00b395',
    'key:TAB': '#ff0080',
    'key:AD01': '#00b395',
    'key:AD02': '#b3002d',
    'key:AD03': '#00ff80',
    'key:AD04': '#ff0080',
    'key:AD05': '#00b395',
    'key:AD06': '#b3002d',
    'key:AD07': '#00ff80',
    'key:AD08': '#ff0080',
    'key:AD09': '#00b395',
    'key:AD10': '#b3002d',
    'key:AD11': '#00ff80',
    'key:AD12': '#ff0080',
    'ghost': '#00b395',
    'key:DELE': '#b3002d',
    'key:END': '#00d4ff',
    'key:PGDN': '#ff8000',
    'key:CAPS': '#0059b3',
    'key:AC01': '#b32d00',
    'key:AC02': '#00d4ff',
    'key:AC03': '#ff0000',
    'key:AC04': '#0059b3',
    'key:AC05': '#b32d00',
    'key:AC06': '#002bff',
    'key:AC07': '#ff0000',
    'key:AC08': '#1e00b3',
    'key:AC09': '#b38600',
    'key:AC10': '#002bff',
    "key:AC11": '#ff8000',
    'key:RTRN': '#1e00b3',
    'key:LFSH': '#ff0000',
    'key:LSGT': '#1e00b3',
    'key:AB01': '#b38600',
    'key:AB02': '#002bff',
    'key:AB03': '#ff8000',
    'key:AB04': '#1e00b3',
    'key:AB05': '#b38600',
    'key:AB06': '#00d4ff',
    'key:AB07': '#ff8000',
    'key:AB08': '#0059b3',
    'key:AB09': '#b32d00',
    'key:AB10': '#00d4ff',
    'key:RTSH': '#ff0000',
    'key:UP': '#00ff80',
    'key:LCTL': '#00b395',
    'key:LWIN': '#b3002d',
    'key:LALT': '#00ff80',
    'key:SPCE': '#ff0080',
    'key:RALT': '#00ff80',
    'key:RWIN': '#b3002d',
    'key:MENU': '#00b395',
    'key:RCTL': '#ff0080',
    'key:LEFT': '#00d4ff',
    'key:DOWN': '#b3002d',
    'key:RGHT': '#00b395',
}
"""Each button's glow color, measured from the original keyboard's engine-computed pattern."""


if __name__ == "__main__":
    unittest.main()
