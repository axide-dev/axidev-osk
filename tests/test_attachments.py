from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication

from axidev_osk.attachments.runtime import AttachmentRuntime
from axidev_osk.config.reader import ConfigError
from axidev_osk.hot_corner.controller import HotCornerWindowToggleController, ScreenCorner
from axidev_osk.messages import DataMap
from axidev_osk.python_defaults import axidev_osk
from axidev_osk.runtime.profile_runtime import CALLBACK_FAILED, state_set
from support import HOT_CORNER_COLORS, RecordingBackend, hot_corner_config, make_test_engine, qt_app


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
        self.dwell: list[Any] = []
        self.locators: list[Any] = []

    def set_dwell(self, config: Any) -> None:
        self.dwell.append(config)

    def set_pointer_locator(self, settings: Any) -> None:
        self.locators.append(settings)


class RecordingHotCorners:
    def __init__(self) -> None:
        self.configured: list[tuple[Any, frozenset[str]]] = []
        self.active: tuple[Any, frozenset[str]] | None = None

    def configure(self, settings: Any, corners: frozenset[str]) -> None:
        self.configured.append((settings, corners))
        self.active = (settings, corners)

    def clear(self) -> None:
        self.active = None


def _root(attachments: list[axidev_osk.Map], windows: tuple[str, ...] = ("pad",), state: axidev_osk.Map | None = None) -> axidev_osk.Map:
    return axidev_osk.config(
        active_profile="p",
        profiles={
            "p": axidev_osk.profile(
                windows=[
                    axidev_osk.window(id=window, title=window, content=axidev_osk.box(id=f"{window}:root", children=[axidev_osk.button(id=f"{window}:b")]))
                    for window in windows
                ],
                attachments=attachments,
                state=state,
            )
        },
    )


class AttachmentHarness:
    def __init__(
        self,
        attachments: list[axidev_osk.Map],
        windows: tuple[str, ...] = ("pad",),
        state: axidev_osk.Map | None = None,
        *,
        hot_corner_service: bool = True,
    ) -> None:
        qt_app()
        self.engine = make_test_engine(RecordingBackend())
        self.windows = {window: RecordingWindow() for window in windows}
        self.hot_corners = RecordingHotCorners()
        self.runtime = AttachmentRuntime(
            self.engine.bindings,
            self.engine.attachments,
            window_lookup=self.windows.get,
            hot_corners=self.hot_corners if hot_corner_service else None,
        )
        self.profile = self.engine.decoder().decode_root(_root(attachments, windows, state))
        self.engine.profile.start(self.profile)
        self.failures: list[DataMap] = []
        self.engine.dispatcher.add_raw_event_handler(CALLBACK_FAILED, lambda event: self.failures.append(event) or [])

    def start(self) -> None:
        self.runtime.start(self.profile)


class DecodeTests(unittest.TestCase):
    def test_options_are_validated_with_their_config_path(self) -> None:
        qt_app()
        engine = make_test_engine(RecordingBackend())
        cases = {
            "unknown corners: middle": axidev_osk.hot_corners(id="hc", corners=["middle"], **HOT_CORNER_COLORS),
            "delay": axidev_osk.dwell(id="d", window="pad", delay_ms=0),
            "radius": axidev_osk.pointer_locator(id="l", window="pad", radius_percent=0, gap_color="#242424"),
            "window is required": axidev_osk.secure_input_panel(id="s"),
            "indicator_background is required": axidev_osk.hot_corners(id="hc"),
            "gap_color is required": axidev_osk.pointer_locator(id="l", window="pad"),
        }
        for message, attachment in cases.items():
            with self.subTest(message), self.assertRaisesRegex(ConfigError, message):
                engine.decoder().decode_root(_root([attachment]))


    def test_references_and_limits_are_checked_at_load_in_every_profile(self) -> None:
        qt_app()
        engine = make_test_engine(RecordingBackend())
        cases = {
            "targets unknown window 'ghost'": [axidev_osk.dwell(id="d", window="ghost")],
            "window 'pad' can have at most one dwell": [axidev_osk.dwell(id="d1", window="pad"), axidev_osk.dwell(id="d2", window="pad")],
            "a profile can have at most one hot_corners": [
                axidev_osk.hot_corners(id="a", **HOT_CORNER_COLORS),
                axidev_osk.hot_corners(id="b", **HOT_CORNER_COLORS),
            ],
            "a profile can have at most one secure_input_panel": [
                axidev_osk.secure_input_panel(id="a", window="pad"),
                axidev_osk.secure_input_panel(id="b", window="pad"),
            ],
        }
        for message, attachments in cases.items():
            spare = _root(attachments)["profiles"]["p"]
            root = axidev_osk.config(active_profile="ok", profiles={"ok": _root([])["profiles"]["p"], "spare": spare})
            with self.subTest(message), self.assertRaisesRegex(ConfigError, rf"config.profiles.spare.attachments\[\d\].*{message}"):
                engine.decoder().decode_root(root)

    def test_pointer_locators_have_no_limit(self) -> None:
        qt_app()
        engine = make_test_engine(RecordingBackend())
        locators = [axidev_osk.pointer_locator(id=name, window="pad", gap_color="#242424") for name in ("a", "b")]

        self.assertEqual(len(engine.decoder().decode_root(_root(locators)).attachments), 2)


class AttachmentRuntimeTests(unittest.TestCase):
    def test_dwell_options_follow_the_state_they_are_bound_to(self) -> None:
        harness = AttachmentHarness(
            [axidev_osk.dwell(id="d", window="pad", enabled=lambda s: s.dwell_on, delay_ms=lambda s: s.delay)],
            state={"dwell_on": axidev_osk.var("boolean", True), "delay": axidev_osk.var("integer", 300)},
        )
        harness.start()

        harness.engine.dispatcher.dispatch(state_set("dwell_on", False), state_set("delay", 500))

        self.assertEqual(
            [(config.enabled, config.delay_ms) for config in harness.windows["pad"].dwell],
            [(True, 300), (False, 500)],
        )
        installed = harness.runtime.for_window("pad").dwell
        assert installed is not None
        self.assertEqual((installed.enabled, installed.delay_ms), (False, 500))

    def test_an_invalid_bound_option_is_reported_and_the_last_options_stay(self) -> None:
        harness = AttachmentHarness(
            [axidev_osk.dwell(id="d", window="pad", delay_ms=lambda s: s.delay)],
            state={"delay": axidev_osk.var("integer", 300)},
        )
        harness.start()

        harness.engine.dispatcher.dispatch(state_set("delay", 0))

        installed = harness.runtime.for_window("pad").dwell
        assert installed is not None
        self.assertEqual(installed.delay_ms, 300)
        self.assertEqual([failure["source"] for failure in harness.failures], ["attachment:d"])

    def test_hot_corners_and_panel_are_configured(self) -> None:
        harness = AttachmentHarness(
            [
                axidev_osk.hot_corners(id="hc", corners=["top_left", "bottom_right"], dwell_ms=150, **HOT_CORNER_COLORS),
                axidev_osk.secure_input_panel(id="lock", window="pad"),
            ]
        )
        harness.start()

        settings, corners = harness.hot_corners.configured[0]
        self.assertEqual((settings.dwell_ms, corners), (150, frozenset({"top_left", "bottom_right"})))
        self.assertEqual(harness.runtime.secure_input_panel_window, "pad")

    def test_an_attachment_whose_service_is_missing_is_logged_and_the_others_still_apply(self) -> None:
        harness = AttachmentHarness(
            [axidev_osk.hot_corners(id="hc", **HOT_CORNER_COLORS), axidev_osk.dwell(id="d", window="pad", delay_ms=250)],
            hot_corner_service=False,
        )

        with self.assertLogs("axidev_osk.attachments.runtime", level="WARNING") as logs:
            harness.start()

        self.assertIn("'hc' does nothing", logs.output[0])
        self.assertEqual([config.delay_ms for config in harness.windows["pad"].dwell], [250])

    def test_starting_a_profile_without_hot_corners_turns_them_off(self) -> None:
        harness = AttachmentHarness([axidev_osk.hot_corners(id="hc", **HOT_CORNER_COLORS)])
        harness.start()
        self.assertIsNotNone(harness.hot_corners.active)

        harness.runtime.start(harness.engine.decoder().decode_root(_root([])))

        self.assertIsNone(harness.hot_corners.active)


class HotCornerFilterTests(unittest.TestCase):
    def test_controller_creates_sensors_only_for_configured_corners(self) -> None:
        qt_app()
        screen = QGuiApplication.primaryScreen()
        assert screen is not None
        engine = make_test_engine(RecordingBackend())

        with patch("axidev_osk.hot_corner.controller.configure_hot_corner_overlay", return_value=FakeHotCornerOverlay()):
            controller = HotCornerWindowToggleController(engine.dispatcher, config=hot_corner_config(), corners=frozenset({"top_left"}))
            handles = controller._create_sensor_handles([screen])

        self.assertEqual([handle.corner for handle in handles], [ScreenCorner.TOP_LEFT])


if __name__ == "__main__":
    unittest.main()
