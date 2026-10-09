"""Apply a profile's theme to the application: Qt palette, font, and stylesheet.

The engine owns no colors or font families. It only maps the profile's names
onto Qt and keeps rendering-quality font settings.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from ..config.profile import ThemeConfig


def qt_enum_name(name: str) -> str:
    """Turn a profile name such as ``alternate_base`` into Qt's ``AlternateBase``."""

    return "".join(part.capitalize() for part in name.split("_"))


def apply_theme(app: QApplication, theme: ThemeConfig) -> None:
    """Apply the profile's palette roles, font, and stylesheet."""

    palette = QPalette(app.palette())
    for role, color in theme.palette.items():
        palette.setColor(getattr(QPalette.ColorRole, qt_enum_name(role)), QColor(color))
    app.setPalette(palette)
    if theme.font is not None:
        font = QFont()
        font.setFamilies(list(theme.font.families))
        font.setPixelSize(theme.font.pixel_size)
        font.setWeight(getattr(QFont.Weight, qt_enum_name(theme.font.weight)))
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
        font.setKerning(True)
        app.setFont(font)
    app.setStyleSheet(theme.qss)
