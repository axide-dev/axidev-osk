from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QWidget

from axidev_osk.config.profile import ConfigDecoder
from axidev_osk.messages import DataMap, MessageResult, RuntimeEvent
from axidev_osk.nodes import BUTTON_PRESSED, BUTTON_RELEASED
from axidev_osk.python_defaults import osk
from axidev_osk.python_defaults.osk.std import keys, prompts, windows
from axidev_osk.runtime.engine_messages import input_key, keyboard_reset
from axidev_osk.runtime.state import StateTree
from axidev_osk.runtime.testing import make_test_context
from axidev_osk.windows.builder import build_profile_window


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


def _app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    return app


class StdHarness:
    def __init__(self, children: list[osk.Map], *, on: dict[str, Any] | None = None) -> None:
        _app()
        self.backend = RecordingBackend()
        self.context = make_test_context(self.backend, activate_behaviors=False)
        self.engine = self.context.engine
        self.window_actions: list[tuple[str, DataMap]] = []
        for name in ("window.set_opacity", "window.block_input", "window.unblock_input", "window.show", "window.hide"):
            self.context.dispatcher.register_action(
                name,
                lambda arguments: arguments,
                lambda arguments, name=name: self._record(name, arguments),
                override=True,
            )
        root = osk.config(
            active_profile="p",
            profiles={
                "p": osk.profile(
                    windows=[osk.window(id="pad", title="Pad", content=osk.box(id="root", children=children))],
                    on=on or {"keyboard.reset": keys.on_reset},
                )
            },
        )
        decoder = ConfigDecoder(node_kinds=self.engine.nodes, attachment_kinds={}, functions=self.engine.functions)
        self.profile = decoder.decode_root(root).profile
        self.engine.profile.start(self.profile)
        with patch("axidev_osk.windows.builder.configure_always_on_top_window", return_value=FakeOverlay()):
            self.window = build_profile_window(self.profile.window("pad"), self.context)

    def _record(self, name: str, arguments: DataMap) -> MessageResult:
        self.window_actions.append((name, arguments))
        return []

    def tap(self, node_id: str) -> None:
        self.context.dispatcher.dispatch_event(RuntimeEvent(BUTTON_PRESSED, {"node": node_id}))
        self.context.dispatcher.dispatch_event(RuntimeEvent(BUTTON_RELEASED, {"node": node_id}))

    def observe(self, key: str, pressed: bool, modifiers: tuple[str, ...] = ()) -> None:
        self.context.dispatcher.dispatch_event(input_key(key, None, modifiers, pressed))

    def widget(self, node_id: str) -> QWidget:
        for child in self.window.findChildren(QWidget):
            if child.property("componentId") == node_id:
                return child
        raise AssertionError(node_id)

    def state(self, *path: str) -> object:
        return self.engine.state.get(path)


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
            [("down", "A", ("Shift",), True), ("up", "A"), ("down", "A", (), True), ("up", "A")],
        )

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

        harness.context.dispatcher.dispatch_event(keyboard_reset())

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
        harness = StdHarness([windows.ghost_button("pad", 0.85)])

        harness.tap("ghost:pad")
        self.assertTrue(harness.widget("ghost:pad").property("latched"))
        harness.tap("ghost:pad")

        self.assertEqual(
            harness.window_actions,
            [
                ("window.set_opacity", {"window": "pad", "opacity": 0.01}),
                ("window.block_input", {"window": "pad", "except": ["ghost:pad"]}),
                ("window.set_opacity", {"window": "pad", "opacity": 0.85}),
                ("window.unblock_input", {"window": "pad"}),
            ],
        )

    def test_corner_toggle_brings_back_ghosted_and_minimized_windows(self) -> None:
        def run(state: DataMap) -> list[str]:
            ctx = SimpleNamespace(state=StateTree(state).view())
            return [item["action"] for item in windows.corner_toggle(ctx, "pad", 0.85)]

        self.assertEqual(run({"std": {"ghosted": {"pad": True}}})[-1], "window.show")
        self.assertEqual(run({"windows": {"pad": {"minimized": True, "visible": True}}}), ["window.show"])
        self.assertEqual(run({"windows": {"pad": {"visible": True}}}), ["window.hide"])
        self.assertEqual(run({}), ["window.show"])


class PromptTests(unittest.TestCase):
    def test_prompt_window_builds_with_button_callbacks(self) -> None:
        _app()
        context = make_test_context(RecordingBackend(), activate_behaviors=False)
        engine = context.engine
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
                prompts.prompt_button("quit:no", "No", answer, accept=False),
            ],
        )
        decoder = ConfigDecoder(node_kinds=engine.nodes, attachment_kinds={}, functions=engine.functions)
        profile = decoder.decode_root(osk.config(active_profile="p", profiles={"p": osk.profile(windows=[prompt])})).profile
        engine.profile.start(profile)
        with patch("axidev_osk.windows.builder.configure_always_on_top_window", return_value=FakeOverlay()):
            window = build_profile_window(profile.window("quit"), context)
        self.addCleanup(window.close)
        context.dispatcher.dispatch_event(RuntimeEvent(BUTTON_RELEASED, {"node": "quit:no"}))

        labels = {child.property("componentId"): child for child in window.findChildren(QWidget)}
        self.assertEqual(labels["quit:message"].text(), "Close it?")  # type: ignore[attr-defined]
        self.assertEqual(labels["quit:yes"].objectName(), "confirmAcceptButton")
        self.assertEqual(answers, ["quit:no"])
        self.assertFalse(profile.window("quit").show_on_start)


if __name__ == "__main__":
    unittest.main()
