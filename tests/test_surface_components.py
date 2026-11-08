from __future__ import annotations

import unittest

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

from axidev_osk.components.pointer_locator import PointerLocator, install_pointer_locator
from axidev_osk.config.models import PointerLocatorConfig
from axidev_osk.windows.surface import RootSurface
from support import qt_app


def _config() -> PointerLocatorConfig:
    return PointerLocatorConfig(
        id="test-pointer-locator",
        radius_percent=30,
        maximum_opacity_percent=60,
        radius_standard_deviations=3,
        gap_color="#242424",
    )


def _surface_with_content() -> tuple[RootSurface, QWidget]:
    surface = RootSurface()
    surface.resize(300, 160)
    content = QWidget(surface)
    content.setGeometry(surface.rect())
    content.show()
    return surface, content


class RootSurfaceComponentTests(unittest.TestCase):
    def setUp(self) -> None:
        qt_app()

    def test_background_component_is_fitted_below_surface_content(self) -> None:
        surface, content = _surface_with_content()
        background = QWidget()
        background.show()

        surface.install_background_component(background)

        self.assertIs(background.parentWidget(), surface)
        self.assertEqual(background.geometry(), surface.rect())
        self.assertIs(surface.childAt(QPoint(20, 20)), content)

    def test_background_components_keep_install_order_below_content(self) -> None:
        surface, content = _surface_with_content()
        first = QWidget()
        second = QWidget()

        surface.install_background_component(first)
        surface.install_background_component(second)
        surface.show()
        self.addCleanup(surface.close)
        surface.resize(400, 220)

        self.assertEqual(surface.children(), [first, second, content])
        self.assertEqual(first.geometry(), surface.rect())
        self.assertEqual(second.geometry(), surface.rect())

    def test_pointer_locator_installs_as_background_component(self) -> None:
        surface, content = _surface_with_content()

        locator = install_pointer_locator(surface, _config())

        self.assertIsInstance(locator, PointerLocator)
        self.assertIs(surface.findChild(PointerLocator, "pointerLocator"), locator)
        self.assertIs(locator.parentWidget(), surface)
        self.assertEqual(locator.property("componentId"), _config().id)
        self.assertTrue(surface.property("pointerLocatorEnabled"))
        self.assertEqual(surface.children(), [locator, content])


if __name__ == "__main__":
    unittest.main()
