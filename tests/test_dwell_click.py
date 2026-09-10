from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.config.models import DwellClickConfig
from axidev_osk.windows.dwell_click import DwellClickController


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class DwellClickConfigTests(unittest.TestCase):
    def test_default_keyboard_enables_dwell_click(self) -> None:
        config = build_default_app_config().windows[0].dwell_click

        self.assertTrue(config.enabled)
        self.assertEqual(config.delay_ms, 200)
        self.assertEqual(config.dead_zone_px, 10)
        self.assertEqual(config.full_speed_px_s, 20)
        self.assertEqual(config.stop_speed_px_s, 240)

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
            ),
        )
        self.addCleanup(self.window.close)

    def test_activates_exact_key_under_current_pointer(self) -> None:
        clicks: list[str] = []
        self.key.clicked.connect(lambda: clicks.append("A"))
        self.other_key.clicked.connect(lambda: clicks.append("B"))
        first_position = self.key.mapToGlobal(QPoint(20, 20))
        current_position = self.key.mapToGlobal(QPoint(24, 20))

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

        self.assertEqual(clicks, ["B"])

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
                now=1.1,
            )

        indicator = self.controller.indicator
        self.assertTrue(indicator.isVisible())
        self.assertAlmostEqual(indicator.progress, 0.5)
        expected_color = indicator.palette().color(
            indicator.palette().ColorRole.Highlight,
        )
        self.assertEqual(
            indicator.progress_color.name(),
            expected_color.name(),
        )
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
        self.assertEqual(self.controller._progress_rate(130), 0.5)
        self.assertEqual(self.controller._progress_rate(240), 0.0)

    def test_origin_is_treated_as_a_real_previous_position(self) -> None:
        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=self.key,
        ):
            self.controller.update_from_global_position(QPoint(0, 0), now=1.0)
            self.controller.update_from_global_position(QPoint(4, 0), now=1.02)

        expected_rate = (240 - 200) / (240 - 20)
        expected_progress = 20 / 200 * expected_rate
        self.assertAlmostEqual(self.controller._progress, expected_progress)

    def test_clicks_at_exact_configured_delay(self) -> None:
        clicks: list[bool] = []
        self.key.clicked.connect(lambda: clicks.append(True))
        position = self.key.mapToGlobal(QPoint(20, 20))

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=self.key,
        ):
            self.controller.update_from_global_position(position, now=1.0)
            self.controller.update_from_global_position(position, now=1.1)
            self.controller.update_from_global_position(position, now=1.2)

        self.assertEqual(clicks, [True])

    def test_movement_outside_dead_zone_restarts_delay(self) -> None:
        clicks: list[bool] = []
        self.key.clicked.connect(lambda: clicks.append(True))
        position = self.key.mapToGlobal(QPoint(20, 20))
        moved_position = position + QPoint(11, 0)

        with patch(
            "axidev_osk.windows.dwell_click.QApplication.widgetAt",
            return_value=self.key,
        ):
            self.controller.update_from_global_position(position, now=1.0)
            self.controller.update_from_global_position(
                moved_position,
                now=1.09,
            )
            self.assertFalse(self.controller.indicator.isVisible())
            self.controller.update_from_global_position(
                moved_position,
                now=1.1,
            )
            self.assertEqual(clicks, [])
            self.assertTrue(self.controller.indicator.isVisible())
            self.controller.update_from_global_position(
                moved_position,
                now=1.3,
            )

        self.assertEqual(len(clicks), 1)

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

        self.assertEqual(len(clicks), 2)
        self.assertFalse(self.controller.indicator.isVisible())

    def test_does_not_activate_non_key_controls(self) -> None:
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
            self.controller.update_from_global_position(position, now=1.1)

        self.assertEqual(clicks, [])

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
