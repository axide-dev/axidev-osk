"""Application theme palette, font, and stylesheet helpers."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

BODY_FONT_FAMILIES = [
    "Segoe UI Variable Text",
    "Segoe UI Variable",
    "Inter",
    "Segoe UI",
    "SF Pro Text",
    "Ubuntu",
    "Noto Sans",
    "Cantarell",
    "Arial",
]


@dataclass(frozen=True)
class ThemePalette:
    """Qt colors used by the application stylesheet.

    Attributes:
        shell_fill: Main overlay background color.
        shell_edge: Border color for shell surfaces.
        shell_bar: Custom chrome/title bar background color.
        shell_bar_hover: Hover color for chrome controls.
        accent: Primary brand/accent color.
        key_fill: Default key background color.
        key_hover: Key hover background color.
        key_pressed: Key pressed background color.
        key_edge: Key border color.
        active_fill: Active or latched key background color.
        active_edge: Active or latched key border color.
        text: Primary text color.
        disabled_text: Muted text color.
        disabled_fill: Disabled key background color.
        disabled_edge: Disabled key border color.
    """

    shell_fill: QColor
    shell_edge: QColor
    shell_bar: QColor
    shell_bar_hover: QColor
    accent: QColor
    key_fill: QColor
    key_hover: QColor
    key_pressed: QColor
    key_edge: QColor
    active_fill: QColor
    active_edge: QColor
    text: QColor
    disabled_text: QColor
    disabled_fill: QColor
    disabled_edge: QColor


def build_theme_palette() -> ThemePalette:
    """Return the default application color palette."""

    return ThemePalette(
        shell_fill=QColor("#0B0B10"),
        shell_edge=QColor("#242433"),
        shell_bar=QColor("#12121A"),
        shell_bar_hover=QColor("#171723"),
        accent=QColor("#E61E8C"),
        key_fill=QColor("#151520"),
        key_hover=QColor("#1D1A27"),
        key_pressed=QColor("#101018"),
        key_edge=QColor("#2E2A3F"),
        active_fill=QColor("#2A1421"),
        active_edge=QColor("#E61E8C"),
        text=QColor("#F5F6FA"),
        disabled_text=QColor("#B9BBC7"),
        disabled_fill=QColor("#0F0F16"),
        disabled_edge=QColor("#242433"),
    )


def _rgba(color: QColor, alpha: int) -> str:
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


def build_application_font() -> QFont:
    """Return the default application font stack and sizing."""

    font = QFont()
    font.setFamilies(BODY_FONT_FAMILIES)
    font.setPixelSize(14)
    font.setWeight(QFont.Weight.Medium)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality
    )
    font.setKerning(True)
    return font


def apply_theme(app: QApplication, *, qss: str) -> None:
    """Apply the engine palette and font, plus the active profile's stylesheet."""

    palette = build_theme_palette()
    qt_palette = QPalette(app.palette())
    qt_palette.setColor(QPalette.ColorRole.Window, palette.shell_fill)
    qt_palette.setColor(QPalette.ColorRole.Base, palette.shell_fill)
    qt_palette.setColor(QPalette.ColorRole.AlternateBase, palette.shell_bar)
    qt_palette.setColor(QPalette.ColorRole.WindowText, palette.text)
    qt_palette.setColor(QPalette.ColorRole.Text, palette.text)
    qt_palette.setColor(QPalette.ColorRole.Button, palette.key_fill)
    qt_palette.setColor(QPalette.ColorRole.ButtonText, palette.text)
    qt_palette.setColor(QPalette.ColorRole.Highlight, palette.active_edge)
    qt_palette.setColor(QPalette.ColorRole.HighlightedText, palette.shell_fill)
    qt_palette.setColor(QPalette.ColorRole.PlaceholderText, palette.disabled_text)
    app.setPalette(qt_palette)
    app.setFont(build_application_font())
    app.setStyleSheet(qss)
