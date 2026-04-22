from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class ThemePalette:
    shell_fill: QColor
    shell_edge: QColor
    shell_bar: QColor
    shell_bar_hover: QColor
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
        shell_fill=QColor("#1c1318"),
        shell_edge=QColor("#6d4c5b"),
        shell_bar=QColor("#24181f"),
        shell_bar_hover=QColor("#2b1d25"),
        key_fill=QColor("#3f2c35"),
        key_hover=QColor("#4b3440"),
        key_pressed=QColor("#312129"),
        key_edge=QColor("#745261"),
        active_fill=QColor("#5b3c49"),
        active_edge=QColor("#9d7284"),
        text=QColor("#f4e9ee"),
        disabled_text=QColor("#b89ba7"),
        disabled_fill=QColor("#24191f"),
        disabled_edge=QColor("#4f3843"),
    )


def build_stylesheet() -> str:
    palette = build_theme_palette()
    shell_fill = palette.shell_fill.name()
    shell_edge = palette.shell_edge.name()
    shell_bar = palette.shell_bar.name()
    shell_bar_hover = palette.shell_bar_hover.name()
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
        QWidget {{
            color: {text};
            font-family: "Segoe UI";
            font-size: 14px;
        }}
        QWidget#rootSurface {{
            background: {shell_fill};
            border: 1px solid {shell_edge};
            border-radius: 6px;
        }}
        QFrame#layerShellTitleBar {{
            background: {shell_bar};
            border: 1px solid {shell_edge};
            border-radius: 4px;
        }}
        QFrame#layerShellTitleBar:hover {{
            background: {shell_bar_hover};
        }}
        QLabel#layerShellTitleLabel {{
            font-size: 13px;
            font-weight: 700;
        }}
        QPushButton#layerShellCloseButton {{
            background-color: {key_fill};
            border: 1px solid {key_edge};
            border-radius: 4px;
            padding: 0px;
            font-size: 12px;
            font-weight: 700;
            min-width: 28px;
            max-width: 28px;
        }}
        QPushButton#layerShellCloseButton:hover {{
            background-color: {key_hover};
        }}
        QPushButton#layerShellCloseButton:pressed {{
            background-color: {key_pressed};
            border-color: {active_edge};
        }}
        QLabel#statusLabel {{
            color: {disabled_text};
            font-size: 12px;
        }}
        QFrame#layerShellResizeHandle {{
            background: {shell_bar};
            border: 1px solid {shell_edge};
            border-radius: 4px;
        }}
        QFrame#keyboard {{
            background: transparent;
            border: none;
        }}
        QPushButton {{
            background-color: {key_fill};
            border: 1px solid {key_edge};
            border-radius: 0px;
            padding: 8px 4px;
            text-align: center;
            font-size: 14px;
            font-weight: 600;
            color: {text};
        }}
        QPushButton:hover {{
            background-color: {key_hover};
        }}
        QPushButton:pressed {{
            background-color: {key_pressed};
            border-color: {active_edge};
        }}
        QPushButton[latched="true"] {{
            background-color: {active_fill};
            color: {text};
            border-color: {active_edge};
        }}
        QPushButton:disabled {{
            color: {disabled_text};
            background-color: {disabled_fill};
            border-color: {disabled_edge};
        }}
        """
