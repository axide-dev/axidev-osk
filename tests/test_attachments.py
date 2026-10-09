from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication

from axidev_osk.attachments.runtime import AttachmentRuntime, dwell_set_enabled
from axidev_osk.config.reader import ConfigError
from axidev_osk.hot_corner.controller import HotCornerWindowToggleController, ScreenCorner
from axidev_osk.messages import DataMap
from axidev_osk.python_defaults import osk
from axidev_osk.runtime.testing import make_test_context
from support import RecordingBackend, qt_app


class FakeHotCornerOverlay:
    """Overlay calls a hot-corner sensor window makes, all doing nothing."""

    backend = None

    def handle_show(self) -> bool:
        return True

    def set_screen(self, screen: object) -> None:
        del screen

    def move_to(self, position: QPoint, *, screen_geometry: QRect | None = None) -> None:
        del position, screen_geometry

    def move_to_anchored(self, position: QPoint, *, anchors: int, screen_geometry: QRect | None = None) -> None:
        del position, anchors, screen_geometry

    def release_resources(self) -> None:
        return None


class RecordingWindow:
    def __init__(self) -> None:
        self.dwell: list[bool] = []

    def set_dwell_enabled(self, enabled: bool) -> None:
        self.dwell.append(enabled)


class RecordingHotCorners:
    def __init__(self) -> None:
        self.configured: list[tuple[Any, frozenset[str]]] = []

    def configure(self, settings: Any, corners: frozenset[str]) -> None:
        self.configured.append((settings, corners))


def _root(attachments: list[osk.Map], windows: tuple[str, ...] = ("pad",)) -> osk.Map:
    return osk.config(
        active_profile="p",
        profiles={
            "p": osk.profile(
                windows=[
                    osk.window(id=window, title=window, content=osk.box(id=f"{window}:root", children=[osk.button(id=f"{window}:b")]))
                    for window in windows
                ],
                attachments=attachments,
            )
        },
    )


class AttachmentHarness:
    def __init__(self, attachments: list[osk.Map], windows: tuple[str, ...] = ("pad",)) -> None:
        qt_app()
        self.context = make_test_context(RecordingBackend())
        self.engine = self.context.engine
        self.windows = {window: RecordingWindow() for window in windows}
        self.hot_corners = RecordingHotCorners()
        self.runtime = AttachmentRuntime(
            self.context.dispatcher,
            self.engine.profile,
            window_lookup=self.windows.get,
            hot_corners=self.hot_corners,
        )
        self.profile = self.engine.decoder().decode_root(_root(attachments, windows))
        self.engine.profile.start(self.profile)
        self.failures: list[DataMap] = []
        self.context.dispatcher.add_raw_event_handler("action.failed", lambda event: self.failures.append(event) or [])

    def start(self) -> None:
        self.runtime.start(self.profile)


class DecodeTests(unittest.TestCase):
    def test_options_are_validated_with_their_config_path(self) -> None:
        qt_app()
        engine = make_test_context(RecordingBackend()).engine
        cases = {
            "unknown corners: middle": osk.hot_corners(id="hc", corners=["middle"]),
            "delay": osk.dwell(id="d", window="pad", delay_ms=0),
            "radius": osk.pointer_locator(id="l", window="pad", radius_percent=0),
            "window is required": osk.secure_input_panel(id="s"),
        }
        for message, attachment in cases.items():
            with self.subTest(message), self.assertRaisesRegex(ConfigError, message):
                engine.decoder().decode_root(_root([attachment]))


class AttachmentRuntimeTests(unittest.TestCase):
    def test_references_are_checked_at_start(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown window 'ghost'"):
            AttachmentHarness([osk.dwell(id="d", window="ghost")]).start()
        with self.assertRaisesRegex(ValueError, "more than one dwell"):
            AttachmentHarness([osk.dwell(id="d1", window="pad"), osk.dwell(id="d2", window="pad")]).start()

    def test_dwell_state_is_seeded_toggled_and_applied_to_its_window(self) -> None:
        harness = AttachmentHarness([osk.dwell(id="d", window="pad", enabled=True, delay_ms=300)])
        harness.start()

        self.assertIs(harness.engine.profile.state.get(("dwell", "d", "enabled")), True)
        harness.context.dispatcher.dispatch(dwell_set_enabled("d", False))

        self.assertIs(harness.engine.profile.state.get(("dwell", "d", "enabled")), False)
        self.assertEqual(harness.windows["pad"].dwell, [False])
        installed = harness.runtime.for_window("pad").dwell
        assert installed is not None
        self.assertEqual((installed.enabled, installed.delay_ms), (False, 300))

    def test_unknown_dwell_fails_the_action(self) -> None:
        harness = AttachmentHarness([])
        harness.start()

        harness.context.dispatcher.dispatch(dwell_set_enabled("nope", True))

        self.assertEqual([failure["action"] for failure in harness.failures], ["dwell.set_enabled"])

    def test_hot_corners_and_panel_are_configured(self) -> None:
        harness = AttachmentHarness(
            [
                osk.hot_corners(id="hc", corners=["top_left", "bottom_right"], dwell_ms=150),
                osk.secure_input_panel(id="lock", window="pad"),
            ]
        )
        harness.start()

        settings, corners = harness.hot_corners.configured[0]
        self.assertEqual((settings.dwell_ms, corners), (150, frozenset({"top_left", "bottom_right"})))
        self.assertEqual(harness.runtime.secure_input_panel_window, "pad")


class HotCornerFilterTests(unittest.TestCase):
    def test_controller_creates_sensors_only_for_configured_corners(self) -> None:
        qt_app()
        screen = QGuiApplication.primaryScreen()
        assert screen is not None
        context = make_test_context(RecordingBackend())

        with patch("axidev_osk.hot_corner.controller.configure_hot_corner_overlay", return_value=FakeHotCornerOverlay()):
            controller = HotCornerWindowToggleController(context.dispatcher, corners=frozenset({"top_left"}))
            handles = controller._create_sensor_handles([screen])

        self.assertEqual([handle.corner for handle in handles], [ScreenCorner.TOP_LEFT])


if __name__ == "__main__":
    unittest.main()
