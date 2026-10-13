from __future__ import annotations

import unittest
from typing import Any

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QWidget

from axidev_osk.messages import DataMap, RuntimeEvent
from axidev_osk.nodes import BUTTON_PRESSED, BUTTON_RELEASED
from axidev_osk.python_defaults import axidev_osk
from axidev_osk.python_defaults.axidev_osk import std
from axidev_osk.python_defaults.axidev_osk.std import keys, prompts, windows
from axidev_osk.config.variables import decode_state
from axidev_osk.runtime.engine_messages import OBSERVED_VARIABLES, input_key, keyboard_reset
from axidev_osk.runtime.state import StateTree
from axidev_osk.runtime.testing import make_test_engine, start_test_profile
from support import RecordingBackend, build_window, find_node, nodes_by_id, qt_app, record_app_actions


class StdHarness:
    def __init__(
        self,
        test: unittest.TestCase,
        children: list[axidev_osk.Map],
        *,
        on: dict[str, Any] | None = None,
        **window_fields: Any,
    ) -> None:
        qt_app()
        self.backend = RecordingBackend()
        self.engine = make_test_engine(self.backend)
        self.window_actions = record_app_actions(self.engine.dispatcher)
        root = axidev_osk.config(
            active_profile="p",
            profiles={
                "p": axidev_osk.profile(
                    windows=[axidev_osk.window(id="pad", title="Pad", content=axidev_osk.box(id="root", children=children), **window_fields)],
                    state=std.with_state(),
                    on=std.with_handlers(on),
                )
            },
        )
        self.profile = start_test_profile(self.engine, root)
        self.window = build_window(test, self.profile.window("pad"), self.engine)

    def tap(self, node_id: str) -> None:
        self.engine.dispatcher.dispatch(RuntimeEvent(BUTTON_PRESSED, {"node": node_id}))
        self.engine.dispatcher.dispatch(RuntimeEvent(BUTTON_RELEASED, {"node": node_id}))

    def observe(self, key: str, pressed: bool, modifiers: tuple[str, ...] = ()) -> None:
        self.engine.dispatcher.dispatch(input_key(key, None, modifiers, pressed))

    def widget(self, node_id: str) -> QWidget:
        return find_node(self.window, node_id)

    def state(self, *path: str) -> object:
        return self.engine.profile.state.get(path)


class KeyTests(unittest.TestCase):
    def test_letter_sends_its_key_and_legend_follows_shift_and_caps(self) -> None:
        harness = StdHarness(self, [keys.letter("a")])
        key = harness.widget("key:A")

        harness.tap("key:A")
        self.assertEqual(harness.backend.sent, [("down", "A", (), True), ("up", "A")])
        self.assertEqual(key.text(), "a")  # type: ignore[attr-defined]

        harness.observe("ShiftLeft", True)
        self.assertEqual(key.text(), "A")  # type: ignore[attr-defined]
        harness.observe("ShiftLeft", True, ("CapsLock",))
        self.assertEqual(key.text(), "a")  # type: ignore[attr-defined]

    def test_held_modifier_holds_its_key_from_first_tap_to_second(self) -> None:
        harness = StdHarness(self, [keys.modifier("Shift", "ShiftLeft")])
        shift = harness.widget("key:ShiftLeft")

        harness.tap("key:ShiftLeft")
        self.assertEqual(harness.backend.sent, [("down", "ShiftLeft", (), True)])
        self.assertTrue(shift.property("latched"))

        harness.tap("key:ShiftLeft")
        self.assertEqual(harness.backend.sent[-1], ("up", "ShiftLeft"))
        self.assertFalse(shift.property("latched"))

    def test_one_shot_modifier_applies_to_the_next_key_only(self) -> None:
        harness = StdHarness(self, [keys.modifier("Shift", "ShiftLeft", {"mode": "one_shot"}), keys.letter("a")])

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

    def test_a_key_releases_the_one_shot_its_press_held_even_if_cancelled_meanwhile(self) -> None:
        harness = StdHarness(self, [keys.modifier("Shift", "ShiftLeft", {"mode": "one_shot"}), keys.letter("a")])
        dispatch = harness.engine.dispatcher.dispatch

        harness.tap("key:ShiftLeft")
        dispatch(RuntimeEvent(BUTTON_PRESSED, {"node": "key:A"}))
        harness.tap("key:ShiftLeft")
        dispatch(RuntimeEvent(BUTTON_RELEASED, {"node": "key:A"}))

        self.assertEqual(
            harness.backend.sent,
            [("down", "ShiftLeft", (), False), ("down", "A", (), True), ("up", "A"), ("up", "ShiftLeft")],
        )
        self.assertEqual(harness.state("std", "held"), {})

    def test_a_one_shot_set_while_a_key_is_down_waits_for_the_next_key(self) -> None:
        harness = StdHarness(self, [keys.modifier("Shift", "ShiftLeft", {"mode": "one_shot"}), keys.letter("a")])
        dispatch = harness.engine.dispatcher.dispatch

        dispatch(RuntimeEvent(BUTTON_PRESSED, {"node": "key:A"}))
        harness.tap("key:ShiftLeft")
        dispatch(RuntimeEvent(BUTTON_RELEASED, {"node": "key:A"}))
        harness.tap("key:A")

        self.assertEqual(
            harness.backend.sent,
            [
                ("down", "A", (), True),
                ("up", "A"),
                ("down", "ShiftLeft", (), False),
                ("down", "A", (), True),
                ("up", "A"),
                ("up", "ShiftLeft"),
            ],
        )

    def test_options_set_to_none_count_as_absent(self) -> None:
        harness = StdHarness(
            self,
            [keys.key("A", "A", {"repeat": None}), keys.modifier("Ctrl", "CtrlLeft", {"mode": None, "repeat": None})]
        )

        harness.tap("key:A")
        harness.tap("key:CtrlLeft")

        self.assertEqual(harness.backend.sent, [("down", "A", (), True), ("up", "A"), ("down", "CtrlLeft", (), True)])

    def test_one_shot_altgr_holds_the_real_altgr_key(self) -> None:
        harness = StdHarness(self, [keys.modifier("AltGr", "AltRight", {"mode": "one_shot"}), keys.key("E", "E")])

        harness.tap("key:AltRight")
        harness.tap("key:E")

        self.assertEqual(
            harness.backend.sent,
            [("down", "AltRight", (), False), ("down", "E", (), True), ("up", "E"), ("up", "AltRight")],
        )

    def test_left_and_right_twins_share_a_latch_and_release_the_original_press(self) -> None:
        harness = StdHarness(self, [keys.modifier("Shift", "ShiftLeft"), keys.modifier("Shift", "ShiftRight")])

        harness.tap("key:ShiftLeft")
        self.assertTrue(harness.widget("key:ShiftRight").property("latched"))
        harness.tap("key:ShiftRight")

        self.assertEqual(harness.backend.sent, [("down", "ShiftLeft", (), True), ("up", "ShiftLeft")])
        self.assertFalse(harness.widget("key:ShiftLeft").property("latched"))

    def test_twins_that_differ_keep_separate_latches_unless_one_is_named(self) -> None:
        harness = StdHarness(
            self,
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
        harness = StdHarness(self, [keys.lock("Caps", "CapsLock")])
        caps = harness.widget("key:CapsLock")

        harness.tap("key:CapsLock")
        self.assertEqual(harness.backend.sent, [("down", "CapsLock", (), False), ("up", "CapsLock")])
        self.assertFalse(caps.property("latched"))

        harness.observe("CapsLock", True, ("CapsLock",))
        self.assertTrue(caps.property("latched"))

    def test_reset_clears_latches(self) -> None:
        harness = StdHarness(self, [keys.modifier("Ctrl", "CtrlLeft")])
        harness.tap("key:CtrlLeft")

        harness.engine.dispatcher.dispatch(keyboard_reset())

        self.assertEqual(harness.state("std", "latched"), {})
        self.assertFalse(harness.widget("key:CtrlLeft").property("latched"))

    def test_keys_whose_names_contain_dots_work(self) -> None:
        harness = StdHarness(self, [keys.shifted(".", ">", "."), keys.modifier("Dot mod", ".", {"id": "dot.mod"})])

        harness.observe(".", True)
        harness.tap("dot.mod")

        self.assertTrue(harness.widget("key:.").property("pressed"))
        self.assertTrue(harness.widget("dot.mod").property("latched"))

    def test_reading_through_a_plain_value_gives_none(self) -> None:
        harness = StdHarness(self, [keys.letter("a")])
        harness.engine.profile.set_observed(("keyboard", "status"), "plain")

        self.assertIsNone(axidev_osk.read(harness.engine.profile.state.view(), "keyboard.status.inner"))
        self.assertEqual(axidev_osk.read(harness.engine.profile.state.view(), "keyboard.status"), "plain")

    def test_any_field_can_be_overridden(self) -> None:
        def custom(ctx: Any, event: Any) -> list[axidev_osk.Map]:
            return [axidev_osk.keyboard.type_text("moo")]

        node = keys.letter("a", {"id": "cow", "on_release": custom, "cell": {"row": 0, "column": 0}})

        self.assertEqual((node["id"], node["on_release"], node["cell"]), ("cow", custom, {"row": 0, "column": 0}))


class WindowHelperTests(unittest.TestCase):
    def test_ghost_button_fades_blocks_and_restores(self) -> None:
        harness = StdHarness(
            self,
            [windows.ghost_button("pad"), keys.letter("a")],
            opacity=windows.ghost_opacity("pad", 0.85),
            input_blocked=windows.ghost_blocked("pad"),
        )
        press = QEvent(QEvent.Type.MouseButtonPress)

        harness.tap("ghost:pad")

        self.assertIs(harness.state("std", "ghosted", "pad"), True)
        self.assertAlmostEqual(harness.window.windowOpacity(), windows.GHOST_OPACITY, delta=0.005)
        blocker = harness.window._input_blocker
        assert blocker is not None
        self.assertTrue(blocker.eventFilter(harness.widget("key:A"), press))
        self.assertFalse(blocker.eventFilter(harness.widget("ghost:pad"), press))

        harness.tap("ghost:pad")

        self.assertIsNone(harness.state("std", "ghosted", "pad"))
        self.assertAlmostEqual(harness.window.windowOpacity(), 0.85, delta=0.005)
        self.assertIsNone(harness.window._input_blocker)
        self.assertEqual(harness.window_actions, [])

    def test_corner_toggle_brings_back_ghosted_and_minimized_windows(self) -> None:
        def run(**window: bool) -> list[str]:
            state = StateTree()
            state.declare(OBSERVED_VARIABLES, "engine")
            state.declare(decode_state(std.with_state(), "test"), "profile")
            ghosted = window.pop("ghosted", False)
            if ghosted:
                state.set(("std", "ghosted", "pad"), True)
            if window:
                state.set(("windows", "pad"), window)
            return [item["action"] for item in windows.corner_toggle(state.view(), "pad")]

        self.assertEqual(run(visible=True, ghosted=True), ["state.set", "window.show"])
        self.assertEqual(run(visible=True, minimized=True), ["window.show"])
        self.assertEqual(run(visible=True), ["window.hide"])
        self.assertEqual(run(), ["window.show"])


class PromptTests(unittest.TestCase):
    def test_an_empty_hint_still_gets_its_row_as_lua_would(self) -> None:
        prompt = prompts.prompt_window("p", title="T", message="M", buttons=[], hint="")

        rows = [row["id"] for row in prompt["content"]["children"]]

        self.assertIn("p:hint", rows)

    def test_prompt_window_builds_with_button_callbacks_and_takes_opts(self) -> None:
        qt_app()
        engine = make_test_engine(RecordingBackend())
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
        profile = start_test_profile(engine, axidev_osk.config(active_profile="p", profiles={"p": axidev_osk.profile(windows=[prompt])}))
        window = build_window(self, profile.window("quit"), engine)
        engine.dispatcher.dispatch(RuntimeEvent(BUTTON_RELEASED, {"node": "quit:no"}))

        widgets = nodes_by_id(window)
        self.assertEqual(widgets["quit:message"].text(), "Close it?")  # type: ignore[attr-defined]
        self.assertEqual(widgets["quit:no"].text(), "Keep")  # type: ignore[attr-defined]
        self.assertEqual(widgets["quit:yes"].objectName(), "confirmAcceptButton")
        self.assertEqual(answers, ["quit:no"])
        self.assertFalse(profile.window("quit").show_on_start)
        self.assertEqual(profile.window("quit").values.initial.minimum_size, (500, 200))


if __name__ == "__main__":
    unittest.main()
