from __future__ import annotations

import unittest
from unittest.mock import Mock

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QWidget

from axidev_osk.components import register_components
from axidev_osk.components.pointer_locator import PointerLocator
from axidev_osk.config.models import PointerLocatorConfig, SurfaceConfig
from axidev_osk.runtime.registries import ComponentRegistry
from axidev_osk.windows.surface import RootSurface, build_surface


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _config() -> PointerLocatorConfig:
    return PointerLocatorConfig(
        id="component:test-pointer-locator",
        radius_percent=30,
        maximum_opacity_percent=60,
        radius_standard_deviations=3,
    )


class RootSurfaceComponentTests(unittest.TestCase):
    def test_surface_rejects_duplicate_ids_across_background_and_content(self) -> None:
        config = _config()

        with self.assertRaisesRegex(ValueError, "Duplicate config IDs"):
            SurfaceConfig(
                id="surface:test",
                components=(config,),
                background_components=(config,),
            )

    def test_background_component_is_fitted_below_surface_content(self) -> None:
        _app()
        surface = RootSurface()
        surface.resize(300, 160)
        content = QWidget(surface)
        content.setGeometry(surface.rect())
        content.show()
        background = QWidget()
        background.show()

        surface.install_background_component(background)

        self.assertIs(background.parentWidget(), surface)
        self.assertEqual(background.geometry(), surface.rect())
        self.assertIs(surface.childAt(QPoint(20, 20)), content)

    def test_surface_builds_pointer_locator_through_component_registry(self) -> None:
        registry = ComponentRegistry()
        register_components(registry)
        context = Mock(components=registry)
        config = SurfaceConfig(
            id="surface:test",
            components=(),
            background_components=(_config(),),
        )

        surface = build_surface(config, context)
        locator = surface.findChild(PointerLocator, "pointerLocator")

        self.assertIsNotNone(locator)
        self.assertIs(locator.parentWidget(), surface)
        self.assertEqual(locator.property("componentId"), _config().id)
