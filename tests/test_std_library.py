from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from PySide6.QtWidgets import QWidget

from axidev_osk.messages import DataMap, RuntimeEvent
from axidev_osk.nodes import BUTTON_PRESSED, BUTTON_RELEASED
from axidev_osk.python_defaults import osk
from axidev_osk.python_defaults.osk import std
from axidev_osk.python_defaults.osk.std import keys, prompts, windows
from axidev_osk.runtime.engine_messages import input_key, keyboard_reset, window_state_changed
from axidev_osk.runtime.state import StateTree
from axidev_osk.runtime.testing import make_test_context, start_test_profile
from axidev_osk.windows.builder import build_profile_window
from support import FakeOverlay, RecordingBackend, qt_app, record_app_actions


def _window_report(window: str, *, blocked: bool, opacity: float, configured: float) -> RuntimeEvent:
    """What the engine reports about a window once actions on it have run."""

    return window_state_changed(
        window, visible=True, minimized=False, opacity=opacity, configured_opacity=configured, input_blocked=blocked
    )


class StdHarness:
    def __init__(self, children: list[osk.Map], *, on: dict[str, Any] | None = None) -> None:
        qt_app()
        self.backend = RecordingBackend()
        self.context = make_test_context(self.backend)
        self.engine = self.context.engine
        self.window_actions = record_app_actions(self.context.dispatcher)
        root = osk.config(
            active_profile="p",
            profiles={
                "p": osk.profile(
                    windows=[osk.window(id="pad", title="Pad", content=osk.box(id="root", children=children))],
                    on=std.with_handlers(on),
                )
            },
        )
        self.profile = start_test_profile(self.context, root)
        with patch("axidev_osk.windows.builder.configure_always_on_top_window", return_value=FakeOverlay()):
            self.window = build_profile_window(self.profile.window("pad"), self.context)

    def tap(self, node_id: str) -> None:
        self.context.dispatcher.dispatch(RuntimeEvent(BUTTON_PRESSED, {"node": node_id}))
        self.context.dispatcher.dispatch(RuntimeEvent(BUTTON_RELEASED, {"node": node_id}))

    def observe(self, key: str, pressed: bool, modifiers: tuple[str, ...] = ()) -> None:
        self.context.dispatcher.dispatch(input_key(key, None, modifiers, pressed))

    def widget(self, node_id: str) -> QWidget:
        for child in self.window.findChildren(QWidget):
            if child.property("componentId") == node_id:
                return child
        raise AssertionError(node_id)

    def state(self, *path: str) -> object:
        return self.engine.profile.state.get(path)


class KeyTests(unittest.TestCase):
    def test_letter_sends_its_key_and_legend_follows_shift_and_caps(self) -> None:
        harness = StdHarness([keys.letter("a")])
        key = harness.widget("key:A")

        harness.tap("key:A")
        self.assertEqual(harness.backend.sent, [("down", "A", (), True), ("up", "A")])
        self.assertEqual(key.text(), "a")  # type: ignore[attr-defined]

        harness.observe("ShiftLeft", True)
        self.assertEqual(key.text(), "A")  # type: ignore[attr-defined]
        harness.observe("ShiftLeft", True, ("CapsLock",))
        self.assertEqual(key.text(), "a")  # type: ignore[attr-defined]

    def test_held_modifier_holds_its_key_from_first_tap_to_second(self) -> None:
        harness = StdHarness([keys.modifier("Shift", "ShiftLeft")])
        shift = harness.widget("key:ShiftLeft")

        harness.tap("key:ShiftLeft")
        self.assertEqual(harness.backend.sent, [("down", "ShiftLeft", (), True)])
        self.assertTrue(shift.property("latched"))

        harness.tap("key:ShiftLeft")
        self.assertEqual(harness.backend.sent[-1], ("up", "ShiftLeft"))
        self.assertFalse(shift.property("latched"))

    def test_one_shot_modifier_applies_to_the_next_key_only(self) -> None:
        harness = StdHarness([keys.modifier("Shift", "ShiftLeft", {"mode": "one_shot"}), keys.letter("a")])

        harness.tap("key:ShiftLeft")
        self.assertEqual(harness.widget("key:A").text(), "A")  # type: ignore[attr-defined]
        harness.tap("key:A")
        harness.tap("key:A")

        self.assertEqual(
            harness.backend.sent,
            [
                ("down", "ShiftLeft", (), False),
                ("down", "A", (), True),
                ("up", "A"),
                ("up", "ShiftLeft"),
                ("down", "A", (), True),
                ("up", "A"),
            ],
        )

    def test_one_shot_altgr_holds_the_real_altgr_key(self) -> None:
        harness = StdHarness([keys.modifier("AltGr", "AltRight", {"mode": "one_shot"}), keys.key("E", "E")])

        harness.tap("key:AltRight")
        harness.tap("key:E")

        self.assertEqual(
            harness.backend.sent,
            [("down", "AltRight", (), False), ("down", "E", (), True), ("up", "E"), ("up", "AltRight")],
        )

    def test_left_and_right_twins_share_a_latch_and_release_the_original_press(self) -> None:
        harness = StdHarness([keys.modifier("Shift", "ShiftLeft"), keys.modifier("Shift", "ShiftRight")])

        harness.tap("key:ShiftLeft")
        self.assertTrue(harness.widget("key:ShiftRight").property("latched"))
        harness.tap("key:ShiftRight")

        self.assertEqual(harness.backend.sent, [("down", "ShiftLeft", (), True), ("up", "ShiftLeft")])
        self.assertFalse(harness.widget("key:ShiftLeft").property("latched"))

    def test_twins_that_differ_keep_separate_latches_unless_one_is_named(self) -> None:
        harness = StdHarness(
            [
                keys.modifier("Alt", "AltLeft"),
                keys.modifier("AltGr", "AltRight"),
                keys.modifier("Ctrl", "CtrlLeft", {"latch": "chord"}),
                keys.modifier("Super", "SuperLeft", {"latch": "chord"}),
            ]
        )

        harness.tap("key:AltLeft")
        harness.tap("key:AltRight")
        harness.tap("key:CtrlLeft")

        self.assertEqual(
            harness.backend.sent,
            [("down", "AltLeft", (), True), ("down", "AltRight", (), True), ("down", "CtrlLeft", (), True)],
        )
        self.assertTrue(harness.widget("key:SuperLeft").property("latched"))

    def test_lock_key_taps_without_repeat_and_lights_from_the_system(self) -> None:
        harness = StdHarness([keys.lock("Caps", "CapsLock")])
        caps = harness.widget("key:CapsLock")

        harness.tap("key:CapsLock")
        self.assertEqual(harness.backend.sent, [("down", "CapsLock", (), False), ("up", "CapsLock")])
        self.assertFalse(caps.property("latched"))

        harness.observe("CapsLock", True, ("CapsLock",))
        self.assertTrue(caps.property("latched"))

    def test_reset_clears_latches(self) -> None:
        harness = StdHarness([keys.modifier("Ctrl", "CtrlLeft")])
        harness.tap("key:CtrlLeft")

        harness.context.dispatcher.dispatch(keyboard_reset())

        self.assertIsNone(harness.state("std", "latched"))
        self.assertFalse(harness.widget("key:CtrlLeft").property("latched"))

    def test_keys_whose_names_contain_dots_work(self) -> None:
        harness = StdHarness([keys.shifted(".", ">", "."), keys.modifier("Dot mod", ".", {"id": "dot.mod"})])

        harness.observe(".", True)
        harness.tap("dot.mod")

        self.assertTrue(harness.widget("key:.").property("pressed"))
        self.assertTrue(harness.widget("dot.mod").property("latched"))

    def test_any_field_can_be_overridden(self) -> None:
        def custom(ctx: Any, event: Any) -> list[osk.Map]:
            return [osk.keyboard.type_text("moo")]

        node = keys.letter("a", {"id": "cow", "on_release": custom, "cell": {"row": 0, "column": 0}})

        self.assertEqual((node["id"], node["on_release"], node["cell"]), ("cow", custom, {"row": 0, "column": 0}))


class WindowHelperTests(unittest.TestCase):
    def test_ghost_button_fades_blocks_and_restores(self) -> None:
        harness = StdHarness([windows.ghost_button("pad")])

        harness.tap("ghost:pad")
        harness.context.dispatcher.dispatch(_window_report("pad", blocked=True, opacity=0.01, configured=0.85))
        self.assertIs(harness.state("std", "ghosted", "pad"), True)
        harness.tap("ghost:pad")

        self.assertEqual(
            harness.window_actions,
            [
                ("window.block_input", {"window": "pad", "except": ["ghost:pad"]}),
                ("window.set_opacity", {"window": "pad", "opacity": 0.01}),
                ("window.set_opacity", {"window": "pad", "opacity": 0.85}),
                ("window.unblock_input", {"window": "pad"}),
            ],
        )
        self.assertIsNone(harness.state("std", "ghosted", "pad"))

    def test_ghost_flag_clears_when_the_engine_reports_the_window_unblocked(self) -> None:
        harness = StdHarness([windows.ghost_button("pad")])
        harness.tap("ghost:pad")
        self.assertIs(harness.state("std", "ghosted", "pad"), True)

        harness.context.dispatcher.dispatch(_window_report("pad", blocked=False, opacity=0.85, configured=0.85))

        self.assertIsNone(harness.state("std", "ghosted", "pad"))

    def test_corner_toggle_brings_back_ghosted_and_minimized_windows(self) -> None:
        def run(state: DataMap) -> list[str]:
            return [item["action"] for item in windows.corner_toggle(StateTree(state).view(), "pad")]

        ghosted = {"std": {"ghosted": {"pad": True}}, "windows": {"pad": {"visible": True, "configured_opacity": 0.85}}}
        self.assertEqual(run(ghosted), ["window.set_opacity", "window.unblock_input", "state.set", "window.show"])
        self.assertEqual(run({"windows": {"pad": {"minimized": True, "visible": True}}}), ["window.show"])
        self.assertEqual(run({"windows": {"pad": {"visible": True}}}), ["window.hide"])
        self.assertEqual(run({}), ["window.show"])


class PromptTests(unittest.TestCase):
    def test_prompt_window_builds_with_button_callbacks_and_takes_opts(self) -> None:
        qt_app()
        context = make_test_context(RecordingBackend())
        answers: list[str] = []

        def answer(ctx: Any, event: DataMap) -> None:
            answers.append(str(event["node"]))

        prompt = prompts.prompt_window(
            "quit",
            title="Close?",
            message="Close it?",
            hint="Hide it instead.",
            danger=True,
            buttons=[
                prompts.prompt_button("quit:yes", "Yes", answer, accept=True),
                prompts.prompt_button("quit:no", "No", answer, accept=False, opts={"label": "Keep"}),
            ],
            opts={"minimum_size": [500, 200]},
        )
        profile = start_test_profile(context, osk.config(active_profile="p", profiles={"p": osk.profile(windows=[prompt])}))
        with patch("axidev_osk.windows.builder.configure_always_on_top_window", return_value=FakeOverlay()):
            window = build_profile_window(profile.window("quit"), context)
        self.addCleanup(window.deleteLater)
        context.dispatcher.dispatch(RuntimeEvent(BUTTON_RELEASED, {"node": "quit:no"}))

        widgets = {child.property("componentId"): child for child in window.findChildren(QWidget)}
        self.assertEqual(widgets["quit:message"].text(), "Close it?")  # type: ignore[attr-defined]
        self.assertEqual(widgets["quit:no"].text(), "Keep")  # type: ignore[attr-defined]
        self.assertEqual(widgets["quit:yes"].objectName(), "confirmAcceptButton")
        self.assertEqual(answers, ["quit:no"])
        self.assertFalse(profile.window("quit").show_on_start)
        self.assertEqual(profile.window("quit").minimum_size, (500, 200))


if __name__ == "__main__":
    unittest.main()
