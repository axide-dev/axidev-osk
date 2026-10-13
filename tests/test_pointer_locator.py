from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QImage, QRegion
from PySide6.QtWidgets import QPushButton, QWidget

from axidev_osk.components.pointer_locator import PointerLocator, gaussian_opacity
from axidev_osk.config.models import PointerLocatorConfig
from support import qt_app


def _locator_config(**overrides: object) -> PointerLocatorConfig:
    values = {
        "id": "component:test-pointer-locator",
        "radius_percent": 30,
        "maximum_opacity_percent": 60,
        "radius_standard_deviations": 3,
        "gap_color": "#242424",
    }
    values.update(overrides)
    return PointerLocatorConfig(**values)


class PointerLocatorPaletteTests(unittest.TestCase):
    def test_config_rejects_radius_outside_percentage_bounds(self) -> None:
        for radius_percent in (0, -1, 100.1, float("nan")):
            with self.subTest(radius_percent=radius_percent):
                with self.assertRaisesRegex(ValueError, "radius percent"):
                    _locator_config(radius_percent=radius_percent)

    def test_config_rejects_invalid_gaussian_values(self) -> None:
        invalid_values = (
            {"maximum_opacity_percent": 0, "radius_standard_deviations": 3},
            {"maximum_opacity_percent": 100.1, "radius_standard_deviations": 3},
            {"maximum_opacity_percent": 60, "radius_standard_deviations": 0},
            {"maximum_opacity_percent": 60, "radius_standard_deviations": float("nan")},
        )
        for values in invalid_values:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    _locator_config(**values)

    def test_config_rejects_non_finite_or_tiny_standard_deviation_count(self) -> None:
        for value in (float("inf"), float("nan"), 0.099):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "finite and at least 0.1"):
                    _locator_config(radius_standard_deviations=value)

    def test_gaussian_opacity_has_configured_peak_and_transparent_edge(self) -> None:
        center = gaussian_opacity(
            0,
            maximum_opacity=0.6,
            radius_standard_deviations=3,
        )
        halfway = gaussian_opacity(
            0.5,
            maximum_opacity=0.6,
            radius_standard_deviations=3,
        )
        edge = gaussian_opacity(
            1,
            maximum_opacity=0.6,
            radius_standard_deviations=3,
        )

        self.assertAlmostEqual(center, 0.6)
        self.assertAlmostEqual(halfway, 0.19, delta=0.01)
        self.assertEqual(edge, 0)


class PointerLocatorWidgetTests(unittest.TestCase):
    def test_glow_tracks_pointer_inside_host_and_hides_outside(self) -> None:
        app = qt_app()
        host = QWidget()
        host.resize(400, 200)
        host.show()
        app.processEvents()
        locator = PointerLocator(
            _locator_config(),
            host,
        )
        self.addCleanup(host.close)

        locator.update_from_global_position(host.mapToGlobal(QPoint(200, 100)))

        self.assertTrue(locator.isVisible())
        self.assertEqual(locator.geometry(), host.rect())
        self.assertEqual(locator.radius, 60)
        self.assertTrue(locator.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertIsNone(host.graphicsEffect())

        image = QImage(locator.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        locator.render(image)
        self.assertAlmostEqual(image.pixelColor(200, 100).alphaF(), 0.6, delta=0.02)
        self.assertEqual(image.pixelColor(270, 100).alpha(), 0)

        locator.update_from_global_position(host.mapToGlobal(QPoint(500, 100)))

        self.assertFalse(locator.isVisible())

    def test_glow_takes_each_widgets_locator_color_and_the_gap_color_elsewhere(self) -> None:
        app = qt_app()
        host = QWidget()
        host.resize(220, 80)
        left = QPushButton("Left", host)
        left.setProperty("locatorColor", "#ff0000")
        left.setGeometry(10, 10, 90, 60)
        right = QPushButton("Right", host)
        right.setProperty("locatorColor", "#0000ff")
        right.setGeometry(120, 10, 90, 60)
        host.show()
        app.processEvents()
        locator = PointerLocator(_locator_config(), host)
        self.addCleanup(host.close)

        locator.update_from_global_position(host.mapToGlobal(QPoint(20, 40)))
        self.assertEqual(locator.current_color.name(), "#ff0000")
        locator.update_from_global_position(host.mapToGlobal(QPoint(190, 40)))
        self.assertEqual(locator.current_color.name(), "#0000ff")
        locator.update_from_global_position(host.mapToGlobal(QPoint(105, 40)))
        self.assertEqual(locator.current_color.name(), "#242424")

        right.hide()
        app.processEvents()
        locator.update_from_global_position(host.mapToGlobal(QPoint(190, 40)))
        self.assertEqual(locator.current_color.name(), "#242424")

    def test_a_shaped_widget_glows_only_inside_its_shape(self) -> None:
        app = qt_app()
        host = QWidget()
        host.resize(220, 80)
        below = QPushButton("Below", host)
        below.setProperty("locatorColor", "#ff0000")
        below.setGeometry(10, 10, 120, 60)
        above = QPushButton("Above", host)
        above.setProperty("locatorColor", "#0000ff")
        above.setGeometry(60, 10, 120, 60)
        # Only the left half of the upper button is part of its shape.
        above.setMask(QRegion(0, 0, 60, 60))
        host.show()
        app.processEvents()
        locator = PointerLocator(_locator_config(), host)
        self.addCleanup(host.close)

        locator.update_from_global_position(host.mapToGlobal(QPoint(100, 40)))
        self.assertEqual(locator.current_color.name(), "#0000ff")
        locator.update_from_global_position(host.mapToGlobal(QPoint(150, 40)))
        self.assertEqual(locator.current_color.name(), "#242424")
        locator.update_from_global_position(host.mapToGlobal(QPoint(40, 40)))
        self.assertEqual(locator.current_color.name(), "#ff0000")

    def test_stale_wayland_position_cannot_restore_glow_after_leave(self) -> None:
        app = qt_app()
        host = QWidget()
        host.resize(400, 200)
        host.show()
        app.processEvents()
        locator = PointerLocator(
            _locator_config(),
            host,
        )
        self.addCleanup(host.close)
        inside = host.mapToGlobal(QPoint(200, 100))
        locator.update_from_global_position(inside)
        self.assertTrue(locator.isVisible())

        app.sendEvent(host, QEvent(QEvent.Type.Leave))
        with patch("axidev_osk.components.pointer_locator.QCursor.pos", return_value=inside):
            locator._poll_cursor()
            self.assertFalse(locator.isVisible())
            self.assertFalse(locator._timer.isActive())
            app.sendEvent(host, QEvent(QEvent.Type.Enter))

        self.assertTrue(locator.isVisible())
        self.assertTrue(locator._timer.isActive())
