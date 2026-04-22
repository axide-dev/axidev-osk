from __future__ import annotations

from PySide6.QtGui import QColor


def build_stylesheet() -> str:
    shell_fill = QColor("#1c1318").name()
    shell_edge = QColor("#6d4c5b").name()
    shell_bar = QColor("#24181f").name()
    shell_bar_hover = QColor("#2b1d25").name()
    key_fill = QColor("#3f2c35").name()
    key_hover = QColor("#4b3440").name()
    key_pressed = QColor("#312129").name()
    key_edge = QColor("#745261").name()
    active_fill = QColor("#5b3c49").name()
    active_edge = QColor("#9d7284").name()
    text = QColor("#f4e9ee").name()
    disabled_text = QColor("#b89ba7").name()
    disabled_fill = QColor("#24191f").name()
    disabled_edge = QColor("#4f3843").name()

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
