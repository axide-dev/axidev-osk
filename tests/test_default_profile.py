"""Parity tests: the default profile must reproduce the original built-in keyboard.

``EXPECTED_GRID`` and ``EXPECTED_OUTPUTS`` were measured from the original
engine-built keyboard widget before it was deleted. Each grid row is
(row, column, row span, column span, minimum width, minimum height, legend).
"""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QGridLayout, QPushButton

from axidev_osk.attachments import DwellOptions, PointerLocatorOptions
from axidev_osk.attachments.runtime import AttachmentRuntime
from axidev_osk.messages import RuntimeEvent
from axidev_osk.nodes import BUTTON_PRESSED, BUTTON_RELEASED
from axidev_osk.python_defaults.default_profile import KEYBOARD_OPACITY, build_default_config
from axidev_osk.python_defaults.osk.std.windows import GHOST_OPACITY
from axidev_osk.runtime.app_messages import window_close_requested
from axidev_osk.runtime.engine_messages import input_key, keyboard_status_changed, window_state_changed
from axidev_osk.runtime.testing import make_test_context, start_test_profile
from support import RecordingBackend, build_window, nodes_by_id, qt_app, record_app_actions

_MODIFIERS = {"ShiftLeft", "ShiftRight", "CtrlLeft", "CtrlRight", "SuperLeft", "SuperRight", "AltLeft", "AltRight"}
_PROMPTS = ("quit-prompt", "permission-prompt", "permission-logout", "permission-terminal-opened", "permission-no-terminal")


def _keyboard_report(*, blocked: bool, opacity: float) -> RuntimeEvent:
    """What the engine reports about the keyboard window once actions on it have run."""

    return window_state_changed(
        "keyboard",
        visible=True,
        minimized=False,
        opacity=opacity,
        configured_opacity=KEYBOARD_OPACITY,
        input_blocked=blocked,
    )


class DefaultProfileHarness:
    def __init__(self, test: unittest.TestCase) -> None:
        qt_app()
        self.backend = RecordingBackend()
        self.context = make_test_context(self.backend)
        self.engine = self.context.engine
        self.actions = record_app_actions(self.context.dispatcher)
        self.attachments = AttachmentRuntime(self.context.dispatcher, self.engine.profile, window_lookup=lambda _id: None)
        self.profile = start_test_profile(self.context, build_default_config())
        self.attachments.start(self.profile)
        self.window = build_window(test, self.profile.window("keyboard"), self.context)
        self.nodes = nodes_by_id(self.window)

    def press(self, node_id: str) -> None:
        self.context.dispatcher.dispatch(RuntimeEvent(BUTTON_PRESSED, {"node": node_id}))

    def release(self, node_id: str) -> None:
        self.context.dispatcher.dispatch(RuntimeEvent(BUTTON_RELEASED, {"node": node_id}))

    def tap(self, node_id: str) -> None:
        self.press(node_id)
        self.release(node_id)

    def emit(self, *messages: RuntimeEvent) -> None:
        self.context.dispatcher.dispatch(*messages)

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
        self.profile = make_test_context(RecordingBackend()).engine.decoder().decode_root(build_default_config())

    def _options(self, attachment_id: str) -> object:
        return next(attachment.options for attachment in self.profile.attachments if attachment.id == attachment_id)

    def test_dwell_starts_disabled_with_the_original_tuning(self) -> None:
        options = self._options("keyboard-dwell")
        assert isinstance(options, DwellOptions)
        settings = options.settings

        self.assertEqual(options.window, "keyboard")
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
        options = self._options("keyboard-locator")
        assert isinstance(options, PointerLocatorOptions)

        self.assertEqual(options.window, "keyboard")
        self.assertEqual(
            (options.settings.radius_percent, options.settings.maximum_opacity_percent, options.settings.radius_standard_deviations),
            (30, 60, 3),
        )

    def test_keyboard_is_translucent_and_prompts_are_opaque(self) -> None:
        self.assertEqual(self.profile.window("keyboard").opacity, KEYBOARD_OPACITY)
        self.assertEqual({self.profile.window(window_id).opacity for window_id in _PROMPTS}, {1.0})

    def test_permission_prompt_has_one_setup_action(self) -> None:
        node_ids = [node.id for node in self.profile.window("permission-prompt").content.walk()]

        self.assertEqual(node_ids.count("permission-prompt:open_terminal"), 1)

    def test_only_the_keyboard_handles_its_own_close(self) -> None:
        self.assertEqual(
            [window.id for window in self.profile.windows if not window.default_close],
            ["keyboard"],
        )


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
        harness.press("ghost")
        harness.emit(_keyboard_report(blocked=True, opacity=GHOST_OPACITY))
        self.assertFalse(harness.nodes["ghost"].property("latched"))
        harness.press("ghost")

        self.assertEqual(
            harness.actions,
            [
                ("window.block_input", {"window": "keyboard", "except": ["ghost"]}),
                ("window.set_opacity", {"window": "keyboard", "opacity": GHOST_OPACITY}),
                ("window.set_opacity", {"window": "keyboard", "opacity": KEYBOARD_OPACITY}),
                ("window.unblock_input", {"window": "keyboard"}),
            ],
        )

    def test_dwell_key_toggles_the_dwell_attachment(self) -> None:
        harness = self.harness
        enabled = ("dwell", "keyboard-dwell", "enabled")

        harness.tap("dwell")
        self.assertIs(harness.engine.profile.state.get(enabled), True)
        self.assertTrue(harness.nodes["dwell"].property("latched"))
        harness.tap("dwell")

        self.assertIs(harness.engine.profile.state.get(enabled), False)
        self.assertFalse(harness.nodes["dwell"].property("latched"))

    def test_hot_corner_toggles_the_keyboard(self) -> None:
        harness = self.harness
        harness.emit(_keyboard_report(blocked=False, opacity=KEYBOARD_OPACITY))

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
        harness.press("ghost")
        harness.emit(_keyboard_report(blocked=True, opacity=GHOST_OPACITY))
        harness.actions.clear()
        harness.emit(RuntimeEvent("app.activated", {}))

        self.assertEqual(
            harness.actions,
            [
                ("window.set_opacity", {"window": "keyboard", "opacity": KEYBOARD_OPACITY}),
                ("window.unblock_input", {"window": "keyboard"}),
                ("window.show", {"window": "keyboard"}),
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
