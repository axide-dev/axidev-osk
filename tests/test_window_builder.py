from __future__ import annotations

import inspect
import unittest
from typing import Any
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QPushButton

from axidev_osk.attachments.runtime import AttachmentRuntime, dwell_set_enabled
from axidev_osk.components.pointer_locator import PointerLocator
from axidev_osk.config.models import ChromeConfig, OverlayConfig
from axidev_osk.config.profile import ProfileConfig
from axidev_osk.python_defaults import osk
from axidev_osk.runtime.context import Context
from axidev_osk.runtime.events import (
    WINDOW_CLOSE_REQUESTED,
    WINDOW_DRAG_ENDED,
    WINDOW_DRAG_STARTED,
    WindowEventArguments,
)
from axidev_osk.runtime.testing import make_test_context, start_test_profile
from axidev_osk.windows.builder import RuntimeWindow, build_profile_window
from axidev_osk.windows.chrome import OverlayResizeHandle, OverlayTitleBar
from axidev_osk.windows.overlay.always_on_top import OverlayPlacement

_CONFIGURE_OVERLAY = "axidev_osk.windows.builder.configure_always_on_top_window"


class FakeKeyboardBackend:
    ready = True
    status_text = "ready"
    needs_permission_setup = False
    permission_setup_text = ""

    def initialize(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def add_observation_listener(self, listener):
        del listener
        return lambda: None

    def canonical_key(self, key: str) -> str:
        return key

    def press(self, key: str, mods: tuple[str, ...], repeat: bool):
        del key, mods, repeat
        return None

    def key_up(self, handle) -> None:
        del handle

    def tap(self, key: str, mods: tuple[str, ...]) -> None:
        del key, mods

    def type_text(self, text: str) -> None:
        del text


class FakeOverlayController:
    def __init__(self, *, uses_custom_chrome: bool = True, uses_runtime_pointer_drag: bool = False) -> None:
        self.uses_custom_chrome = uses_custom_chrome
        self.uses_runtime_pointer_drag = uses_runtime_pointer_drag

    def prepare_show(self) -> bool:
        return True

    def move_by(self, dx: int, dy: int) -> None:
        return None

    def resize_by(self, dx: int, dy: int) -> None:
        return None

    def handle_show(self) -> bool:
        return True

    def apply_configured_position(self) -> None:
        return None


def _app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    return app


def _root(attachments: list[osk.Map] | None = None, windows: tuple[str, ...] = ("pad",), **window_fields: Any) -> osk.Map:
    return osk.config(
        active_profile="p",
        profiles={
            "p": osk.profile(
                windows=[
                    osk.window(
                        **osk.merge(
                            {
                                "id": window,
                                "title": window.title(),
                                "content": osk.box(
                                    id=f"{window}:root",
                                    children=[osk.button(id=f"{window}:a", label="a")],
                                ),
                            },
                            window_fields,
                        )
                    )
                    for window in windows
                ],
                attachments=attachments or [],
            )
        },
    )


class WindowHarness:
    """A started profile with its attachment runtime, ready to build windows."""

    def __init__(self, attachments: list[osk.Map] | None = None, windows: tuple[str, ...] = ("pad",), **window_fields: Any) -> None:
        _app()
        self.context: Context = make_test_context(FakeKeyboardBackend())
        self.built: dict[str, RuntimeWindow] = {}
        self.attachments = AttachmentRuntime(
            self.context.dispatcher,
            self.context.engine.profile,
            window_lookup=self.built.get,
        )
        self.profile: ProfileConfig = start_test_profile(self.context, _root(attachments, windows, **window_fields))
        self.attachments.start(self.profile)

    def build(self, window_id: str = "pad", overlay: object | None = None) -> RuntimeWindow:
        with patch(_CONFIGURE_OVERLAY, return_value=overlay or FakeOverlayController()):
            window = build_profile_window(
                self.profile.window(window_id),
                self.context,
                attachments=self.attachments.for_window(window_id),
            )
        self.built[window_id] = window
        return window


class RuntimeWindowCloseTests(unittest.TestCase):
    def _record_close_requests(self, harness: WindowHarness) -> list[WindowEventArguments]:
        events: list[WindowEventArguments] = []
        harness.context.dispatcher.add_event_handler(
            WINDOW_CLOSE_REQUESTED,
            lambda close_event: events.append(close_event) or [],
        )
        return events

    def test_managed_close_requests_close_through_dispatcher(self) -> None:
        harness = WindowHarness()
        window = harness.build()
        self.addCleanup(window.close)
        events = self._record_close_requests(harness)
        window.set_quit_controller_managed(True)

        event = QCloseEvent()
        window.closeEvent(event)

        self.assertFalse(event.isAccepted())
        self.assertEqual(events, [WindowEventArguments("pad")])
        window.set_quit_controller_managed(False)

    def test_unmanaged_close_is_accepted_without_a_request(self) -> None:
        harness = WindowHarness()
        window = harness.build()
        events = self._record_close_requests(harness)

        event = QCloseEvent()
        window.closeEvent(event)

        self.assertTrue(event.isAccepted())
        self.assertEqual(events, [])

    def test_removed_output_close_does_not_request_application_quit(self) -> None:
        harness = WindowHarness()
        overlay = FakeOverlayController()
        overlay.has_removed_output = Mock(return_value=True)  # type: ignore[attr-defined]
        window = harness.build(overlay=overlay)
        events = self._record_close_requests(harness)
        try:
            window.set_quit_controller_managed(True)
            event = QCloseEvent()
            window.closeEvent(event)
            self.assertFalse(event.isAccepted())
            self.assertEqual(events, [])

            overlay.has_removed_output.return_value = False  # type: ignore[attr-defined]
            window.closeEvent(QCloseEvent())
            self.assertEqual(events, [WindowEventArguments("pad")])
        finally:
            overlay.has_removed_output.return_value = False  # type: ignore[attr-defined]
            window.set_quit_controller_managed(False)
            window.close()


class RuntimeWindowLayoutTests(unittest.TestCase):
    """Tests covering profile windows built via ``build_profile_window``."""

    def test_failed_content_build_releases_platform_resources(self) -> None:
        _app()
        context = make_test_context(FakeKeyboardBackend())
        overlay = Mock()

        with (
            patch(_CONFIGURE_OVERLAY, return_value=overlay),
            self.assertRaisesRegex(RuntimeError, "content failed"),
        ):
            RuntimeWindow(
                window_id="pad",
                title="Pad",
                overlay=OverlayConfig(),
                chrome=ChromeConfig(),
                opacity=1.0,
                minimum_size=(0, 0),
                build_content=Mock(side_effect=RuntimeError("content failed")),
                context=context,
            )

        overlay.release_resources.assert_called_once_with()

    def test_custom_chrome_puts_resize_handle_in_title_bar(self) -> None:
        window = WindowHarness().build()
        self.addCleanup(window.close)

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
        unsupported = WindowHarness().build(overlay=FakeOverlayController(uses_custom_chrome=False))
        for window in (disabled, unsupported):
            self.addCleanup(window.close)
            with self.subTest(window=window):
                self.assertIsNone(window.findChild(OverlayTitleBar))
                self.assertEqual(window.centralWidget().layout().count(), 1)

    def test_runtime_pointer_drag_reports_drag_events_for_the_window(self) -> None:
        harness = WindowHarness()
        window = harness.build(overlay=FakeOverlayController(uses_runtime_pointer_drag=True))
        self.addCleanup(window.close)
        events: list[tuple[str, WindowEventArguments]] = []
        for name in (WINDOW_DRAG_STARTED, WINDOW_DRAG_ENDED):
            harness.context.dispatcher.add_event_handler(
                name,
                lambda event, name=name: events.append((name, event)) or [],
            )

        title_bar = window.findChild(OverlayTitleBar)
        assert title_bar is not None
        title_bar.dragStarted.emit()
        title_bar.dragEnded.emit()

        self.assertEqual(
            events,
            [(WINDOW_DRAG_STARTED, WindowEventArguments("pad")), (WINDOW_DRAG_ENDED, WindowEventArguments("pad"))],
        )

    def test_qt_pointer_drag_does_not_report_drag_events(self) -> None:
        harness = WindowHarness()
        window = harness.build()
        self.addCleanup(window.close)
        events: list[object] = []
        harness.context.dispatcher.add_raw_event_handler(WINDOW_DRAG_STARTED, lambda event: events.append(event) or [])

        title_bar = window.findChild(OverlayTitleBar)
        assert title_bar is not None
        title_bar.dragStarted.emit()

        self.assertEqual(events, [])

    def test_runtime_title_bar_drag_suppresses_qt_motion_deltas(self) -> None:
        _app()
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

    def test_non_raw_title_bar_drag_uses_incremental_global_positions(self) -> None:
        _app()
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
        _app()
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
        self.addCleanup(window.close)

        central = window.centralWidget()
        self.assertTrue(central.testAttribute(Qt.WidgetAttribute.WA_StyledBackground))
        self.assertEqual(central.objectName(), "rootSurface")

    def test_startup_size_uses_minimum_size(self) -> None:
        window = WindowHarness().build()
        self.addCleanup(window.close)

        self.assertEqual(window.size(), window.minimumSize())
        self.assertEqual(window.minimumSize(), window.minimumSizeHint().expandedTo(window.minimumSize()))
        self.assertLessEqual(window.minimumWidth(), window.width())
        self.assertLessEqual(window.minimumHeight(), window.height())

    def test_startup_size_honors_configured_minimum_size(self) -> None:
        window = WindowHarness(minimum_size=[640, 320]).build()
        self.addCleanup(window.close)

        self.assertGreaterEqual(window.minimumWidth(), 640)
        self.assertGreaterEqual(window.minimumHeight(), 320)
        self.assertEqual(window.size(), window.minimumSize())

    def test_window_installs_pointer_locator_from_its_attachment(self) -> None:
        harness = WindowHarness([osk.pointer_locator(id="glow", window="pad")], windows=("pad", "other"))
        window = harness.build("pad")
        other = harness.build("other")
        self.addCleanup(window.close)
        self.addCleanup(other.close)

        locator = window.findChild(PointerLocator, "pointerLocator")
        self.assertIsNotNone(locator)
        self.assertIs(locator.parentWidget(), window.centralWidget())
        self.assertEqual(locator.property("componentId"), "glow")
        self.assertTrue(window.centralWidget().property("pointerLocatorEnabled"))
        self.assertIsNone(other.findChild(PointerLocator, "pointerLocator"))

    def test_runtime_window_has_no_pointer_locator_branch(self) -> None:
        source = inspect.getsource(RuntimeWindow.__init__)

        self.assertNotIn("PointerLocator", source)
        self.assertNotIn("pointerLocatorEnabled", source)

    def test_window_uses_configured_overlay_placement(self) -> None:
        harness = WindowHarness(overlay={"placement": "center"})

        with patch(_CONFIGURE_OVERLAY, return_value=FakeOverlayController()) as configure_overlay:
            window = build_profile_window(harness.profile.window("pad"), harness.context)
        self.addCleanup(window.close)

        self.assertEqual(configure_overlay.call_args.kwargs["config"].placement, OverlayPlacement.CENTER)

    def test_window_without_always_on_top_uses_plain_window(self) -> None:
        harness = WindowHarness(overlay={"always_on_top": False})

        with (
            patch(_CONFIGURE_OVERLAY) as configure_overlay,
            patch(
                "axidev_osk.windows.builder.configure_plain_window",
                return_value=FakeOverlayController(uses_custom_chrome=False),
            ) as configure_plain,
        ):
            window = build_profile_window(harness.profile.window("pad"), harness.context)
        self.addCleanup(window.close)

        configure_overlay.assert_not_called()
        configure_plain.assert_called_once_with(window)

    def test_window_uses_configured_opacity(self) -> None:
        window = WindowHarness(opacity=0.85).build()
        self.addCleanup(window.close)

        self.assertAlmostEqual(window.configured_opacity, 0.85)
        self.assertAlmostEqual(window.windowOpacity(), 0.85, delta=0.005)

    def test_runtime_window_can_hide_and_restore_custom_close_control(self) -> None:
        window = WindowHarness().build()
        self.addCleanup(window.close)
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
        self.addCleanup(window.close)

        self.assertEqual(window.objectName(), "padWindow")
        self.assertEqual(window.property("classes"), ["floating"])
        self.assertEqual(window.property("variant"), "compact")
        self.assertEqual(window.styleSheet(), "QMainWindow { background: black; }")

    def test_runtime_window_and_nodes_expose_identity_properties(self) -> None:
        window = WindowHarness().build()
        self.addCleanup(window.close)

        self.assertEqual(window.window_id, "pad")
        self.assertEqual(window.windowTitle(), "Pad")
        self.assertEqual(window.property("componentType"), "window")
        self.assertEqual(window.property("componentId"), "pad")
        self.assertEqual(window.centralWidget().property("componentType"), "surface")
        self.assertEqual(window.centralWidget().property("componentId"), "pad")

        key = next(button for button in window.findChildren(QPushButton) if button.text() == "a")
        self.assertEqual(key.property("componentType"), "button")
        self.assertEqual(key.property("componentId"), "pad:a")

    def test_show_hide_and_minimize_record_window_visibility(self) -> None:
        harness = WindowHarness()
        window = harness.build()
        self.addCleanup(window.close)
        state = harness.context.engine.state

        window.show()
        self.assertEqual((state.get(("windows", "pad", "visible")), state.get(("windows", "pad", "minimized"))), (True, False))

        window.hide()
        self.assertIs(state.get(("windows", "pad", "visible")), False)


class RuntimeWindowDwellTests(unittest.TestCase):
    def test_dwell_controller_is_installed_only_on_the_targeted_window(self) -> None:
        harness = WindowHarness([osk.dwell(id="d", window="pad", enabled=True)], windows=("pad", "other"))
        pad = harness.build("pad")
        other = harness.build("other")
        self.addCleanup(pad.close)
        self.addCleanup(other.close)

        self.assertIsNotNone(pad._dwell_click)
        self.assertTrue(pad._dwell_click.enabled)
        self.assertIsNone(other._dwell_click)
        other.set_dwell_enabled(True)
        self.assertIsNone(other._dwell_click)

    def test_dwell_set_enabled_reaches_the_built_window(self) -> None:
        harness = WindowHarness([osk.dwell(id="d", window="pad", enabled=False)])
        window = harness.build()
        self.addCleanup(window.close)
        self.assertFalse(window._dwell_click.enabled)

        harness.context.dispatcher.dispatch_action(dwell_set_enabled("d", True))

        self.assertTrue(window._dwell_click.enabled)

    def test_rebuilt_window_restores_current_dwell_state(self) -> None:
        harness = WindowHarness([osk.dwell(id="d", window="pad", enabled=False)])
        harness.context.dispatcher.dispatch_action(dwell_set_enabled("d", True))
        self.assertIs(harness.context.engine.state.get(("dwell", "d", "enabled")), True)

        window = harness.build()
        self.addCleanup(window.close)

        self.assertTrue(window._dwell_click.enabled)


if __name__ == "__main__":
    unittest.main()
