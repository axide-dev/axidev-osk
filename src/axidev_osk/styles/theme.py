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


def apply_theme(app: QApplication) -> None:
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
    app.setStyleSheet(build_stylesheet())


def build_stylesheet() -> str:
    palette = build_theme_palette()
    shell_fill = palette.shell_fill.name()
    shell_edge = palette.shell_edge.name()
    shell_bar = palette.shell_bar.name()
    shell_bar_hover = palette.shell_bar_hover.name()
    accent = palette.accent.name()
    accent_wash = _rgba(palette.accent, 32)
    accent_wash_hover = _rgba(palette.accent, 48)
    accent_edge = _rgba(palette.accent, 110)
    accent_glow = _rgba(palette.accent, 72)
    key_fill = palette.key_fill.name()
    key_hover = palette.key_hover.name()
    key_pressed = palette.key_pressed.name()
    key_edge = palette.key_edge.name()
    active_fill = palette.active_fill.name()
    active_edge = palette.active_edge.name()
    text = palette.text.name()
    disabled_text = palette.disabled_text.name()
    disabled_fill = palette.disabled_fill.name()
    disabled_edge = palette.disabled_edge.name()

    return f"""
        QMainWindow {{
            background: transparent;
        }}
        QDialog,
        QMessageBox {{
            background-color: {shell_fill};
        }}
        QMessageBox {{
            border: 1px solid {shell_edge};
            border-radius: 14px;
        }}
        QMessageBox QWidget {{
            background-color: transparent;
        }}
        QWidget {{
            color: {text};
            font-size: 14px;
        }}
        QWidget#rootSurface {{
            background-color: qlineargradient(
                x1: 0,
                y1: 0,
                x2: 1,
                y2: 1,
                stop: 0 {shell_fill},
                stop: 0.74 {shell_fill},
                stop: 1 {shell_bar}
            );
            border: 1px solid {shell_edge};
            border-radius: 14px;
        }}
        QFrame#layerShellTitleBar {{
            background-color: qlineargradient(
                x1: 0,
                y1: 0,
                x2: 1,
                y2: 1,
                stop: 0 {shell_bar},
                stop: 0.8 {shell_bar},
                stop: 1 {accent_wash}
            );
            border: 1px solid {shell_edge};
            border-radius: 10px;
        }}
        QFrame#layerShellTitleBar:hover {{
            background-color: qlineargradient(
                x1: 0,
                y1: 0,
                x2: 1,
                y2: 1,
                stop: 0 {shell_bar_hover},
                stop: 0.76 {shell_bar_hover},
                stop: 1 {accent_wash_hover}
            );
        }}
        QLabel#layerShellTitleLabel {{
            color: {text};
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}
        QPushButton#layerShellCloseButton {{
            background-color: {key_fill};
            border: 1px solid {key_edge};
            border-radius: 10px;
            padding: 0px;
            font-size: 13px;
            font-weight: 700;
            min-width: 28px;
            max-width: 28px;
        }}
        QPushButton#layerShellCloseButton:hover {{
            background-color: {accent_wash};
            border-color: {accent_edge};
        }}
        QPushButton#layerShellCloseButton:pressed {{
            background-color: {active_fill};
            border-color: {active_edge};
        }}
        QLabel#statusLabel {{
            color: {disabled_text};
            font-size: 13px;
        }}
        QFrame#layerShellResizeHandle {{
            background-color: qlineargradient(
                x1: 0,
                y1: 1,
                x2: 1,
                y2: 0,
                stop: 0 {shell_bar},
                stop: 0.45 {shell_bar},
                stop: 1 {accent_wash}
            );
            border: 1px solid {key_edge};
            border-radius: 8px;
        }}
        QFrame#keyboard {{
            background: transparent;
            border: none;
        }}
        QPushButton {{
            background-color: qlineargradient(
                x1: 0,
                y1: 0,
                x2: 1,
                y2: 1,
                stop: 0 {shell_bar},
                stop: 1 {key_fill}
            );
            border: 1px solid {key_edge};
            border-radius: 12px;
            padding: 8px 4px;
            text-align: center;
            font-size: 15px;
            font-weight: 600;
            color: {text};
        }}
        QPushButton:hover {{
            background-color: qlineargradient(
                x1: 0,
                y1: 0,
                x2: 1,
                y2: 1,
                stop: 0 {key_hover},
                stop: 1 {accent_wash}
            );
            border-color: {accent_edge};
        }}
        QPushButton:pressed {{
            background-color: {key_pressed};
            border-color: {active_edge};
        }}
        QPushButton[latched="true"] {{
            background-color: qlineargradient(
                x1: 0,
                y1: 0,
                x2: 1,
                y2: 1,
                stop: 0 {active_fill},
                stop: 1 {accent_wash}
            );
            color: {text};
            border-color: {active_edge};
        }}
        QPushButton[latched="true"]:hover {{
            background-color: qlineargradient(
                x1: 0,
                y1: 0,
                x2: 1,
                y2: 1,
                stop: 0 {active_fill},
                stop: 1 {accent_wash_hover}
            );
        }}
        QPushButton:disabled {{
            color: {disabled_text};
            background-color: {disabled_fill};
            border-color: {disabled_edge};
        }}
        QMessageBox QLabel#qt_msgbox_label {{
            color: {text};
            font-size: 15px;
            font-weight: 600;
            min-width: 360px;
        }}
        QMessageBox QLabel#qt_msgbox_informativelabel {{
            color: {disabled_text};
            font-size: 13px;
            line-height: 1.45;
        }}
        QMessageBox QLabel {{
            color: {text};
        }}
        QMessageBox QDialogButtonBox {{
            background-color: {shell_bar};
            border-top: 1px solid {shell_edge};
            padding-top: 12px;
            margin-top: 8px;
        }}
        QMessageBox QPushButton {{
            min-width: 124px;
            padding: 10px 12px;
        }}
        QMessageBox QPushButton:hover {{
            border-color: {active_edge};
        }}
        QToolTip {{
            color: {text};
            background-color: {shell_bar};
            border: 1px solid {accent_glow};
            border-radius: 8px;
            padding: 4px 6px;
        }}
        """
