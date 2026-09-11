from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QEvent, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.config.models import DwellClickConfig
from axidev_osk.windows.dwell_click import DwellClickController


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _MouseEventRecorder(QWidget):
    def __init__(self, events: list[QEvent.Type], parent: QWidget) -> None:
        super().__init__(parent)
        self._events = events

    def mousePressEvent(  # type: ignore[override]
        self,
        event: QMouseEvent,
    ) -> None:
        self._events.append(event.type())
        event.accept()

    def mouseReleaseEvent(  # type: ignore[override]
        self,
        event: QMouseEvent,
    ) -> None:
        self._events.append(event.type())
        event.accept()


class DwellClickConfigTests(unittest.TestCase):
    def test_default_keyboard_enables_dwell_click(self) -> None:
        config = build_default_app_config().windows[0].dwell_click

        self.assertTrue(config.enabled)
        self.assertEqual(config.delay_ms, 200)
        self.assertEqual(config.dead_zone_px, 10)
        self.assertEqual(config.full_speed_px_s, 20)
        self.assertEqual(config.stop_speed_px_s, 240)
        self.assertEqual(config.maximum_progress_rate, 1.75)
        self.assertEqual(config.indicator_start_progress, 0.25)
        self.assertEqual(config.direction_reversal_progress_factor, 0.5)
        self.assertEqual(config.movement_penalty_px, 15)
        self.assertEqual(config.distance_curve_full_px, 200)
        self.assertEqual(config.velocity_release_ms, 100)

    def test_config_rejects_invalid_delay_and_dead_zone(self) -> None:
        for delay in (0, float("nan"), float("inf")):
            with self.subTest(delay=delay):
                with self.assertRaisesRegex(
                    ValueError,
                    "at least 1 millisecond",
                ):
                    DwellClickConfig(delay_ms=delay)
        for dead_zone in (-1, float("nan"), float("inf")):
            with self.subTest(dead_zone=dead_zone):
                with self.assertRaisesRegex(
                    ValueError,
                    "finite and non-negative",
                ):
                    DwellClickConfig(dead_zone_px=dead_zone)
        with self.assertRaisesRegex(ValueError, "full speed"):
            DwellClickConfig(full_speed_px_s=-1)
        with self.assertRaisesRegex(ValueError, "stop speed"):
            DwellClickConfig(full_speed_px_s=20, stop_speed_px_s=20)
        for rate in (0.5, float("nan"), float("inf")):
            with self.subTest(maximum_progress_rate=rate):
                with self.assertRaisesRegex(ValueError, "maximum progress rate"):
                    DwellClickConfig(maximum_progress_rate=rate)
        for progress in (-0.1, 1.1, float("nan"), float("inf")):
            with self.subTest(indicator_start_progress=progress):
                with self.assertRaisesRegex(ValueError, "indicator start progress"):
                    DwellClickConfig(indicator_start_progress=progress)
            with self.subTest(direction_reversal_progress_factor=progress):
                with self.assertRaisesRegex(ValueError, "direction reversal"):
                    DwellClickConfig(direction_reversal_progress_factor=progress)
        for distance in (0, -1, float("nan"), float("inf")):
            with self.subTest(movement_penalty_px=distance):
                with self.assertRaisesRegex(ValueError, "movement penalty distance"):
                    DwellClickConfig(movement_penalty_px=distance)
            with self.subTest(distance_curve_full_px=distance):
                with self.assertRaisesRegex(ValueError, "full curve distance"):
                    DwellClickConfig(distance_curve_full_px=distance)
        for release in (0, float("nan"), float("inf")):
            with self.subTest(release=release):
                with self.assertRaisesRegex(
                    ValueError,
                    "at least 1 millisecond",
                ):
                    DwellClickConfig(velocity_release_ms=release)


class DwellClickControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        _app()
        self.window = QWidget()
        self.window.setGeometry(100, 100, 240, 100)
        self.key = QPushButton("A", self.window)
        self.key.setProperty("componentType", "key")
        self.key.setGeometry(10, 10, 80, 80)
        self.other_key = QPushButton("B", self.window)
        self.other_key.setProperty("componentType", "key")
        self.other_key.setGeometry(110, 10, 80, 80)
        self.window.show()
        QApplication.processEvents()
        self.controller = DwellClickController(
            self.window,
            self.window,
            DwellClickConfig(
                enabled=True,
                delay_ms=200,
                dead_zone_px=10,
                full_speed_px_s=20,
                stop_speed_px_s=240,
                maximum_progress_rate=1.75,
                indicator_start_progress=0.25,
                direction_reversal_progress_factor=0.5,
                movement_penalty_px=15,
                distance_curve_full_px=200,
                velocity_release_ms=100,
            ),
        )
        self.addCleanup(self.window.close)

    def test_activates_exact_key_under_current_pointer(self) -> None:
        clicks: list[str] = []
        self.key.clicked.connect(lambda: clicks.append("A"))
        self.other_key.clicked.connect(lambda: clicks.append("B"))
        first_position = self.other_key.mapToGlobal(QPoint(20, 20))
        current_position = self.other_key.mapToGlobal(QPoint(24, 20))

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=self.other_key,
        ):
            self.controller.update_from_global_position(
                first_position,
                now=1.0,
            )
            self.controller.update_from_global_position(
                current_position,
                now=1.21,
            )
            self.controller.update_from_global_position(
                current_position,
                now=1.3,
            )

        self.assertTrue(self.other_key.isDown())
        QTest.qWait(150)
        self.assertEqual(clicks, ["B"])
        self.assertFalse(self.other_key.isDown())
        self.assertFalse(self.other_key.isChecked())
        self.assertTrue(self.controller.indicator.complete_feedback.isVisible())

    def test_indicator_tracks_progress_at_pointer_position(self) -> None:
        current_position = self.key.mapToGlobal(QPoint(24, 20))

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=self.key,
        ):
            self.controller.update_from_global_position(
                current_position,
                now=1.0,
            )
            self.assertFalse(self.controller.indicator.isVisible())
            self.controller.update_from_global_position(
                current_position,
                now=1.04,
            )
            self.assertFalse(self.controller.indicator.isVisible())
            self.controller.update_from_global_position(
                current_position,
                now=1.05,
            )

        indicator = self.controller.indicator
        self.assertTrue(indicator.isVisible())
        self.assertAlmostEqual(indicator.progress, 0.25)
        expected_color = indicator.palette().color(
            indicator.palette().ColorRole.Mid,
        )
        self.assertEqual(
            indicator.progress_color.name(),
            expected_color.name(),
        )
        self.assertEqual(indicator.track_color.name(), expected_color.name())
        self.assertLess(indicator.track_color.alpha(), indicator.progress_color.alpha())
        painted_center = indicator.pos() + QPoint(
            indicator.width() // 2,
            indicator.height() // 2,
        )
        self.assertEqual(
            painted_center,
            self.window.mapFromGlobal(current_position),
        )
        self.assertTrue(
            indicator.testAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            )
        )

    def test_progress_rate_decreases_with_pointer_speed(self) -> None:
        self.assertEqual(self.controller._progress_rate(20), 1.0)
        self.controller._deceleration_score = 0.25
        self.assertEqual(self.controller._progress_rate(20), 1.375)
        self.controller._deceleration_score = 1.0
        self.assertEqual(self.controller._progress_rate(20), 1.75)
        self.assertEqual(self.controller._progress_rate(130), 0.875)
        self.assertEqual(self.controller._progress_rate(240), 0.0)

    def test_short_distance_makes_partial_slowdown_more_valuable(self) -> None:
        self.controller._deceleration_score = 0.25
        self.controller._travel_distance_since_click = 0
        short_distance_rate = self.controller._progress_rate(20)
        self.controller._travel_distance_since_click = 200
        long_distance_rate = self.controller._progress_rate(20)

        self.assertAlmostEqual(short_distance_rate, 1 + 0.75 * 0.25**0.25)
        self.assertEqual(long_distance_rate, 1.375)
        self.assertGreater(short_distance_rate, long_distance_rate)

        self.controller._deceleration_score = 0
        self.controller._travel_distance_since_click = 0
        self.assertEqual(self.controller._progress_rate(20), 1.0)

    def test_clear_direction_reversal_reduces_progress(self) -> None:
        self.controller._progress = 0.8
        self.controller._deceleration_score = 0.6
        self.controller._target_direction = QPoint(4, 0)
        self.controller._sample_delta = QPoint(-3, 1)

        self.controller._reduce_progress_on_direction_reversal()

        self.assertAlmostEqual(self.controller._progress, 0.4)
        self.assertAlmostEqual(self.controller._deceleration_score, 0.3)

    def test_distance_travelled_removes_progress_softly(self) -> None:
        self.controller._progress = 0.8
        self.controller._sample_delta = QPoint(3, 4)

        self.controller._apply_movement_penalty()

        self.assertAlmostEqual(self.controller._progress, 0.8 - 5 / 15)

    def test_only_progressive_slowdown_earns_acceleration(self) -> None:
        self.controller._target_speed = 240
        self.controller._instantaneous_speed = 0
        self.controller._update_deceleration_score(0.02)

        self.assertEqual(self.controller._deceleration_score, 0)

        self.controller._target_speed = 240
        for speed in (200, 160, 120, 80, 40):
            self.controller._instantaneous_speed = speed
            self.controller._update_deceleration_score(0.02)

        self.assertAlmostEqual(self.controller._deceleration_score, 200 / 220)

    def test_speed_rises_immediately_and_releases_over_time(self) -> None:
        position = self.key.mapToGlobal(QPoint(20, 20))

        self.controller._sample_speed(position, 1.0)
        _, speed = self.controller._sample_speed(
            position + QPoint(4, 0),
            1.01,
        )
        self.assertEqual(speed, 240)

        _, speed = self.controller._sample_speed(
            position + QPoint(4, 0),
            1.06,
        )
        self.assertAlmostEqual(speed, 120)
        _, speed = self.controller._sample_speed(
            position + QPoint(4, 0),
            1.11,
        )
        self.assertEqual(speed, 0)

    def test_motion_on_same_target_preserves_progress_and_speed(self) -> None:
        position = self.key.mapToGlobal(QPoint(20, 20))

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=self.key,
        ):
            self.controller.update_from_global_position(position, now=1.0)
            self.controller.update_from_global_position(
                position + QPoint(11, 0),
                now=1.01,
            )
            self.controller.update_from_global_position(
                position + QPoint(11, 0),
                now=1.026,
            )

        self.assertAlmostEqual(self.controller._smoothed_speed, 201.6)
        self.assertGreater(self.controller._progress, 0)
        self.assertLess(self.controller._progress, 0.03)

    def test_origin_is_treated_as_a_real_previous_position(self) -> None:
        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=self.key,
        ):
            self.controller.update_from_global_position(QPoint(0, 0), now=1.0)
            self.controller.update_from_global_position(QPoint(4, 0), now=1.02)

        self.assertAlmostEqual(self.controller._instantaneous_speed, 200)
        self.assertEqual(self.controller._progress, 0)

    def test_pointer_without_slowdown_uses_base_delay(self) -> None:
        clicks: list[bool] = []
        self.key.clicked.connect(lambda: clicks.append(True))
        position = self.key.mapToGlobal(QPoint(20, 20))

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=self.key,
        ):
            self.controller.update_from_global_position(position, now=1.0)
            self.controller.update_from_global_position(position, now=1.2)

        QTest.qWait(150)
        self.assertEqual(clicks, [True])

    def test_movement_on_same_target_does_not_restart_progress(self) -> None:
        clicks: list[bool] = []
        self.key.clicked.connect(lambda: clicks.append(True))
        position = self.key.mapToGlobal(QPoint(20, 20))
        moved_position = position + QPoint(11, 0)

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=self.key,
        ):
            self.controller.update_from_global_position(position, now=1.0)
            self.controller.update_from_global_position(position, now=1.04)
            self.controller.update_from_global_position(
                moved_position,
                now=1.09,
            )
            self.controller.update_from_global_position(
                moved_position,
                now=1.14,
            )
            self.controller.update_from_global_position(
                moved_position,
                now=1.27,
            )
            self.controller.update_from_global_position(
                moved_position,
                now=1.32,
            )

        QTest.qWait(150)
        self.assertEqual(len(clicks), 1)

    def test_entering_another_target_restarts_progress(self) -> None:
        first_position = self.key.mapToGlobal(QPoint(20, 20))
        second_position = self.other_key.mapToGlobal(QPoint(20, 20))

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            side_effect=(self.key, self.key, self.other_key),
        ):
            self.controller.update_from_global_position(first_position, now=1.0)
            self.controller.update_from_global_position(first_position, now=1.06)
            self.controller.update_from_global_position(second_position, now=1.07)

        self.assertEqual(self.controller._progress, 0)
        self.assertFalse(self.controller.indicator.isVisible())
        feedback = self.controller.indicator.cancel_feedback
        self.assertTrue(feedback.isVisible())
        QTest.qWait(300)
        self.assertFalse(feedback.isVisible())

    def test_completion_feedback_fades_in_accent_color(self) -> None:
        position = self.key.mapToGlobal(QPoint(20, 20))

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=self.key,
        ):
            self.controller.update_from_global_position(position, now=1.0)
            self.controller.update_from_global_position(position, now=1.2)

        feedback = self.controller.indicator.complete_feedback
        expected_color = feedback.palette().color(
            feedback.palette().ColorRole.Highlight,
        )
        self.assertTrue(feedback.isVisible())
        self.assertEqual(feedback.feedback_color.name(), expected_color.name())
        QTest.qWait(300)
        self.assertFalse(feedback.isVisible())

    def test_requires_dead_zone_exit_before_another_click(self) -> None:
        clicks: list[bool] = []
        self.key.clicked.connect(lambda: clicks.append(True))
        position = self.key.mapToGlobal(QPoint(20, 20))

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=self.key,
        ):
            self.controller.update_from_global_position(position, now=1.0)
            self.controller.update_from_global_position(position, now=1.2)
            QTest.qWait(150)
            self.controller.update_from_global_position(position, now=2.0)
            moved_position = position + QPoint(11, 0)
            self.controller.update_from_global_position(
                moved_position,
                now=2.1,
            )
            self.controller.update_from_global_position(
                moved_position,
                now=2.31,
            )

        QTest.qWait(150)
        self.assertEqual(len(clicks), 2)
        self.assertFalse(self.controller.indicator.isVisible())

    def test_activates_non_key_controls_in_the_same_window(self) -> None:
        button = QPushButton("Not a key", self.window)
        button.setProperty("componentType", "button")
        clicks: list[bool] = []
        button.clicked.connect(lambda: clicks.append(True))
        position = button.mapToGlobal(QPoint(1, 1))

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=button,
        ):
            self.controller.update_from_global_position(position, now=1.0)
            self.controller.update_from_global_position(position, now=1.2)

        QTest.qWait(150)
        self.assertEqual(clicks, [True])

    def test_sends_mouse_click_to_plain_window_content(self) -> None:
        events: list[QEvent.Type] = []
        target = _MouseEventRecorder(events, self.window)
        target.setGeometry(200, 10, 30, 30)
        position = target.mapToGlobal(QPoint(10, 10))

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=target,
        ):
            self.controller.update_from_global_position(position, now=1.0)
            self.controller.update_from_global_position(position, now=1.2)

        self.assertEqual(
            events,
            [QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease],
        )

    def test_high_speed_pauses_without_cancellation_feedback(self) -> None:
        position = self.key.mapToGlobal(QPoint(20, 20))

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=self.key,
        ):
            self.controller.update_from_global_position(position, now=1.0)
            self.controller.update_from_global_position(position, now=1.05)
            self.controller.update_from_global_position(
                position + QPoint(4, 0),
                now=1.06,
            )

        self.assertFalse(self.controller.indicator.isVisible())
        self.assertFalse(self.controller.indicator.cancel_feedback.isVisible())
        self.assertEqual(self.controller._progress, 0)

    def test_physical_mouse_button_suspends_and_rearms_dwell(self) -> None:
        clicks: list[bool] = []
        self.key.clicked.connect(lambda: clicks.append(True))
        position = self.key.mapToGlobal(QPoint(20, 20))

        with (
            patch(
                "axidev_osk.windows.dwell_click.QApplication.mouseButtons",
                side_effect=(Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton),
            ),
            patch(
                "axidev_osk.windows.dwell_click.QApplication.widgetAt",
                return_value=self.key,
            ),
            patch(
                "axidev_osk.windows.dwell_click.QCursor.pos",
                return_value=position,
            ),
            patch(
                "axidev_osk.windows.dwell_click.monotonic",
                return_value=1.0,
            ),
        ):
            self.controller._progress = 0.8
            self.controller._target = self.key
            self.controller.indicator.show_progress(position, 0.8)

            self.controller._poll_cursor()

            self.assertEqual(self.controller._progress, 0)
            self.assertIsNone(self.controller._target)
            self.assertFalse(self.controller.indicator.isVisible())
            self.controller._poll_cursor()

        QTest.qWait(150)
        self.assertEqual(clicks, [])
        self.assertIs(self.controller._target, self.key)
        self.assertEqual(self.controller._progress, 0)

    def test_does_not_activate_a_key_from_another_window(self) -> None:
        other_window = QWidget()
        other_key = QPushButton("Other", other_window)
        other_key.setProperty("componentType", "key")
        clicks: list[bool] = []
        other_key.clicked.connect(lambda: clicks.append(True))
        self.addCleanup(other_window.close)

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=other_key,
        ):
            self.controller.update_from_global_position(
                QPoint(500, 500),
                now=1.0,
            )
            self.controller.update_from_global_position(
                QPoint(500, 500),
                now=1.1,
            )

        self.assertEqual(clicks, [])
