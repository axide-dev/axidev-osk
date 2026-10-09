from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QStackedWidget, QWidget

from axidev_osk.components.button import Button
from axidev_osk.config.profile import ConfigDecoder, ProfileConfig
from axidev_osk.config.reader import ConfigError
from axidev_osk.messages import DataMap
from axidev_osk.runtime.functions import CallbackContext
from axidev_osk.runtime.profile_runtime import state_set
from axidev_osk.runtime.testing import make_test_context
from axidev_osk.windows.builder import build_profile_window


class FakeKeyboardBackend:
    ready = True
    status_text = "ready"
    needs_permission_setup = False
    permission_setup_text = ""

    def add_observation_listener(self, listener):
        del listener
        return lambda: None

    def add_key_state_listener(self, listener):
        del listener
        return lambda: None

    def add_modifier_state_listener(self, listener):
        del listener
        return lambda: None


class FakeOverlay:
    uses_custom_chrome = False

    def handle_show(self) -> bool:
        return True

    def move_by(self, dx: int, dy: int) -> None:
        del dx, dy

    def resize_by(self, dx: int, dy: int) -> None:
        del dx, dy


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication)
    return app


def _button(node_id: str, **fields: object) -> dict[str, object]:
    return {"kind": "button", "id": node_id, **fields}


class NodeTests(unittest.TestCase):
    def setUp(self) -> None:
        _app()
        self.context = make_test_context(FakeKeyboardBackend())
        self.engine = self.context.engine
        self.pressed: list[DataMap] = []

    def _profile(self, content: dict[str, object], state: DataMap | None = None) -> ProfileConfig:
        decoder = ConfigDecoder(node_kinds=self.engine.nodes, attachment_kinds={}, functions=self.engine.functions)
        profile = decoder.decode_root(
            {
                "active_profile": "p",
                "profiles": {
                    "p": {
                        "state": state or {},
                        "windows": [
                            {
                                "id": "pad",
                                "title": "Pad",
                                "opacity": 0.9,
                                "style": {"object_name": "padWindow"},
                                "content": content,
                            }
                        ],
                    }
                },
            }
        ).profile
        self.engine.profile.start(profile)
        return profile

    def _window(self, profile: ProfileConfig) -> QWidget:
        with patch("axidev_osk.windows.builder.configure_always_on_top_window", return_value=FakeOverlay()):
            window = build_profile_window(profile.window("pad"), self.context)
        self.addCleanup(window.close)
        window.show()
        return window

    def _find(self, window: QWidget, node_id: str) -> QWidget:
        for child in window.findChildren(QWidget):
            if child.property("componentId") == node_id:
                return child
        raise AssertionError(f"node {node_id!r} not found")

    def test_buttons_bind_labels_and_states_to_profile_state(self) -> None:
        def legend(state: object) -> str:
            return "A" if state.shift else "a"  # type: ignore[attr-defined]

        profile = self._profile(
            {
                "kind": "grid",
                "id": "keys",
                "spacing": 4,
                "children": [
                    _button("a", label=legend, latched=lambda s: s.shift, cell={"row": 0, "column": 0}),
                    _button("plain", label="Plain", cell={"row": 0, "column": 1, "column_span": 2}),
                ],
            },
            state={"shift": False},
        )
        window = self._window(profile)
        key = self._find(window, "a")
        assert isinstance(key, Button)

        self.assertEqual((key.text(), key.property("interactionState")), ("a", "idle"))
        self.context.dispatcher.dispatch_action(state_set("shift", True))

        self.assertEqual((key.text(), key.property("latched"), key.property("interactionState")), ("A", True, "latched"))
        self.assertEqual(self._find(window, "plain").text(), "Plain")  # type: ignore[attr-defined]
        self.assertEqual(key.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertEqual(window.objectName(), "padWindow")

    def test_press_and_release_run_node_callbacks_with_the_node_event(self) -> None:
        def on_press(ctx: CallbackContext, event: DataMap) -> list[object]:
            self.pressed.append(event)
            return [{"action": "state.set", "arguments": {"path": "count", "value": (ctx.state.count or 0) + 1}}]

        profile = self._profile(
            {
                "kind": "box",
                "id": "root",
                "direction": "horizontal",
                "children": [
                    _button("cow", label=lambda s: f"Moo {s.count or 0}", on_press=on_press),
                    _button("quiet"),
                ],
            }
        )
        window = self._window(profile)
        cow = self._find(window, "cow")

        QTest.mouseClick(cow, Qt.MouseButton.LeftButton)
        QTest.mouseClick(cow, Qt.MouseButton.RightButton)
        QTest.mouseClick(self._find(window, "quiet"), Qt.MouseButton.LeftButton)

        self.assertEqual(self.pressed, [{"node": "cow"}, {"node": "cow"}])
        self.assertEqual(cow.text(), "Moo 2")  # type: ignore[attr-defined]

    def test_labels_stacks_and_style_hooks(self) -> None:
        profile = self._profile(
            {
                "kind": "box",
                "id": "root",
                "children": [
                    {"kind": "label", "id": "status", "text": lambda s: s.keyboard.status, "word_wrap": True,
                     "style": {"object_name": "statusLabel", "classes": ["muted"]}},
                    {"kind": "stack", "id": "pages", "current": lambda s: s.page or "one", "children": [
                        {"kind": "label", "id": "one", "text": "One"},
                        {"kind": "label", "id": "two", "text": "Two"},
                    ]},
                ],
            }
        )
        self.engine.profile.set_observed(("keyboard", "status"), "ready")
        window = self._window(profile)
        status = self._find(window, "status")
        pages = self._find(window, "pages")
        assert isinstance(status, QLabel) and isinstance(pages, QStackedWidget)

        self.assertEqual((status.text(), status.objectName(), status.property("classes")), ("ready", "statusLabel", ["muted"]))
        self.assertEqual(pages.currentWidget().property("componentId"), "one")
        self.context.dispatcher.dispatch_action(state_set("page", "two"))
        self.assertEqual(pages.currentWidget().property("componentId"), "two")

    def test_grid_children_need_cells(self) -> None:
        profile = self._profile({"kind": "grid", "id": "keys", "children": [_button("a")]})

        with self.assertRaisesRegex(ConfigError, "needs a cell"):
            self._window(profile)


if __name__ == "__main__":
    unittest.main()
