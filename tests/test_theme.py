import unittest

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from axidev_osk.python_defaults.theme import DEFAULT_QSS
from axidev_osk.styles.theme import BODY_FONT_FAMILIES, apply_theme, build_theme_palette


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication)
    return app


class ThemeTests(unittest.TestCase):
    def test_apply_theme_sets_profile_stylesheet_engine_palette_and_font(self) -> None:
        app = _app()
        previous = (app.styleSheet(), app.palette(), app.font())
        self.addCleanup(lambda: (app.setStyleSheet(previous[0]), app.setPalette(previous[1]), app.setFont(previous[2])))

        apply_theme(app, qss="QPushButton { color: red; }")

        palette = build_theme_palette()
        self.assertEqual(app.styleSheet(), "QPushButton { color: red; }")
        self.assertEqual(app.palette().color(QPalette.ColorRole.Window), palette.shell_fill)
        self.assertEqual(app.palette().color(QPalette.ColorRole.Highlight), palette.active_edge)
        self.assertEqual(app.font().families(), BODY_FONT_FAMILIES)
        self.assertEqual(app.font().pixelSize(), 14)

    def test_default_stylesheet_targets_the_keyboard_and_interaction_states(self) -> None:
        self.assertIn("QWidget#keyboard {", DEFAULT_QSS)
        self.assertIn('QPushButton[interactionState="pressed"]', DEFAULT_QSS)
        self.assertIn('QPushButton[interactionState="latched_pressed"]', DEFAULT_QSS)

    def test_pointer_locator_surface_uses_translucent_button_backgrounds(self) -> None:
        self.assertIn('QWidget[pointerLocatorEnabled="true"] QPushButton', DEFAULT_QSS)
        self.assertIn("rgba(18, 18, 26, 153)", DEFAULT_QSS)
        self.assertIn("rgba(16, 16, 24, 153)", DEFAULT_QSS)


if __name__ == "__main__":
    unittest.main()
