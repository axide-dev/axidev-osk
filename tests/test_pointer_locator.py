from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QWidget

from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.config.models import PointerLocatorConfig
from axidev_osk.windows.pointer_locator import (
    PointerLocator,
    build_pointer_palette,
    gaussian_opacity,
    interpolate_pointer_color,
)


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _locator_config(**overrides: object) -> PointerLocatorConfig:
    values = {
        "id": "decoration:test-pointer-locator",
        "rows": 4,
        "columns": 4,
        "radius_percent": 30,
        "maximum_opacity_percent": 60,
        "radius_standard_deviations": 3,
    }
    values.update(overrides)
    return PointerLocatorConfig(**values)


class PointerLocatorPaletteTests(unittest.TestCase):
    def test_default_keyboard_uses_four_by_four_locator(self) -> None:
        decorations = build_default_app_config().windows[0].decorations

        self.assertEqual(len(decorations), 1)
        config = decorations[0]
        self.assertIsInstance(config, PointerLocatorConfig)
        self.assertEqual(config.rows, 4)
        self.assertEqual(config.columns, 4)
        self.assertEqual(config.radius_percent, 30)
        self.assertEqual(config.maximum_opacity_percent, 60)
        self.assertEqual(config.radius_standard_deviations, 3)

    def test_config_rejects_non_positive_dimensions(self) -> None:
        for rows, columns in ((0, 4), (4, 0), (-1, 4), (4, -1)):
            with self.subTest(rows=rows, columns=columns):
                with self.assertRaisesRegex(ValueError, "rows and columns must be positive"):
                    _locator_config(rows=rows, columns=columns)

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

    def test_four_by_four_palette_is_deterministic_and_unique(self) -> None:
        first = build_pointer_palette(4, 4)
        second = build_pointer_palette(4, 4)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)
        self.assertEqual(len({color.name() for color in first}), 16)

    def test_four_by_four_palette_separates_all_orthogonal_neighbors(self) -> None:
        palette = build_pointer_palette(4, 4)

        for row in range(4):
            for column in range(4):
                index = row * 4 + column
                neighbor_indexes = []
                if column < 3:
                    neighbor_indexes.append(index + 1)
                if row < 3:
                    neighbor_indexes.append(index + 4)
                for neighbor_index in neighbor_indexes:
                    first_hue = palette[index].hsvHueF() * 360
                    second_hue = palette[neighbor_index].hsvHueF() * 360
                    distance = abs(first_hue - second_hue)
                    distance = min(distance, 360 - distance)
                    self.assertGreaterEqual(distance, 89.9)

    def test_region_centers_keep_their_exact_palette_colors(self) -> None:
        rows = 4
        columns = 4
        width = 800
        height = 400
        palette = build_pointer_palette(rows, columns)

        for row in range(rows):
            for column in range(columns):
                with self.subTest(row=row, column=column):
                    color = interpolate_pointer_color(
                        palette,
                        rows=rows,
                        columns=columns,
                        x=(column + 0.5) * width / columns,
                        y=(row + 0.5) * height / rows,
                        width=width,
                        height=height,
                    )
                    self.assertEqual(color, palette[row * columns + column])

    def test_position_uses_the_same_color_after_grid_stretching(self) -> None:
        palette = build_pointer_palette(4, 4)

        original = interpolate_pointer_color(
            palette,
            rows=4,
            columns=4,
            x=312.5,
            y=162.5,
            width=500,
            height=250,
        )
        stretched = interpolate_pointer_color(
            palette,
            rows=4,
            columns=4,
            x=625,
            y=325,
            width=1000,
            height=500,
        )

        self.assertEqual(original, stretched)

    def test_midpoint_blends_neighboring_colors(self) -> None:
        palette = (QColor("#ff0000"), QColor("#0000ff"))

        color = interpolate_pointer_color(
            palette,
            rows=1,
            columns=2,
            x=50,
            y=25,
            width=100,
            height=50,
        )

        self.assertAlmostEqual(color.redF(), 0.5, delta=0.01)
        self.assertAlmostEqual(color.greenF(), 0.0, delta=0.01)
        self.assertAlmostEqual(color.blueF(), 0.5, delta=0.01)


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

        image = QImage(locator.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        locator.render(image)
        self.assertAlmostEqual(image.pixelColor(200, 100).alphaF(), 0.6, delta=0.02)
        self.assertEqual(image.pixelColor(270, 100).alpha(), 0)

        locator.update_from_global_position(host.mapToGlobal(QPoint(500, 100)))

        self.assertFalse(locator.isVisible())

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
        with patch("axidev_osk.windows.pointer_locator.QCursor.pos", return_value=inside):
            locator._poll_cursor()
            self.assertFalse(locator.isVisible())
            app.sendEvent(host, QEvent(QEvent.Type.Enter))

        self.assertTrue(locator.isVisible())
