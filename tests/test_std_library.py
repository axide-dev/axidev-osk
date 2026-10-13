from __future__ import annotations

import unittest
from typing import Any

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from axidev_osk.messages import DataMap, RuntimeEvent
from axidev_osk.nodes import BUTTON_PRESSED, BUTTON_RELEASED
from axidev_osk.python_defaults import axidev_osk
from axidev_osk.python_defaults.axidev_osk import std
from axidev_osk.python_defaults.axidev_osk.std import controls, failures, keys, layouts, prompts, wheel, windows
from axidev_osk.config.variables import decode_state
from axidev_osk.runtime.dispatcher import ACTION_FAILED
from axidev_osk.runtime.engine_messages import OBSERVED_VARIABLES, input_key, keyboard_reset, window_state_changed
from axidev_osk.runtime.dispatcher import CHECK_HINT
from axidev_osk.runtime.profile_runtime import callback_failed, state_set
from axidev_osk.runtime.state import StateTree
from support import RecordingBackend, build_window, find_node, make_test_engine, nodes_by_id, qt_app, record_app_actions, start_test_profile


class StdHarness:
    def __init__(
        self,
        test: unittest.TestCase,
        children: list[axidev_osk.Map],
        *,
        on: dict[str, Any] | None = None,
        state: dict[str, Any] | None = None,
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
                    state=std.with_state(state),
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


class LayoutTests(unittest.TestCase):
    def test_a_layout_missing_a_position_is_rejected_when_built(self) -> None:
        tables = {"one": {"AD01": layouts.letter("q")}, "two": {}}

        with self.assertRaisesRegex(ValueError, "Layout 'two' has no entry for AD01"):
            keys.at("AD01", tables, lambda state: "one")

    def test_a_position_key_shows_and_sends_whatever_the_active_layout_puts_there(self) -> None:
        tables = {"one": {"AD01": layouts.letter("q")}, "two": {"AD01": layouts.shifted("&", "1", "&")}}
        harness = StdHarness(
            self,
            [keys.at("AD01", tables, lambda state: axidev_osk.read(state, "layout"))],
            state={"layout": axidev_osk.var("string", "one")},
        )
        key = harness.widget("key:AD01")

        harness.tap("key:AD01")
        self.assertEqual(key.text(), "q")  # type: ignore[attr-defined]

        harness.engine.dispatcher.dispatch(state_set("layout", "two"))
        harness.tap("key:AD01")
        harness.observe("ShiftLeft", True)

        self.assertEqual(key.text(), "1")  # type: ignore[attr-defined]
        self.assertEqual(
            harness.backend.sent,
            [("down", "Q", (), True), ("up", "Q"), ("down", "&", (), True), ("up", "&")],
        )


class WheelTests(unittest.TestCase):
    def _harness(self) -> StdHarness:
        return StdHarness(self, [wheel.wheel("w", wheel.TKL, layouts.LAYOUTS, lambda state: "us")])

    def test_picking_slices_opens_menus_then_sends_the_key_and_returns_to_the_top(self) -> None:
        harness = self._harness()

        harness.tap("w:slice:9")
        self.assertEqual(harness.widget("w:slice:8").text(), "w")  # type: ignore[attr-defined]
        harness.tap("w:slice:8")
        harness.tap("w:slice:5")

        # A key slice holds its key like a key button does, repeating until released.
        self.assertEqual(
            harness.backend.sent,
            [("down", "W", (), True), ("up", "W"), ("down", "Space", (), True), ("up", "Space")],
        )
        self.assertIsNone(harness.state("std", "wheels", "w"))

    def test_a_modifier_latches_until_picked_again(self) -> None:
        harness = self._harness()

        harness.tap("w:slice:6")
        harness.tap("w:slice:7")
        harness.tap("w:slice:6")
        self.assertTrue(harness.widget("w:slice:7").property("latched"))
        harness.tap("w:center")
        harness.tap("w:slice:9")
        harness.tap("w:slice:7")
        harness.tap("w:slice:6")
        harness.tap("w:slice:7")

        self.assertEqual(
            harness.backend.sent,
            [("down", "ShiftLeft", (), True), ("down", "Q", (), True), ("up", "Q"), ("up", "ShiftLeft")],
        )

    def test_the_center_goes_back_to_the_top(self) -> None:
        harness = self._harness()

        harness.tap("w:slice:3")
        harness.tap("w:slice:8")
        self.assertEqual(harness.widget("w:center").text(), "×")  # type: ignore[attr-defined]
        harness.tap("w:center")

        self.assertEqual(harness.widget("w:center").text(), "")  # type: ignore[attr-defined]
        self.assertEqual(harness.widget("w:slice:6").text(), "Shift Ctrl Super Alt AltGr Super Ctrl Shift")  # type: ignore[attr-defined]
        self.assertEqual(harness.backend.sent, [])

    def test_a_wheel_menu_with_another_slice_count_is_rejected_when_built(self) -> None:
        short = wheel.menu({0: ["AD01", "AD02"]})

        with self.assertRaisesRegex(ValueError, r"wheel menu \[0\] has 2 slices; every menu needs 10"):
            wheel.wheel("w", short, layouts.LAYOUTS, lambda state: "us")

    def test_the_slices_fill_the_wheel_whatever_size_it_takes(self) -> None:
        harness = StdHarness(
            self, [wheel.wheel("w", wheel.TKL, layouts.LAYOUTS, lambda state: "us", {"min_width": 200, "min_height": 200})]
        )
        harness.window.show()
        canvas = harness.widget("w")
        for width, height in ((200, 200), (500, 260)):
            harness.window.resize(width + 100, height + 100)
            qt_app().processEvents()
            slices = [harness.widget(f"w:slice:{index}").geometry() for index in range(wheel.SLICES)]
            with self.subTest(size=(canvas.width(), canvas.height())):
                self.assertGreater(canvas.width(), canvas.height() if width > height else 0)
                self.assertLessEqual(min(rect.left() for rect in slices), 1)
                self.assertLessEqual(min(rect.top() for rect in slices), 1)
                self.assertGreaterEqual(max(rect.right() for rect in slices), canvas.width() - 2)
                self.assertGreaterEqual(max(rect.bottom() for rect in slices), canvas.height() - 2)


class ControlTests(unittest.TestCase):
    def test_checkbox_flips_its_variable_and_lights_while_true(self) -> None:
        harness = StdHarness(self, [controls.checkbox("on", "On", "on")], state={"on": axidev_osk.var("boolean", False)})

        harness.tap("on")
        self.assertIs(harness.state("on"), True)
        self.assertTrue(harness.widget("on").property("latched"))

        harness.tap("on")
        self.assertIs(harness.state("on"), False)
        self.assertFalse(harness.widget("on").property("latched"))

    def test_stepper_moves_by_exact_steps_and_stops_at_its_bounds(self) -> None:
        harness = StdHarness(
            self,
            [controls.stepper("level", "level", minimum=0.3, maximum=1.0, step=0.05, label="Level")],
            state={"level": axidev_osk.var("number", 0.85)},
        )
        up = harness.widget("level:up")

        for _tap in range(4):
            harness.tap("level:up")
        self.assertEqual(harness.state("level"), 1.0)
        self.assertEqual(harness.widget("level:value").text(), "1")  # type: ignore[attr-defined]
        self.assertFalse(up.isEnabled())

        harness.tap("level:down")
        self.assertEqual(harness.state("level"), 0.95)
        self.assertTrue(up.isEnabled())

    def test_linked_steppers_never_cross(self) -> None:
        harness = StdHarness(
            self,
            [
                controls.stepper("low", "low", minimum=0, maximum=lambda state: state.high - 5, step=5),
                controls.stepper("high", "high", minimum=lambda state: state.low + 5, maximum=100, step=5),
            ],
            state={"low": axidev_osk.var("integer", 0), "high": axidev_osk.var("integer", 15)},
        )

        for _tap in range(5):
            harness.tap("low:up")
        self.assertEqual(harness.state("low"), 10)
        self.assertFalse(harness.widget("high:down").isEnabled())

        harness.tap("high:up")
        harness.tap("low:up")
        self.assertEqual((harness.state("low"), harness.state("high")), (15, 20))

    def test_dropdown_opens_inline_and_picking_a_choice_runs_on_select_and_closes_it(self) -> None:
        mode, mode_panel = controls.dropdown(
            "mode",
            [("a", "Alpha"), ("b", "Beta")],
            value=lambda state: state.mode,
            on_select=lambda ctx, value: [axidev_osk.state.set("mode", value)],
            label="Mode",
            group="g",
        )
        other, other_panel = controls.menu("other", "Other", [axidev_osk.label(id="other:text", text="hi")], group="g")
        harness = StdHarness(self, [mode_panel, other_panel, mode, other], state={"mode": axidev_osk.var("string", "a")})
        panel = harness.widget("mode:panel")
        self.assertEqual(harness.widget("mode").text(), "Mode: Alpha ▾")  # type: ignore[attr-defined]
        self.assertTrue(panel.isHidden())

        harness.tap("mode")
        self.assertFalse(panel.isHidden())
        self.assertTrue(harness.widget("mode:choice:0").property("latched"))

        harness.tap("mode:choice:1")
        self.assertEqual(harness.state("mode"), "b")
        self.assertTrue(panel.isHidden())
        self.assertEqual(harness.widget("mode").text(), "Mode: Beta ▾")  # type: ignore[attr-defined]

        harness.tap("mode")
        harness.tap("other")
        self.assertTrue(panel.isHidden())
        self.assertFalse(harness.widget("other:panel").isHidden())

    def test_strip_shows_only_its_toggle_until_opened_and_closes_its_menus_with_it(self) -> None:
        group = controls.strip_group("s")
        more, more_panel = controls.menu("more", "More", [axidev_osk.label(id="more:text", text="hi")], group=group)
        harness = StdHarness(self, [controls.strip("s", [more], panels=[more_panel])])
        controls_row, panel = harness.widget("s:controls"), harness.widget("more:panel")
        self.assertTrue(controls_row.isHidden())

        harness.tap("s:toggle")
        self.assertFalse(controls_row.isHidden())
        harness.tap("more")
        self.assertFalse(panel.isHidden())
        self.assertFalse(controls_row.isHidden())

        harness.tap("s:toggle")
        self.assertTrue(controls_row.isHidden())
        harness.tap("s:toggle")
        self.assertTrue(panel.isHidden())

    def test_a_window_with_a_strip_gives_its_spare_height_to_its_content(self) -> None:
        qt_app()
        engine = make_test_engine(RecordingBackend())
        content = axidev_osk.grid(id="keys", children=[axidev_osk.button(id="key", label="A", cell={"row": 0, "column": 0})])
        window = controls.with_strip(axidev_osk.window(id="pad", title="Pad", content=content), controls.strip("s", []))
        root = axidev_osk.config(active_profile="p", profiles={"p": axidev_osk.profile(windows=[window], state=std.with_state(None))})
        built = build_window(self, start_test_profile(engine, root).window("pad"), engine)
        built.show()
        key, strip = find_node(built, "key"), find_node(built, "s")
        key_height, strip_height = key.height(), strip.height()

        built.resize(built.width(), built.height() + 200)
        qt_app().processEvents()

        self.assertEqual(key.height(), key_height + 200)
        self.assertEqual(strip.height(), strip_height)


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


class FailureNoticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = make_test_engine(RecordingBackend())
        self.actions = record_app_actions(self.engine.dispatcher)
        root = axidev_osk.config(
            active_profile="p",
            profiles={
                "p": axidev_osk.profile(
                    windows=[
                        axidev_osk.window(id="pad", title="Pad", content=axidev_osk.box(id="root")),
                        failures.notice_window(),
                    ],
                    state=std.with_state(),
                    on=std.with_handlers(failure_notice=True),
                )
            },
        )
        self.profile = start_test_profile(self.engine, root)

    def _action_failed(self, action: str, arguments: DataMap) -> RuntimeEvent:
        return RuntimeEvent(
            ACTION_FAILED,
            {"action": action, "arguments": arguments, "stage": "execute", "exception_type": "RuntimeError", "message": "gone", "hint": CHECK_HINT},
        )

    def test_the_notice_lists_each_distinct_failure_once_with_its_repeats_until_ok(self) -> None:
        qt_app()
        width = callback_failed(None, "binding", "node:root", ValueError("bad width"))
        self.engine.dispatcher.dispatch(width)
        self.engine.dispatcher.dispatch(
            window_state_changed(failures.NOTICE, visible=True, minimized=False, x=0, y=0, width=460, height=120),
            self._action_failed("window.hide", {"window": "pad"}),
            width,
        )

        self.assertEqual(self.actions, [("window.show", {"window": failures.NOTICE})])
        self.assertEqual(
            self.engine.profile.state.get(("std", "failure")),
            {
                "entries": [
                    "A binding of node:root failed: ValueError: bad width",
                    "The action window.hide failed while it was run: RuntimeError: gone",
                    "A binding of node:root failed: ValueError: bad width",
                ],
                "hint": CHECK_HINT,
            },
        )
        window = build_window(self, self.profile.window(failures.NOTICE), self.engine)
        message = find_node(window, f"{failures.NOTICE}:message")
        self.assertEqual(
            message.text(),  # type: ignore[attr-defined]
            "A binding of node:root failed: ValueError: bad width \u00d72\n"
            "The action window.hide failed while it was run: RuntimeError: gone",
        )

        QTest.mouseClick(find_node(window, f"{failures.NOTICE}:ok"), Qt.MouseButton.LeftButton)
        self.engine.dispatcher.process_pending()

        self.assertEqual(self.actions[-1], ("window.hide", {"window": failures.NOTICE}))
        self.assertEqual(self.engine.profile.state.get(("std", "failure", "entries")), [])

    def test_a_notice_that_cannot_show_does_not_report_itself(self) -> None:
        self.engine.dispatcher.dispatch(self._action_failed("window.show", {"window": failures.NOTICE}))
        self.engine.dispatcher.dispatch(callback_failed(None, "callback", "action.failed", KeyError("arguments")))

        self.assertEqual(self.actions, [])


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
