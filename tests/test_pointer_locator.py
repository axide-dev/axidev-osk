from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from axidev_osk.components.pointer_locator import (
    PointerLocator,
    _build_proximity_graph,
    build_component_palette,
    gaussian_opacity,
)
from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.config.models import PointerLocatorConfig


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _locator_config(**overrides: object) -> PointerLocatorConfig:
    values = {
        "id": "component:test-pointer-locator",
        "radius_percent": 30,
        "maximum_opacity_percent": 60,
        "radius_standard_deviations": 3,
    }
    values.update(overrides)
    return PointerLocatorConfig(**values)


class PointerLocatorPaletteTests(unittest.TestCase):
    def test_default_keyboard_uses_component_aware_locator(self) -> None:
        background_components = build_default_app_config().windows[0].surface.background_components

        self.assertEqual(len(background_components), 1)
        config = background_components[0]
        self.assertIsInstance(config, PointerLocatorConfig)
        self.assertEqual(config.radius_percent, 30)
        self.assertEqual(config.maximum_opacity_percent, 60)
        self.assertEqual(config.radius_standard_deviations, 3)

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

    def test_component_palette_is_deterministic_distinct_and_vivid(self) -> None:
        rectangles = tuple(QRect(column * 52, row * 52, 48, 48) for row in range(3) for column in range(4))

        first = build_component_palette(rectangles)
        second = build_component_palette(rectangles)
        graph = _build_proximity_graph(rectangles)

        self.assertEqual(first, second)
        for color in first:
            self.assertAlmostEqual(color.hsvSaturationF(), 1.0)
            self.assertGreaterEqual(color.valueF(), 0.69)
        for index, neighbors in enumerate(graph):
            for neighbor in neighbors:
                self.assertNotEqual(first[index], first[neighbor])

        for row in range(3):
            for column in range(4):
                hue = first[row * 4 + column].hsvHueF() * 360
                if (row + column) % 2 == 0:
                    self.assertTrue(hue >= 329.9 or hue <= 60.1)
                else:
                    self.assertTrue(149.9 <= hue <= 270.1)

    def test_nearby_components_receive_different_colors(self) -> None:
        rectangles = (
            QRect(0, 0, 48, 48),
            QRect(52, 0, 48, 48),
            QRect(104, 0, 48, 48),
        )

        colors = build_component_palette(rectangles)

        self.assertEqual(len({color.name() for color in colors}), 3)

    def test_distant_components_still_alternate_temperature(self) -> None:
        colors = build_component_palette((QRect(0, 0, 48, 48), QRect(1000, 0, 48, 48)))

        first_hue = colors[0].hsvHueF() * 360
        second_hue = colors[1].hsvHueF() * 360
        self.assertTrue(first_hue >= 329.9 or first_hue <= 60.1)
        self.assertTrue(149.9 <= second_hue <= 270.1)


class PointerLocatorWidgetTests(unittest.TestCase):
    def test_glow_tracks_pointer_inside_host_and_hides_outside(self) -> None:
        app = _app()
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

    def test_glow_uses_button_colors_and_a_muted_gap_color(self) -> None:
        app = _app()
        host = QWidget()
        host.resize(220, 80)
        left = QPushButton("Left", host)
        left.setProperty("componentType", "key")
        left.setGeometry(10, 10, 90, 60)
        right = QPushButton("Right", host)
        right.setProperty("componentType", "key")
        right.setGeometry(120, 10, 90, 60)
        host.show()
        app.processEvents()
        locator = PointerLocator(_locator_config(), host)
        self.addCleanup(host.close)

        locator.update_from_global_position(host.mapToGlobal(QPoint(20, 40)))
        left_color = locator.current_color
        locator.update_from_global_position(host.mapToGlobal(QPoint(90, 40)))
        self.assertEqual(locator.current_color, left_color)

        locator.update_from_global_position(host.mapToGlobal(QPoint(190, 40)))
        self.assertNotEqual(locator.current_color, left_color)

        right.hide()
        app.processEvents()
        locator.update_from_global_position(host.mapToGlobal(QPoint(190, 40)))
        self.assertLess(locator.current_color.hsvSaturationF(), 0.1)

        locator.update_from_global_position(host.mapToGlobal(QPoint(105, 40)))
        self.assertNotEqual(locator.current_color, left_color)
        self.assertLess(locator.current_color.hsvSaturationF(), 0.1)
        self.assertLess(locator.current_color.valueF(), 0.2)

    def test_stale_wayland_position_cannot_restore_glow_after_leave(self) -> None:
        app = _app()
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
