from __future__ import annotations

import unittest
from unittest.mock import Mock

from PySide6.QtCore import QObject, QPoint
from PySide6.QtWidgets import QApplication, QWidget

from axidev_osk.config.models import PointerLocatorConfig
from axidev_osk.runtime.registries import SurfaceDecorationRegistry
from axidev_osk.windows.pointer_locator import attach_pointer_locator
from axidev_osk.windows.surface import RootSurface


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _config() -> PointerLocatorConfig:
    return PointerLocatorConfig(
        id="decoration:test-pointer-locator",
        rows=4,
        columns=4,
        radius_percent=30,
        maximum_opacity_percent=60,
        radius_standard_deviations=3,
    )


class SurfaceDecorationRegistryTests(unittest.TestCase):
    def test_registry_attaches_decorations_by_kind_in_order(self) -> None:
        registry = SurfaceDecorationRegistry()
        first = QObject()
        second = QObject()
        builder = Mock(side_effect=(first, second))
        registry.register("pointer-locator", builder)
        surface = QWidget()
        context = Mock()

        attached = registry.attach_all((_config(), _config()), surface, context)

        self.assertEqual(attached, (first, second))
        self.assertEqual(builder.call_count, 2)

    def test_registry_rejects_missing_decoration_kind(self) -> None:
        registry = SurfaceDecorationRegistry()

        with self.assertRaisesRegex(ValueError, "No surface decoration registered"):
            registry.attach(_config(), QWidget(), Mock())


class RootSurfaceDecorationTests(unittest.TestCase):
    def test_background_decoration_is_fitted_below_surface_content(self) -> None:
        _app()
        surface = RootSurface()
        surface.resize(300, 160)
        content = QWidget(surface)
        content.setGeometry(surface.rect())
        content.show()
        decoration = QWidget()
        decoration.show()

        surface.install_background_decoration(decoration)

        self.assertIs(decoration.parentWidget(), surface)
        self.assertEqual(decoration.geometry(), surface.rect())
        self.assertIs(surface.childAt(QPoint(20, 20)), content)

    def test_incompatible_surface_warns_and_skips_pointer_locator(self) -> None:
        surface = QWidget()
        surface.setProperty("componentId", "surface:incompatible")

        with self.assertLogs("axidev_osk.windows.pointer_locator", level="WARNING") as logs:
            attached = attach_pointer_locator(_config(), surface, Mock())

        self.assertIsNone(attached)
        self.assertIn("decoration:test-pointer-locator", logs.output[0])
        self.assertIn("surface:incompatible", logs.output[0])
