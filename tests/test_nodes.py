from __future__ import annotations

import unittest

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QStackedWidget, QWidget

from axidev_osk.components.button import Button
from axidev_osk.config.profile import ProfileConfig
from axidev_osk.config.reader import ConfigError
from axidev_osk.messages import DataMap
from axidev_osk.nodes import NodeKind
from axidev_osk.python_defaults import axidev_osk
from axidev_osk.runtime.engine_messages import keyboard_status_changed
from axidev_osk.runtime.functions import CallbackContext
from axidev_osk.runtime.profile_runtime import CALLBACK_FAILED, state_set
from support import RecordingBackend, build_window, find_node, make_test_engine, qt_app, start_test_profile


def _button(node_id: str, **fields: object) -> dict[str, object]:
    return {"kind": "button", "id": node_id, **fields}


class NodeTests(unittest.TestCase):
    def setUp(self) -> None:
        qt_app()
        self.engine = make_test_engine(RecordingBackend())
        self.pressed: list[DataMap] = []

    def _profile(self, content: dict[str, object], state: DataMap | None = None) -> ProfileConfig:
        window = {"id": "pad", "title": "Pad", "opacity": 0.9, "style": {"object_name": "padWindow"}, "content": content}
        return start_test_profile(
            self.engine,
            {"active_profile": "p", "profiles": {"p": {"state": state or {}, "windows": [window]}}},
        )

    def _window(self, profile: ProfileConfig) -> QWidget:
        window = build_window(self, profile.window("pad"), self.engine)
        window.show()
        return window

    def _find(self, window: QWidget, node_id: str) -> QWidget:
        return find_node(window, node_id)

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
            state={"shift": axidev_osk.var("boolean", False)},
        )
        window = self._window(profile)
        key = self._find(window, "a")
        assert isinstance(key, Button)

        self.assertEqual((key.text(), key.property("interactionState")), ("a", "idle"))
        self.engine.dispatcher.dispatch(state_set("shift", True))

        self.assertEqual((key.text(), key.property("latched"), key.property("interactionState")), ("A", True, "latched"))
        self.assertEqual(self._find(window, "plain").text(), "Plain")  # type: ignore[attr-defined]
        self.assertEqual(key.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertEqual(window.objectName(), "padWindow")

    def test_button_labels_show_ampersands_as_written(self) -> None:
        profile = self._profile(
            {"kind": "box", "id": "row", "children": [_button("and", label="&"), _button("save", label="S&ave")]}
        )
        window = self._window(profile)

        for node_id in ("and", "save"):
            with self.subTest(node_id):
                key = self._find(window, node_id)
                assert isinstance(key, Button)
                self.assertTrue(QKeySequence.mnemonic(key.text()).isEmpty())

    def test_a_spacer_keeps_its_minimum_size_and_lets_clicks_through(self) -> None:
        profile = self._profile(
            {"kind": "box", "id": "row", "direction": "horizontal", "children": [
                {"kind": "spacer", "id": "gap", "min_width": 30, "min_height": 10},
            ]}
        )
        gap = self._find(self._window(profile), "gap")

        self.assertEqual((gap.minimumWidth(), gap.minimumHeight()), (30, 10))
        self.assertTrue(gap.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))

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
            row, _unbinds = self.engine.node_builder.build_tree(profile.window("pad").content)
        finally:
            qt_app().removeEventFilter(watcher)
        self.addCleanup(row.deleteLater)

        self.assertEqual(shown_as_windows, [])
        row.show()
        self.assertTrue(self._find(row, "shown").isVisible())
        self.assertFalse(self._find(row, "hidden").isVisible())

    def test_a_binding_result_of_the_wrong_type_is_reported_not_converted(self) -> None:
        failures: list[DataMap] = []
        self.engine.dispatcher.add_raw_event_handler(CALLBACK_FAILED, lambda event: failures.append(event) or [])
        profile = self._profile(
            {"kind": "box", "id": "row", "children": [_button("a", latched=lambda s: s.mode == "on" or s.mode)]},
            state={"mode": axidev_osk.var("string", "on")},
        )
        key = self._find(self._window(profile), "a")

        self.engine.dispatcher.dispatch(state_set("mode", "no"))

        self.assertTrue(key.property("latched"))
        self.assertEqual([failure["source"] for failure in failures], ["node:a"])
        self.assertIn("latched must be a boolean", str(failures[0]["message"]))

    def test_a_kind_added_later_gets_its_events_and_collisions_are_rejected(self) -> None:
        nodes = self.engine.nodes
        nodes.register(NodeKind(name="dial", build=lambda node, builder: QWidget(), apply=lambda *args: None, decode_options=lambda reader: None, callbacks={"on_turn": "dial.turned"}))
        self.assertTrue(self.engine.dispatcher.has_event("dial.turned"))

        clash = NodeKind(name="clash", build=lambda node, builder: QWidget(), apply=lambda *args: None, decode_options=lambda reader: None, callbacks={"on_x": "app.activated"})
        with self.assertRaisesRegex(ValueError, "already registered elsewhere: app.activated"):
            nodes.register(clash)
        self.assertNotIn("clash", nodes)

    def test_press_and_release_run_node_callbacks_with_the_node_event(self) -> None:
        def on_press(ctx: CallbackContext, event: DataMap) -> list[object]:
            self.pressed.append(event)
            return [{"action": "state.set", "arguments": {"path": "count", "value": ctx.state.count + 1}}]

        profile = self._profile(
            {
                "kind": "box",
                "id": "root",
                "direction": "horizontal",
                "children": [
                    _button("cow", label=lambda s: f"Moo {s.count}", on_press=on_press),
                    _button("quiet"),
                ],
            },
            state={"count": axidev_osk.var("integer", 0)},
        )
        window = self._window(profile)
        cow = self._find(window, "cow")

        QTest.mouseClick(cow, Qt.MouseButton.LeftButton)
        QTest.mouseClick(cow, Qt.MouseButton.RightButton)
        QTest.mouseClick(self._find(window, "quiet"), Qt.MouseButton.LeftButton)
        self.engine.dispatcher.process_pending()

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
                    {"kind": "stack", "id": "pages", "current": lambda s: s.page, "children": [
                        {"kind": "label", "id": "one", "text": "One"},
                        {"kind": "label", "id": "two", "text": "Two"},
                    ]},
                ],
            },
            state={"page": axidev_osk.var("string", "one")},
        )
        self.engine.dispatcher.dispatch(keyboard_status_changed(True, "ready", False, ""))
        window = self._window(profile)
        status = self._find(window, "status")
        pages = self._find(window, "pages")
        assert isinstance(status, QLabel) and isinstance(pages, QStackedWidget)

        self.assertEqual((status.text(), status.objectName(), status.property("classes")), ("ready", "statusLabel", ["muted"]))
        self.assertEqual(pages.currentWidget().property("componentId"), "one")
        self.engine.dispatcher.dispatch(state_set("page", "two"))
        self.assertEqual(pages.currentWidget().property("componentId"), "two")

    def test_style_hooks_follow_state(self) -> None:
        profile = self._profile(
            {"kind": "label", "id": "status", "text": "Status",
             "style": lambda s: {"classes": ["warning"] if s.alert else [], "properties": {"level": s.level}}},
            state={"alert": axidev_osk.var("boolean", False), "level": axidev_osk.var("integer", 1)},
        )
        status = self._find(self._window(profile), "status")

        self.engine.dispatcher.dispatch(state_set("alert", True), state_set("level", 2))

        self.assertEqual((status.property("classes"), status.property("level")), (["warning"], 2))

    def test_a_style_property_changing_from_true_to_1_is_applied(self) -> None:
        profile = self._profile(
            {"kind": "label", "id": "status", "text": "Status",
             "style": lambda s: {"properties": {"flag": True if s.mode == "a" else 1}}},
            state={"mode": axidev_osk.var("string", "a")},
        )
        status = self._find(self._window(profile), "status")

        self.engine.dispatcher.dispatch(state_set("mode", "b"))

        self.assertIs(type(status.property("flag")), int)

    def test_a_stack_page_that_does_not_exist_is_reported(self) -> None:
        failures: list[DataMap] = []
        self.engine.dispatcher.add_raw_event_handler(CALLBACK_FAILED, lambda event: failures.append(event) or [])
        profile = self._profile(
            {"kind": "stack", "id": "pages", "current": lambda s: s.page, "children": [
                {"kind": "label", "id": "one", "text": "One"},
            ]},
            state={"page": axidev_osk.var("string", "one")},
        )
        pages = self._find(self._window(profile), "pages")
        assert isinstance(pages, QStackedWidget)

        self.engine.dispatcher.dispatch(state_set("page", "nope"))

        self.assertEqual(
            [failure["message"] for failure in failures],
            ["config.profiles.p.windows[0].content.current names 'nope', which is not a page of this stack"],
        )
        self.assertEqual(pages.currentWidget().property("componentId"), "one")

    def test_a_stack_whose_current_names_no_page_fails_at_load(self) -> None:
        with self.assertRaisesRegex(ConfigError, r"content\.current names 'nope', which is not a page of this stack"):
            self._profile(
                {"kind": "stack", "id": "pages", "current": "nope", "children": [{"kind": "label", "id": "one", "text": "One"}]}
            )

    def test_stack_pages_cannot_set_visible(self) -> None:
        for visible in (True, lambda s: s.show):
            with self.subTest(visible=visible), self.assertRaisesRegex(
                ConfigError, r"children\[1\]\.visible cannot be set on a stack page"
            ):
                self._profile(
                    {"kind": "stack", "id": "pages", "current": "one", "children": [
                        {"kind": "label", "id": "one", "text": "One"},
                        {"kind": "label", "id": "two", "text": "Two", "visible": visible},
                    ]}
                )

    def test_styles_cannot_set_the_properties_the_engine_sets(self) -> None:
        cases = {
            "componentId": {"kind": "label", "id": "a"},
            "latched": _button("a"),
        }
        for name, node in cases.items():
            content = {**node, "style": {"properties": {name: "x"}}}
            with self.subTest(name), self.assertRaisesRegex(ConfigError, f"cannot set engine properties: {name}"):
                self._profile(content)

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

    def test_canvas_children_take_the_shape_their_binding_gives_and_follow_it(self) -> None:
        def triangle(state: object) -> list[list[int]]:
            left = 100 if state.moved else 0  # type: ignore[attr-defined]
            return [[left, 0], [left + 100, 0], [left, 100]]

        profile = self._profile(
            {
                "kind": "canvas",
                "id": "board",
                "min_width": 300,
                "min_height": 200,
                "children": [
                    _button("corner", shape=triangle),
                    _button("square", shape=[[0, 150], [50, 150], [50, 200], [0, 200]]),
                ],
            },
            state={"moved": {"var": "boolean", "default": False}},
        )
        window = self._window(profile)
        board = self._find(window, "board")

        def hit(x: int, y: int) -> object:
            found = board.childAt(QPoint(x, y))
            return found.property("componentId") if found else None

        self.assertEqual(hit(20, 20), "corner")
        # Inside the triangle's bounding box but past its long side.
        self.assertIsNone(hit(80, 80))
        self.assertEqual(hit(25, 175), "square")

        self.engine.dispatcher.dispatch(state_set("moved", True))
        self.assertIsNone(hit(20, 20))
        self.assertEqual(hit(120, 20), "corner")

    def test_a_kind_with_live_child_placement_must_also_place_its_children(self) -> None:
        with self.assertRaisesRegex(ValueError, "must set both decode_live_placement and place_child"):
            NodeKind(
                name="half",
                build=lambda node, builder: QWidget(),
                apply=lambda *args: None,
                decode_options=lambda reader: None,
                has_children=True,
                decode_live_placement=lambda reader: None,
            )

    def test_a_canvas_child_with_an_anchor_centers_its_box_on_it(self) -> None:
        profile = self._profile(
            {
                "kind": "canvas",
                "id": "board",
                "min_width": 300,
                "min_height": 200,
                "children": [_button("wedge", shape=[[100, 0], [200, 0], [100, 100]], anchor=[120, 30])],
            }
        )
        window = self._window(profile)

        box = self._find(window, "wedge").geometry()
        self.assertEqual((box.x() + box.width() / 2, box.y() + box.height() / 2), (120, 30))
        self.assertTrue(box.contains(100, 0) and box.contains(199, 0) and box.contains(100, 99))

    def test_shape_is_required_under_a_canvas_and_unknown_anywhere_else(self) -> None:
        square = [[0, 0], [10, 0], [10, 10], [0, 10]]
        cases = {
            r"children\[0\] has unknown keys: shape": {
                "kind": "box",
                "id": "row",
                "children": [_button("a", shape=square)],
            },
            r"children\[0\] has unknown keys: anchor": {
                "kind": "box",
                "id": "row",
                "children": [_button("a", anchor=[0, 0])],
            },
            r"children\[0\]\.shape is required": {"kind": "canvas", "id": "board", "children": [_button("a")]},
            r"children\[0\]\.shape must be a list of at least three \[x, y\] corners": {
                "kind": "canvas",
                "id": "board",
                "children": [_button("a", shape=[[0, 0], [10, 0]])],
            },
        }
        for message, content in cases.items():
            with self.subTest(message), self.assertRaisesRegex(ConfigError, message):
                self._profile(content)

    def test_a_node_that_reports_its_size_writes_it_to_state(self) -> None:
        profile = self._profile({"kind": "canvas", "id": "board", "report_size": True, "children": []})
        window = self._window(profile)
        window.resize(320, 240)
        qt_app().processEvents()

        board = self._find(window, "board")
        self.assertEqual(
            self.engine.profile.state.get(("nodes", "board", "size")),
            {"width": board.width(), "height": board.height()},
        )


if __name__ == "__main__":
    unittest.main()
