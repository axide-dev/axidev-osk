import unittest

from axidev_osk.styles.theme import build_stylesheet


class PointerLocatorThemeTests(unittest.TestCase):
    def test_pointer_locator_surface_uses_translucent_button_backgrounds(self) -> None:
        stylesheet = build_stylesheet()

        self.assertIn('QWidget[pointerLocatorEnabled="true"] QPushButton', stylesheet)
        self.assertIn("rgba(18, 18, 26, 153)", stylesheet)
        self.assertIn("rgba(16, 16, 24, 153)", stylesheet)
