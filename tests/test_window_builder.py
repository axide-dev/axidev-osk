from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPushButton

from axidev_osk.attachments.runtime import AttachmentRuntime
from axidev_osk.components.pointer_locator import PointerLocator
from axidev_osk.config.models import ChromeConfig, OverlayConfig
from axidev_osk.config.profile import Live, ProfileConfig, StyleConfig, WindowValues
from axidev_osk.python_defaults import axidev_osk
from axidev_osk.messages import DataMap
from axidev_osk.nodes import BUTTON_PRESSED
from axidev_osk.runtime.app_messages import (
    DWELL_COMPLETED,
    WINDOW_CLOSE_REQUESTED,
    WINDOW_DRAG_ENDED,
    WINDOW_DRAG_STARTED,
    WINDOW_DRAGGED,
    WINDOW_RESIZE_DRAG_ENDED,
    WINDOW_RESIZE_DRAG_STARTED,
    WINDOW_RESIZE_DRAGGED,
    WindowArguments,
    WindowButtonArguments,
    WindowCloseRequestedArguments,
)
from axidev_osk.runtime.engine import Engine
from axidev_osk.runtime.profile_runtime import state_set
from axidev_osk.windows.builder import RuntimeWindow, build_profile_window
from axidev_osk.windows.chrome import OverlayResizeHandle, OverlayTitleBar
from axidev_osk.config.models import ANCHORS, Anchor
from support import FakeOverlay, RecordingBackend, make_test_engine, qt_app, start_test_profile, wait_until

_CONFIGURE_OVERLAY = "axidev_osk.windows.builder.configure_always_on_top_window"


def _root(
    attachments: list[axidev_osk.Map] | None = None,
    windows: tuple[str, ...] = ("pad",),
    state: axidev_osk.Map | None = None,
    **window_fields: Any,
) -> axidev_osk.Map:
    return axidev_osk.config(
        active_profile="p",
        profiles={
            "p": axidev_osk.profile(
                windows=[
                    axidev_osk.window(
                        **axidev_osk.merge(
                            {
                                "id": window,
                                "title": window.title(),
                                "content": axidev_osk.box(
                                    id=f"{window}:root",
                                    children=[axidev_osk.button(id=f"{window}:a", label="a")],
                                ),
                            },
                            window_fields,
                        )
                    )
                    for window in windows
                ],
                attachments=attachments or [],
                state=state,
            )
        },
    )


class WindowHarness:
    """A started profile with its attachment runtime, ready to build windows."""

    def __init__(
        self,
        attachments: list[axidev_osk.Map] | None = None,
        windows: tuple[str, ...] = ("pad",),
        state: axidev_osk.Map | None = None,
        **window_fields: Any,
    ) -> None:
        qt_app()
        self.engine: Engine = make_test_engine(RecordingBackend())
        self.built: dict[str, RuntimeWindow] = {}
        self.attachments = AttachmentRuntime(self.engine.bindings, self.engine.attachments, window_lookup=self.built.get)
        self.profile: ProfileConfig = start_test_profile(self.engine, _root(attachments, windows, state, **window_fields))
        self.attachments.start(self.profile)

    def build(self, window_id: str = "pad", overlay: object | None = None) -> RuntimeWindow:
        with patch(_CONFIGURE_OVERLAY, return_value=overlay or FakeOverlay(uses_custom_chrome=True)):
            window = build_profile_window(
                self.profile.window(window_id),
                self.engine,
                attachments=self.attachments.for_window(window_id),
            )
        self.built[window_id] = window
        return window


class RuntimeWindowCloseTests(unittest.TestCase):
    def _record_close_requests(self, harness: WindowHarness) -> list[WindowArguments]:
        events: list[WindowArguments] = []
        harness.engine.dispatcher.add_event_handler(
            WINDOW_CLOSE_REQUESTED,
            lambda close_event: events.append(close_event) or [],
        )
        return events

    def test_close_sends_a_request_instead_of_closing(self) -> None:
        harness = WindowHarness()
        window = harness.build()
        self.addCleanup(window.deleteLater)
        events = self._record_close_requests(harness)

        event = QCloseEvent()
        window.closeEvent(event)

        self.assertFalse(event.isAccepted())
        # The request is posted, so it runs after the Qt event returns.
        self.assertEqual(events, [])
        qt_app().processEvents()
        self.assertEqual(events, [WindowCloseRequestedArguments("pad", None)])

    def test_removed_output_close_does_not_request_application_quit(self) -> None:
        harness = WindowHarness()
        overlay = FakeOverlay(uses_custom_chrome=True)
        overlay.has_removed_output = Mock(return_value=True)  # type: ignore[attr-defined]
        window = harness.build(overlay=overlay)
        self.addCleanup(window.deleteLater)
        events = self._record_close_requests(harness)

        event = QCloseEvent()
        window.closeEvent(event)
        qt_app().processEvents()
        self.assertFalse(event.isAccepted())
        self.assertEqual(events, [])

        overlay.has_removed_output.return_value = False  # type: ignore[attr-defined]
        window.closeEvent(QCloseEvent())
        qt_app().processEvents()
        self.assertEqual(events, [WindowCloseRequestedArguments("pad", None)])


class RuntimeWindowLayoutTests(unittest.TestCase):
    """Tests covering profile windows built via ``build_profile_window``."""

    def test_failed_content_build_releases_platform_resources(self) -> None:
        qt_app()
        engine = make_test_engine(RecordingBackend())
        overlay = Mock()
        values = WindowValues(
            title="Pad",
            opacity=1.0,
            minimum_size=(0, 0),
            default_close=True,
            input_blocked=False,
            style=StyleConfig(),
            close_label="x",
            fit_content=True,
        )

        with (
            patch(_CONFIGURE_OVERLAY, return_value=overlay),
            self.assertRaisesRegex(RuntimeError, "content failed"),
        ):
            RuntimeWindow(
                window_id="pad",
                overlay=OverlayConfig(),
                chrome=ChromeConfig(),
                values=Live(values, lambda _resolver: values),
                build_content=Mock(side_effect=RuntimeError("content failed")),
                engine=engine,
            )

        overlay.release_resources.assert_called_once_with()

    def test_custom_chrome_puts_resize_handle_in_title_bar(self) -> None:
        window = WindowHarness().build()
        self.addCleanup(window.deleteLater)

        central_layout = window.centralWidget().layout()
        self.assertEqual(central_layout.count(), 2)

        title_bar = central_layout.itemAt(0).widget()
        self.assertIsInstance(title_bar, OverlayTitleBar)

        resize_handle = title_bar.findChild(OverlayResizeHandle, "layerShellResizeHandle")
        self.assertIsNotNone(resize_handle)

        close_button = title_bar.findChild(QPushButton, "layerShellCloseButton")
        self.assertIsNotNone(close_button)
        title_bar_layout = title_bar.layout()
        self.assertLess(title_bar_layout.indexOf(resize_handle), title_bar_layout.indexOf(close_button))

    def test_custom_chrome_is_skipped_when_disabled_or_unsupported(self) -> None:
        disabled = WindowHarness(chrome={"enabled": False}).build()
        unsupported = WindowHarness().build(overlay=FakeOverlay())
        for window in (disabled, unsupported):
            self.addCleanup(window.deleteLater)
            with self.subTest(window=window):
                self.assertIsNone(window.findChild(OverlayTitleBar))
                self.assertEqual(window.centralWidget().layout().count(), 1)

    def test_title_bar_and_grip_drags_are_reported_without_moving_the_window(self) -> None:
        harness = WindowHarness()
        overlay = Mock(wraps=FakeOverlay(uses_custom_chrome=True))
        overlay.uses_custom_chrome = True
        overlay.uses_runtime_pointer_drag = False
        window = harness.build(overlay=overlay)
        self.addCleanup(window.deleteLater)
        events: list[tuple[str, DataMap]] = []
        for name in (WINDOW_DRAGGED, WINDOW_RESIZE_DRAGGED):
            harness.engine.dispatcher.add_raw_event_handler(name, lambda event, name=name: events.append((name, event)) or [])

        title_bar = window.findChild(OverlayTitleBar)
        grip = window.findChild(OverlayResizeHandle)
        assert title_bar is not None and grip is not None
        title_bar.dragDelta.emit(3, -4, "left")
        grip.resizeDelta.emit(5, 6, "right")
        harness.engine.dispatcher.process_pending()

        self.assertEqual(
            events,
            [
                (WINDOW_DRAGGED, {"window": "pad", "dx": 3, "dy": -4, "button": "left"}),
                (WINDOW_RESIZE_DRAGGED, {"window": "pad", "dx": 5, "dy": 6, "button": "right"}),
            ],
        )
        overlay.move_by.assert_not_called()
        overlay.resize_by.assert_not_called()

    def test_move_to_and_resize_to_reach_the_point_and_size_asked_for(self) -> None:
        harness = WindowHarness()
        overlay = Mock(wraps=FakeOverlay(uses_custom_chrome=True))
        overlay.uses_custom_chrome = True
        overlay.uses_runtime_pointer_drag = False
        overlay.position.return_value = (100, 50)
        window = harness.build(overlay=overlay)
        self.addCleanup(window.deleteLater)
        window.resize(400, 300)

        window.move_to(300, 80)
        window.resize_to(500, 250)

        overlay.move_by.assert_called_once_with(200, 30)
        overlay.resize_by.assert_called_once_with(100, -50)

    def test_a_click_presses_the_button_under_the_point_with_the_mouse_button_asked_for(self) -> None:
        harness = WindowHarness()
        window = harness.build()
        self.addCleanup(window.deleteLater)
        window.show()
        presses: list[DataMap] = []
        harness.engine.dispatcher.add_raw_event_handler(BUTTON_PRESSED, lambda event: presses.append(event) or [])
        key = next(button for button in window.findChildren(QPushButton) if button.property("componentId") == "pad:a")

        window.click_at(*key.mapToGlobal(key.rect().center()).toTuple(), "right")
        wait_until(lambda: presses)

        self.assertEqual(presses, [{"node": "pad:a", "button": "right"}])

    def test_title_bar_and_grip_report_where_each_drag_starts_and_ends(self) -> None:
        harness = WindowHarness()
        window = harness.build()
        self.addCleanup(window.deleteLater)
        events: list[tuple[str, object]] = []
        for name in (WINDOW_DRAG_STARTED, WINDOW_DRAG_ENDED, WINDOW_RESIZE_DRAG_STARTED, WINDOW_RESIZE_DRAG_ENDED):
            harness.engine.dispatcher.add_event_handler(
                name,
                lambda event, name=name: events.append((name, event)) or [],
            )

        title_bar = window.findChild(OverlayTitleBar)
        grip = window.findChild(OverlayResizeHandle)
        assert title_bar is not None and grip is not None
        title_bar.dragStarted.emit("middle")
        title_bar.dragEnded.emit()
        grip.resizeStarted.emit("right")
        grip.resizeEnded.emit()
        self.assertEqual(events, [])
        harness.engine.dispatcher.process_pending()

        self.assertEqual(
            events,
            [
                (WINDOW_DRAG_STARTED, WindowButtonArguments("pad", "middle")),
                (WINDOW_DRAG_ENDED, WindowArguments("pad")),
                (WINDOW_RESIZE_DRAG_STARTED, WindowButtonArguments("pad", "right")),
                (WINDOW_RESIZE_DRAG_ENDED, WindowArguments("pad")),
            ],
        )

    def test_runtime_title_bar_drag_suppresses_qt_motion_deltas(self) -> None:
        qt_app()
        title_bar = OverlayTitleBar("Test", use_runtime_drag_motion=True)
        deltas: list[tuple[int, int]] = []
        lifecycle: list[str] = []
        title_bar.dragDelta.connect(lambda dx, dy: deltas.append((dx, dy)))
        title_bar.dragStarted.connect(lambda: lifecycle.append("started"))
        title_bar.dragEnded.connect(lambda: lifecycle.append("ended"))

        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            QPointF(500, 500),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        title_bar.mousePressEvent(press)

        for local, global_position in ((QPointF(-20, 30), QPointF(0, 0)), (QPointF(40, -5), QPointF(2000, 1000))):
            move = QMouseEvent(
                QEvent.Type.MouseMove,
                local,
                global_position,
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            title_bar.mouseMoveEvent(move)

        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(40, -5),
            QPointF(2000, 1000),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        title_bar.mouseReleaseEvent(release)

        self.assertEqual(deltas, [])
        self.assertEqual(lifecycle, ["started", "ended"])

    def test_any_mouse_button_drags_the_title_bar_and_grip_and_is_named(self) -> None:
        qt_app()
        title_bar = OverlayTitleBar("Test")
        grip = OverlayResizeHandle()
        drags: list[tuple[int, int, str]] = []
        title_bar.dragDelta.connect(lambda dx, dy, button: drags.append((dx, dy, button)))
        grip.resizeDelta.connect(lambda dx, dy, button: drags.append((dx, dy, button)))
        resizes: list[str] = []
        grip.resizeStarted.connect(lambda button: resizes.append(f"started {button}"))
        grip.resizeEnded.connect(lambda: resizes.append("ended"))

        def drag(widget: Any, button: Qt.MouseButton) -> None:
            widget.mousePressEvent(
                QMouseEvent(
                    QEvent.Type.MouseButtonPress, QPointF(1, 1), QPointF(100, 100), button, button, Qt.KeyboardModifier.NoModifier
                )
            )
            widget.mouseMoveEvent(
                QMouseEvent(
                    QEvent.Type.MouseMove,
                    QPointF(3, 4),
                    QPointF(102, 103),
                    Qt.MouseButton.NoButton,
                    button,
                    Qt.KeyboardModifier.NoModifier,
                )
            )
            widget.mouseReleaseEvent(
                QMouseEvent(
                    QEvent.Type.MouseButtonRelease,
                    QPointF(3, 4),
                    QPointF(102, 103),
                    button,
                    Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier,
                )
            )

        drag(title_bar, Qt.MouseButton.RightButton)
        drag(grip, Qt.MouseButton.MiddleButton)

        self.assertEqual(drags, [(2, 3, "right"), (2, 3, "middle")])
        self.assertEqual(resizes, ["started middle", "ended"])

    def test_close_button_reports_its_mouse_button_through_the_window(self) -> None:
        harness = WindowHarness()
        window = harness.build(overlay=FakeOverlay(uses_custom_chrome=True))
        self.addCleanup(window.deleteLater)
        window.show()
        events: list[object] = []
        harness.engine.dispatcher.add_event_handler(WINDOW_CLOSE_REQUESTED, lambda event: events.append(event) or [])
        close_button = window.findChild(QPushButton, "layerShellCloseButton")
        assert close_button is not None

        QTest.mouseClick(close_button, Qt.MouseButton.RightButton)
        harness.engine.dispatcher.process_pending()

        self.assertEqual(events, [WindowCloseRequestedArguments("pad", "right")])
        self.assertTrue(window.isVisible())

    def test_non_raw_title_bar_drag_uses_incremental_global_positions(self) -> None:
        qt_app()
        title_bar = OverlayTitleBar("Test")
        deltas: list[tuple[int, int]] = []
        title_bar.dragDelta.connect(lambda dx, dy: deltas.append((dx, dy)))

        title_bar.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(10, 10),
                QPointF(100, 100),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        title_bar.mouseMoveEvent(
            QMouseEvent(
                QEvent.Type.MouseMove,
                QPointF(12, 13),
                QPointF(105, 107),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )

        self.assertEqual(deltas, [(5, 7)])

    def test_runtime_title_bar_ends_drag_when_mouse_grab_is_lost(self) -> None:
        qt_app()
        title_bar = OverlayTitleBar("Test", use_runtime_drag_motion=True)
        lifecycle: list[str] = []
        title_bar.dragStarted.connect(lambda: lifecycle.append("started"))
        title_bar.dragEnded.connect(lambda: lifecycle.append("ended"))
        title_bar.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(10, 10),
                QPointF(100, 100),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )

        title_bar.event(QEvent(QEvent.Type.UngrabMouse))
        title_bar.event(QEvent(QEvent.Type.UngrabMouse))

        self.assertEqual(lifecycle, ["started", "ended"])

    def test_root_surface_uses_styled_background(self) -> None:
        window = WindowHarness().build()
        self.addCleanup(window.deleteLater)

        central = window.centralWidget()
        self.assertTrue(central.testAttribute(Qt.WidgetAttribute.WA_StyledBackground))
        self.assertEqual(central.objectName(), "rootSurface")

    def test_startup_size_uses_minimum_size(self) -> None:
        window = WindowHarness().build()
        self.addCleanup(window.deleteLater)

        self.assertEqual(window.size(), window.minimumSize())
        self.assertEqual(window.minimumSize(), window.minimumSizeHint().expandedTo(window.minimumSize()))
        self.assertLessEqual(window.minimumWidth(), window.width())
        self.assertLessEqual(window.minimumHeight(), window.height())

    def test_a_bound_minimum_size_uses_current_state_on_the_first_build(self) -> None:
        harness = WindowHarness(state={"width": axidev_osk.var("integer", 100)}, minimum_size=lambda s: [s.width, 50])
        harness.engine.dispatcher.dispatch(state_set("width", 640))

        window = harness.build()
        self.addCleanup(window.deleteLater)
        window.show()

        self.assertGreaterEqual(window.minimumWidth(), 640)

    def test_hiding_and_showing_a_window_keeps_the_size_it_was_given(self) -> None:
        window = WindowHarness().build()
        self.addCleanup(window.deleteLater)
        window.show()
        window.resize(window.minimumWidth() + 200, window.minimumHeight() + 100)
        chosen = window.size()

        window.hide()
        window.show()

        self.assertEqual(window.size(), chosen)

    def test_a_smaller_minimum_size_shrinks_an_enlarged_window_only_with_fit_content(self) -> None:
        for fit_content in (True, False):
            with self.subTest(fit_content=fit_content):
                harness = WindowHarness(
                    state={"width": axidev_osk.var("integer", 400)},
                    minimum_size=lambda s: [s.width, 50],
                    fit_content=fit_content,
                )
                window = harness.build()
                self.addCleanup(window.deleteLater)
                window.show()
                window.resize(700, 300)

                harness.engine.dispatcher.dispatch(state_set("width", 300))
                harness.engine.dispatcher.process_pending()

                self.assertEqual(window.minimumWidth(), 300)
                self.assertEqual(window.width(), 300 if fit_content else 700)
                self.assertEqual(
                    harness.engine.profile.state.get(("windows", "pad", "content_size")),
                    {"width": window.minimumWidth(), "height": window.minimumHeight()},
                )

    def test_startup_size_honors_configured_minimum_size(self) -> None:
        window = WindowHarness(minimum_size=[640, 320]).build()
        self.addCleanup(window.deleteLater)

        self.assertGreaterEqual(window.minimumWidth(), 640)
        self.assertGreaterEqual(window.minimumHeight(), 320)
        self.assertEqual(window.size(), window.minimumSize())

    def test_window_installs_pointer_locator_from_its_attachment(self) -> None:
        harness = WindowHarness([axidev_osk.pointer_locator(id="glow", window="pad", gap_color="#242424")], windows=("pad", "other"))
        window = harness.build("pad")
        other = harness.build("other")
        self.addCleanup(window.deleteLater)
        self.addCleanup(other.deleteLater)

        locator = window.findChild(PointerLocator, "pointerLocator")
        self.assertIsNotNone(locator)
        self.assertIs(locator.parentWidget(), window.centralWidget())
        self.assertEqual(locator.property("componentId"), "glow")
        self.assertTrue(window.centralWidget().property("pointerLocatorEnabled"))
        self.assertIsNone(other.findChild(PointerLocator, "pointerLocator"))

    def test_window_uses_configured_overlay_placement(self) -> None:
        harness = WindowHarness(overlay={"placement": "center"})

        with patch(_CONFIGURE_OVERLAY, return_value=FakeOverlay(uses_custom_chrome=True)) as configure_overlay:
            window = build_profile_window(harness.profile.window("pad"), harness.engine)
        self.addCleanup(window.deleteLater)

        self.assertEqual(configure_overlay.call_args.kwargs["config"].placement, ANCHORS["center"])

    def test_window_can_start_at_its_own_anchor(self) -> None:
        harness = WindowHarness(overlay={"placement": {"x": 0.25, "y": 1}, "keep_on_screen": False})

        with patch(_CONFIGURE_OVERLAY, return_value=FakeOverlay(uses_custom_chrome=True)) as configure_overlay:
            window = build_profile_window(harness.profile.window("pad"), harness.engine)
        self.addCleanup(window.deleteLater)

        config = configure_overlay.call_args.kwargs["config"]
        self.assertEqual((config.placement, config.keep_on_screen), (Anchor(0.25, 1.0), False))

    def test_window_without_always_on_top_uses_plain_window(self) -> None:
        harness = WindowHarness(overlay={"always_on_top": False})

        with (
            patch(_CONFIGURE_OVERLAY) as configure_overlay,
            patch(
                "axidev_osk.windows.builder.configure_plain_window",
                return_value=FakeOverlay(),
            ) as configure_plain,
        ):
            window = build_profile_window(harness.profile.window("pad"), harness.engine)
        self.addCleanup(window.deleteLater)

        configure_overlay.assert_not_called()
        configure_plain.assert_called_once_with(window)

    def test_a_plain_window_moves_and_resizes_when_asked_except_moving_on_wayland(self) -> None:
        harness = WindowHarness(overlay={"always_on_top": False})
        window = build_profile_window(harness.profile.window("pad"), harness.engine)
        self.addCleanup(window.deleteLater)
        window.show()
        window.move(100, 50)
        window.resize(400, 300)
        start = window.pos()

        window.move_to(start.x() + 30, start.y() + 20)
        window.resize_to(450, 320)

        self.assertEqual((window.x() - start.x(), window.y() - start.y()), (30, 20))
        self.assertEqual((window.width(), window.height()), (450, 320))
        with patch("axidev_osk.windows.overlay.always_on_top.qt_platform_name", return_value="wayland"):
            with self.assertRaisesRegex(RuntimeError, "Wayland does not let an ordinary window move itself"):
                window.move_by(5, 5)

    def test_window_uses_configured_opacity(self) -> None:
        window = WindowHarness(opacity=0.85).build()
        self.addCleanup(window.deleteLater)

        self.assertAlmostEqual(window.windowOpacity(), 0.85, delta=0.005)

    def test_runtime_window_can_hide_and_restore_custom_close_control(self) -> None:
        window = WindowHarness().build()
        self.addCleanup(window.deleteLater)
        close_button = window.findChild(QPushButton, "layerShellCloseButton")
        self.assertIsNotNone(close_button)
        self.assertFalse(close_button.isHidden())

        window.set_close_enabled(False)
        self.assertTrue(close_button.isHidden())

        window.set_close_enabled(True)
        self.assertFalse(close_button.isHidden())

    def test_window_applies_configured_style(self) -> None:
        window = WindowHarness(
            style={
                "object_name": "padWindow",
                "classes": ["floating"],
                "properties": {"variant": "compact"},
                "qss": "QMainWindow { background: black; }",
            }
        ).build()
        self.addCleanup(window.deleteLater)

        self.assertEqual(window.objectName(), "padWindow")
        self.assertEqual(window.property("classes"), ["floating"])
        self.assertEqual(window.property("variant"), "compact")
        self.assertEqual(window.styleSheet(), "QMainWindow { background: black; }")

    def test_runtime_window_and_nodes_expose_identity_properties(self) -> None:
        window = WindowHarness().build()
        self.addCleanup(window.deleteLater)

        self.assertEqual(window.window_id, "pad")
        self.assertEqual(window.windowTitle(), "Pad")
        self.assertEqual(window.property("componentType"), "window")
        self.assertEqual(window.property("componentId"), "pad")
        self.assertEqual(window.centralWidget().property("componentType"), "surface")
        self.assertEqual(window.centralWidget().property("componentId"), "pad")

        key = next(button for button in window.findChildren(QPushButton) if button.text() == "a")
        self.assertEqual(key.property("componentType"), "button")
        self.assertEqual(key.property("componentId"), "pad:a")

    def test_wrapped_text_is_never_cut_off_at_the_starting_size(self) -> None:
        text = "A long sentence that has to wrap over several lines inside a narrow window. " * 3
        harness = WindowHarness(
            minimum_size=[300, 80],
            content=axidev_osk.box(
                id="pad:root",
                children=[
                    axidev_osk.box(
                        id="pad:row",
                        direction="horizontal",
                        children=[
                            axidev_osk.label(id="pad:badge", text="!", min_width=40, max_width=40),
                            axidev_osk.label(id="pad:message", text=text, word_wrap=True, stretch=1),
                        ],
                    ),
                    axidev_osk.label(id="pad:hint", text=text, word_wrap=True),
                ],
            ),
        )
        window = harness.build()
        self.addCleanup(window.deleteLater)
        window.show()
        qt_app().processEvents()

        labels = [child for child in window.findChildren(QLabel) if child.wordWrap()]
        self.assertEqual(len(labels), 2)
        for label in labels:
            with self.subTest(label.property("componentId")):
                self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))

    def test_show_hide_and_minimize_record_window_visibility(self) -> None:
        harness = WindowHarness()
        window = harness.build()
        self.addCleanup(window.deleteLater)
        state = harness.engine.profile.state

        window.show()
        qt_app().processEvents()
        self.assertEqual((state.get(("windows", "pad", "visible")), state.get(("windows", "pad", "minimized"))), (True, False))

        self.assertEqual(
            state.get(("windows", "pad", "size")),
            {"width": window.width(), "height": window.height()},
        )

        window.hide()
        qt_app().processEvents()
        self.assertIs(state.get(("windows", "pad", "visible")), False)

    def test_title_opacity_and_input_block_follow_state(self) -> None:
        harness = WindowHarness(
            state={"faded": axidev_osk.var("boolean", False), "name": axidev_osk.var("string", "Pad")},
            title=lambda s: s.name,
            opacity=lambda s: 0.01 if s.faded else 0.85,
            input_blocked=lambda s: s.faded,
            content=axidev_osk.box(
                id="pad:root",
                children=[axidev_osk.button(id="pad:a", label="a"), axidev_osk.button(id="pad:ghost", label="g", passes_input_block=True)],
            ),
        )
        window = harness.build()
        self.addCleanup(window.deleteLater)
        keys = {button.property("componentId"): button for button in window.findChildren(QPushButton)}
        press = QEvent(QEvent.Type.MouseButtonPress)
        self.assertIsNone(window._input_blocker)

        harness.engine.dispatcher.dispatch(state_set("faded", True), state_set("name", "Faded"))

        self.assertEqual(window.windowTitle(), "Faded")
        self.assertAlmostEqual(window.windowOpacity(), 0.01, delta=0.005)
        blocker = window._input_blocker
        assert blocker is not None
        self.assertTrue(blocker.eventFilter(keys["pad:a"], press))
        self.assertFalse(blocker.eventFilter(keys["pad:ghost"], press))

        harness.engine.dispatcher.dispatch(state_set("faded", False))

        self.assertIsNone(window._input_blocker)
        self.assertAlmostEqual(window.windowOpacity(), 0.85, delta=0.005)


    def test_the_close_button_shows_the_close_label_and_follows_it(self) -> None:
        harness = WindowHarness(state={"close": axidev_osk.var("string", "Close")}, close_label=lambda s: s.close)
        window = harness.build()
        self.addCleanup(window.deleteLater)
        close_button = window.findChild(QPushButton, "layerShellCloseButton")
        assert close_button is not None
        self.assertEqual(close_button.text(), "Close")

        harness.engine.dispatcher.dispatch(state_set("close", "Fermer"))

        self.assertEqual(close_button.text(), "Fermer")


class RuntimeWindowDwellTests(unittest.TestCase):
    def test_dwell_controller_is_installed_only_on_the_targeted_window(self) -> None:
        harness = WindowHarness([axidev_osk.dwell(id="d", window="pad", enabled=True)], windows=("pad", "other"))
        pad = harness.build("pad")
        other = harness.build("other")
        self.addCleanup(pad.deleteLater)
        self.addCleanup(other.deleteLater)

        self.assertIsNotNone(pad._dwell_click)
        self.assertTrue(pad._dwell_click.enabled)
        self.assertIsNone(other._dwell_click)

    def test_a_finished_dwell_is_reported_instead_of_clicking(self) -> None:
        harness = WindowHarness([axidev_osk.dwell(id="d", window="pad", enabled=True)])
        window = harness.build()
        self.addCleanup(window.deleteLater)
        window.show()
        completed: list[DataMap] = []
        presses: list[DataMap] = []
        harness.engine.dispatcher.add_raw_event_handler(DWELL_COMPLETED, lambda event: completed.append(event) or [])
        harness.engine.dispatcher.add_raw_event_handler(BUTTON_PRESSED, lambda event: presses.append(event) or [])
        key = next(button for button in window.findChildren(QPushButton) if button.property("componentId") == "pad:a")
        point = key.mapToGlobal(key.rect().center())
        dwell = window._dwell_click
        assert dwell is not None

        with patch("axidev_osk.windows.dwell_click.QApplication.widgetAt", return_value=key):
            dwell.update_from_global_position(point, now=1.0)
            dwell.update_from_global_position(point, now=1.5)
        wait_until(lambda: completed)
        QTest.qWait(150)

        self.assertEqual(completed, [{"window": "pad", "x": point.x(), "y": point.y()}])
        self.assertEqual(presses, [])

    def test_bound_dwell_options_reach_the_built_window(self) -> None:
        harness = WindowHarness(
            [axidev_osk.dwell(id="d", window="pad", enabled=lambda s: s.dwell_on)],
            state={"dwell_on": axidev_osk.var("boolean", False)},
        )
        window = harness.build()
        self.addCleanup(window.deleteLater)
        self.assertFalse(window._dwell_click.enabled)

        harness.engine.dispatcher.dispatch(state_set("dwell_on", True))

        self.assertTrue(window._dwell_click.enabled)

    def test_rebuilt_window_starts_from_current_dwell_options(self) -> None:
        harness = WindowHarness(
            [axidev_osk.dwell(id="d", window="pad", enabled=lambda s: s.dwell_on)],
            state={"dwell_on": axidev_osk.var("boolean", False)},
        )
        harness.engine.dispatcher.dispatch(state_set("dwell_on", True))

        window = harness.build()
        self.addCleanup(window.deleteLater)

        self.assertTrue(window._dwell_click.enabled)


if __name__ == "__main__":
    unittest.main()
