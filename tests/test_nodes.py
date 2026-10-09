from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QStackedWidget, QWidget

from axidev_osk.components.button import Button
from axidev_osk.config.profile import ProfileConfig
from axidev_osk.config.reader import ConfigError
from axidev_osk.messages import DataMap
from axidev_osk.nodes import NodeKind
from axidev_osk.runtime.functions import CallbackContext
from axidev_osk.runtime.profile_runtime import CALLBACK_FAILED, state_set
from axidev_osk.runtime.testing import make_test_context, start_test_profile
from axidev_osk.windows.builder import build_profile_window
from support import FakeOverlay, RecordingBackend, qt_app


def _button(node_id: str, **fields: object) -> dict[str, object]:
    return {"kind": "button", "id": node_id, **fields}


class NodeTests(unittest.TestCase):
    def setUp(self) -> None:
        qt_app()
        self.context = make_test_context(RecordingBackend())
        self.engine = self.context.engine
        self.pressed: list[DataMap] = []

    def _profile(self, content: dict[str, object], state: DataMap | None = None) -> ProfileConfig:
        window = {"id": "pad", "title": "Pad", "opacity": 0.9, "style": {"object_name": "padWindow"}, "content": content}
        return start_test_profile(
            self.context,
            {"active_profile": "p", "profiles": {"p": {"state": state or {}, "windows": [window]}}},
        )

    def _window(self, profile: ProfileConfig) -> QWidget:
        with patch("axidev_osk.windows.builder.configure_always_on_top_window", return_value=FakeOverlay()):
            window = build_profile_window(profile.window("pad"), self.context)
        self.addCleanup(window.deleteLater)
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
        self.context.dispatcher.dispatch(state_set("shift", True))

        self.assertEqual((key.text(), key.property("latched"), key.property("interactionState")), ("A", True, "latched"))
        self.assertEqual(self._find(window, "plain").text(), "Plain")  # type: ignore[attr-defined]
        self.assertEqual(key.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertEqual(window.objectName(), "padWindow")

    def test_built_nodes_never_become_windows_of_their_own(self) -> None:
        profile = self._profile(
            {"kind": "box", "id": "row", "children": [_button("shown"), _button("hidden", visible=False)]}
        )
        shown_as_windows: list[str] = []

        class ShowWatcher(QObject):
            def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
                if event.type() == QEvent.Type.Show and isinstance(watched, QWidget) and watched.isWindow():
                    shown_as_windows.append(str(watched.property("componentId")))
                return False

        watcher = ShowWatcher()
        qt_app().installEventFilter(watcher)
        try:
            row = self.engine.node_builder.build(profile.window("pad").content)
        finally:
            qt_app().removeEventFilter(watcher)
        self.addCleanup(row.deleteLater)

        self.assertEqual(shown_as_windows, [])
        row.show()
        self.assertTrue(self._find(row, "shown").isVisible())
        self.assertFalse(self._find(row, "hidden").isVisible())

    def test_a_binding_result_of_the_wrong_type_is_reported_not_converted(self) -> None:
        failures: list[DataMap] = []
        self.context.dispatcher.add_raw_event_handler(CALLBACK_FAILED, lambda event: failures.append(event) or [])
        profile = self._profile(
            {"kind": "box", "id": "row", "children": [_button("a", latched=lambda s: s.mode)]},
            state={"mode": True},
        )
        key = self._find(self._window(profile), "a")

        self.context.dispatcher.dispatch(state_set("mode", "no"))

        self.assertTrue(key.property("latched"))
        self.assertEqual([failure["source"] for failure in failures], ["a.latched"])

    def test_a_kind_added_later_gets_its_events_and_collisions_are_rejected(self) -> None:
        nodes = self.engine.nodes
        nodes.register(NodeKind(name="dial", build=lambda node, builder: QWidget(), apply=lambda *args: None, callbacks={"on_turn": "dial.turned"}))
        self.assertTrue(self.context.dispatcher.has_event("dial.turned"))

        clash = NodeKind(name="clash", build=lambda node, builder: QWidget(), apply=lambda *args: None, callbacks={"on_x": "app.activated"})
        with self.assertRaisesRegex(ValueError, "already registered elsewhere: app.activated"):
            nodes.register(clash)
        self.assertNotIn("clash", nodes)

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
        self.context.dispatcher.dispatch(state_set("page", "two"))
        self.assertEqual(pages.currentWidget().property("componentId"), "two")

    def test_placement_fields_are_checked_where_the_parent_reads_them(self) -> None:
        cell = {"row": 0, "column": 0}
        cases = {
            r"children\[0\]\.cell is required": {"kind": "grid", "id": "keys", "children": [_button("a")]},
            r"children\[0\] has unknown keys: cell": {"kind": "box", "id": "row", "children": [_button("a", cell=cell)]},
            r"children\[0\] has unknown keys: stretch": {
                "kind": "grid",
                "id": "keys",
                "children": [_button("a", cell=cell, stretch=1)],
            },
            r"content has unknown keys: direction": {"kind": "grid", "id": "keys", "direction": "vertical"},
        }
        for message, content in cases.items():
            with self.subTest(message), self.assertRaisesRegex(ConfigError, message):
                self._profile(content)


if __name__ == "__main__":
    unittest.main()
