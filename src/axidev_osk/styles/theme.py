from __future__ import annotations

from PySide6.QtGui import QColor


def build_stylesheet() -> str:
    key_fill = QColor("#232933").name()
    key_hover = QColor("#2d3642").name()
    key_pressed = QColor("#1b2129").name()
    key_edge = QColor("#465364").name()
    active_fill = QColor("#3c556f").name()
    active_edge = QColor("#78a6d1").name()
    text = QColor("#f5f7fa").name()
    disabled_text = QColor("#96a1af").name()
    disabled_fill = QColor("#171c23").name()
    disabled_edge = QColor("#2a323d").name()

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
            background: rgba(10, 12, 16, 190);
            border: 1px solid rgba(255, 255, 255, 28);
            border-radius: 18px;
        }}
        QFrame#keyboard {{
            background: transparent;
            border: none;
        }}
        QPushButton {{
            background-color: {key_fill};
            border: 1px solid {key_edge};
            border-radius: 10px;
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
