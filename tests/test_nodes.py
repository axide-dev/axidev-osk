from __future__ import annotations

import unittest

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QKeySequence, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QStackedWidget, QWidget

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
                    _button(
                        "a",
                        label=legend,
                        style={"properties": lambda s: {"latched": s.shift}},
                        cell={"row": 0, "column": 0},
                    ),
                    _button("plain", label="Plain", cell={"row": 0, "column": 1, "column_span": 2}),
                ],
            },
            state={"shift": axidev_osk.var("boolean", False)},
        )
        window = self._window(profile)
        key = self._find(window, "a")
        assert isinstance(key, Button)

        self.assertEqual((key.text(), key.property("latched")), ("a", False))
        self.engine.dispatcher.dispatch(state_set("shift", True))

        self.assertEqual((key.text(), key.property("latched")), ("A", True))
        self.assertEqual(self._find(window, "plain").text(), "Plain")  # type: ignore[attr-defined]
        self.assertEqual(key.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertEqual(window.objectName(), "padWindow")

    def test_buttons_report_the_pointer_entering_and_leaving(self) -> None:
        seen: list[tuple[str, str]] = []

        def record(name: str) -> object:
            return lambda ctx, event: seen.append((name, event["node"])) or []

        profile = self._profile(
            {
                "kind": "box",
                "id": "row",
                "children": [_button("a", on_enter=record("enter"), on_leave=record("leave"))],
            }
        )
        key = self._find(self._window(profile), "a")
        # Showing the window may report the pointer already over it, so start from the pointer outside.
        QApplication.sendEvent(key, QEvent(QEvent.Type.Leave))
        self.engine.dispatcher.process_pending()
        seen.clear()

        QApplication.sendEvent(key, QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)))
        QApplication.sendEvent(key, QEnterEvent(QPointF(2, 2), QPointF(2, 2), QPointF(2, 2)))
        QApplication.sendEvent(key, QEvent(QEvent.Type.Leave))
        self.engine.dispatcher.process_pending()

        self.assertEqual(seen, [("enter", "a"), ("leave", "a")])

    def test_a_node_reporting_the_pointer_follows_a_swipe_across_its_children_with_its_button(self) -> None:
        reports: list[tuple[str, str, float, float]] = []
        buttons: list[object] = []
        pressed: list[str] = []

        def record(ctx: object, event: DataMap) -> list[object]:
            del ctx
            reports.append((str(event["name"]), str(event["node"]), float(event["x"]), float(event["y"])))  # type: ignore[arg-type]
            buttons.append(event.get("button"))
            return []

        def on(name: str) -> object:
            return lambda ctx, event: record(ctx, {**event, "name": name})

        window = {
            "id": "pad",
            "title": "Pad",
            "content": {
                "kind": "grid",
                "id": "keys",
                "reports_pointer": True,
                "children": [
                    _button("a", cell={"row": 0, "column": 0}, on_press=lambda ctx, event: pressed.append(event["node"]) or []),
                    _button("b", cell={"row": 0, "column": 1}),
                ],
            },
        }
        handlers = {name: on(name) for name in ("node.pointer_pressed", "node.pointer_moved", "node.pointer_released")}
        profile = start_test_profile(
            self.engine,
            {"active_profile": "p", "profiles": {"p": {"windows": [window], "on": handlers}}},
        )
        shown = self._window(profile)
        shown.resize(200, 60)
        QTest.qWait(10)
        grid, a, b = (self._find(shown, node_id) for node_id in ("keys", "a", "b"))
        start = a.rect().center()
        end = b.mapTo(a, b.rect().center())

        QTest.mousePress(a, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, start)
        QTest.mouseMove(a, end)
        QTest.mouseRelease(a, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, end)
        QTest.qWait(10)

        in_grid = (a.mapTo(grid, start), a.mapTo(grid, end))
        self.assertEqual(pressed, ["a"])
        self.assertEqual(
            [(name, node) for name, node, _x, _y in reports],
            [("node.pointer_pressed", "keys"), ("node.pointer_moved", "keys"), ("node.pointer_released", "keys")],
        )
        self.assertEqual((reports[0][2], reports[0][3]), (in_grid[0].x(), in_grid[0].y()))
        self.assertEqual((reports[2][2], reports[2][3]), (in_grid[1].x(), in_grid[1].y()))
        self.assertEqual(buttons, ["right", None, "right"])

    def test_nodes_that_opt_in_report_hovering_leaving_and_wheel_turns(self) -> None:
        reports: list[DataMap] = []

        def record(name: str) -> object:
            return lambda ctx, event: reports.append({"name": name, **event}) or []

        window = {
            "id": "pad",
            "title": "Pad",
            "content": {
                "kind": "box",
                "id": "row",
                "reports_hover": True,
                "reports_wheel": True,
                "children": [_button("a"), _button("quiet")],
            },
        }
        names = ("node.pointer_hovered", "node.pointer_left", "node.wheel")
        profile = start_test_profile(
            self.engine,
            {"active_profile": "p", "profiles": {"p": {"windows": [window], "on": {n: record(n) for n in names}}}},
        )
        shown = self._window(profile)
        shown.resize(200, 60)
        QTest.qWait(10)
        row, a = self._find(shown, "row"), self._find(shown, "a")
        point = a.rect().center()

        QTest.mouseMove(a, point)
        turns = ((0, 240, 1), (-120, 0, 2))
        for dx, dy, timestamp in turns:
            local = QPointF(point)
            turn = QWheelEvent(
                local, QPointF(a.mapToGlobal(point)), QPoint(), QPoint(dx, dy),
                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False,
            )
            turn.setTimestamp(timestamp)
            QApplication.sendEvent(a, turn)
        QApplication.sendEvent(row, QEvent(QEvent.Type.Leave))
        QTest.qWait(10)

        in_row = a.mapTo(row, point)
        on_screen = a.mapToGlobal(point)
        self.assertEqual(
            [report for report in reports if report["name"] == "node.pointer_hovered"][-1],
            {
                "name": "node.pointer_hovered", "node": "row", "x": in_row.x(), "y": in_row.y(),
                "screen_x": on_screen.x(), "screen_y": on_screen.y(),
            },
        )
        self.assertEqual(
            [report for report in reports if report["name"] != "node.pointer_hovered"],
            [
                {"name": "node.wheel", "node": "row", "dx": 0, "dy": 2},
                {"name": "node.wheel", "node": "row", "dx": -1, "dy": 0},
                {"name": "node.pointer_left", "node": "row"},
            ],
        )

    def test_a_node_reporting_its_geometry_records_its_place_in_state(self) -> None:
        profile = self._profile(
            {
                "kind": "box",
                "id": "row",
                "direction": "horizontal",
                "children": [_button("a"), _button("b", report_geometry=True)],
            }
        )
        shown = self._window(profile)
        shown.resize(240, 60)
        QTest.qWait(10)
        self.engine.dispatcher.process_pending()
        b = self._find(shown, "b")
        content = shown.centralWidget()  # type: ignore[attr-defined]
        corner = b.mapTo(content, QPoint(0, 0))

        state = self.engine.profile.state
        self.assertEqual(state.get(("nodes", "b", "position")), {"x": corner.x(), "y": corner.y()})
        self.assertEqual(state.get(("nodes", "b", "size")), {"width": b.width(), "height": b.height()})
        self.assertIsNone(state.get(("nodes", "a", "position")))

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
        self.engine.dispatcher.add_raw_event_handler(CALLBACK_FAILED, lambda event: failures.append(event) or [])
        profile = self._profile(
            {"kind": "box", "id": "row", "children": [_button("a", enabled=lambda s: s.mode == "on" or s.mode)]},
            state={"mode": axidev_osk.var("string", "on")},
        )
        key = self._find(self._window(profile), "a")

        self.engine.dispatcher.dispatch(state_set("mode", "no"))

        self.assertTrue(key.isEnabled())
        self.assertEqual([failure["source"] for failure in failures], ["node:a"])
        self.assertIn("enabled must be a boolean", str(failures[0]["message"]))

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
        QTest.mouseClick(cow, Qt.MouseButton.BackButton)
        QTest.mouseClick(cow, Qt.MouseButton.ForwardButton)
        QTest.mouseClick(self._find(window, "quiet"), Qt.MouseButton.LeftButton)
        self.engine.dispatcher.process_pending()

        self.assertEqual(
            self.pressed,
            [{"node": "cow", "button": name} for name in ("left", "right", "back", "forward")],
        )
        self.assertEqual(cow.text(), "Moo 4")  # type: ignore[attr-defined]

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
            "classes": _button("a"),
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


if __name__ == "__main__":
    unittest.main()
