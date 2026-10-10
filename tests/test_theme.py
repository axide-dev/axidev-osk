import re
import unittest

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QWidget

from axidev_osk.attachments.runtime import AttachmentRuntime
from axidev_osk.config.reader import ConfigError
from axidev_osk.python_defaults import osk
from axidev_osk.python_defaults.default_profile import build_default_config
from axidev_osk.python_defaults.theme import DEFAULT_FONT, DEFAULT_QSS
from axidev_osk.runtime.testing import make_test_context, start_test_profile
from axidev_osk.styles.theme import apply_theme
from support import FakeOverlay, RecordingBackend, build_window, qt_app


def _decode(theme: osk.Map) -> object:
    root = osk.config(
        active_profile="p",
        profiles={"p": osk.profile(theme=theme, windows=[osk.window(id="w", title="w", content=osk.box(id="r"))])},
    )
    return make_test_context(RecordingBackend()).engine.decoder().decode_root(root)


class ThemeTests(unittest.TestCase):
    def test_default_profile_theme_sets_palette_font_and_stylesheet(self) -> None:
        app = qt_app()
        previous = (app.styleSheet(), app.palette(), app.font())
        self.addCleanup(lambda: (app.setStyleSheet(previous[0]), app.setPalette(previous[1]), app.setFont(previous[2])))
        profile = make_test_context(RecordingBackend()).engine.decoder().decode_root(build_default_config())

        apply_theme(app, profile.theme)

        self.assertEqual(app.styleSheet(), DEFAULT_QSS)
        self.assertEqual(app.palette().color(QPalette.ColorRole.Window), QColor("#0B0B10"))
        self.assertEqual(app.palette().color(QPalette.ColorRole.Highlight), QColor("#E61E8C"))
        self.assertEqual(app.font().families(), DEFAULT_FONT["families"])
        self.assertEqual((app.font().pixelSize(), app.font().weight()), (14, QFont.Weight.Medium))

    def test_theme_rejects_unknown_palette_roles_and_malformed_colors(self) -> None:
        cases = {
            "unknown keys: glow": {"palette": {"glow": "#FFFFFF"}},
            "must be a color": {"palette": {"window": "black"}},
            "must be one of": {"font": {"families": ["Inter"], "pixel_size": 14, "weight": "heavy"}},
        }
        for message, theme in cases.items():
            with self.subTest(message), self.assertRaisesRegex(ConfigError, message):
                _decode(theme)

    def test_every_name_and_property_the_default_stylesheet_targets_exists_on_the_keyboard(self) -> None:
        qt_app()
        context = make_test_context(RecordingBackend())
        attachments = AttachmentRuntime(context.dispatcher, context.engine.profile, window_lookup=lambda _id: None)
        profile = start_test_profile(context, build_default_config())
        attachments.start(profile)
        window = build_window(
            self,
            profile.window("keyboard"),
            context,
            attachments=attachments.for_window("keyboard"),
            overlay=FakeOverlay(uses_custom_chrome=True),
        )
        widgets = [window, *window.findChildren(QWidget)]
        object_names = {widget.objectName() for widget in widgets}
        properties = {bytes(name.data()).decode() for widget in widgets for name in widget.dynamicPropertyNames()}
        selectors = "".join(re.findall(r"([^{}]+)\{", DEFAULT_QSS))

        self.assertEqual(set(re.findall(r"#([A-Za-z_][\w-]*)", selectors)) - object_names, set())
        self.assertEqual(set(re.findall(r"\[([A-Za-z_]\w*)", selectors)) - properties, set())

if __name__ == "__main__":
    unittest.main()
