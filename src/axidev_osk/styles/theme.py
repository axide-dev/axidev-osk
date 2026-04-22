from __future__ import annotations

from PySide6.QtGui import QColor


def build_stylesheet() -> str:
    chrome = QColor("#d8dbe0").name()
    panel = QColor("#c4c9d1").name()
    surface = QColor("#eef1f4").name()
    key_fill = QColor("#f7f8fa").name()
    key_edge = QColor("#8f97a3").name()
    key_shadow = QColor("#b3b8c0").name()
    active_fill = QColor("#5d6b7d").name()
    active_edge = QColor("#445161").name()
    text = QColor("#1f2329").name()

    return f"""
        QWidget {{
            background: {chrome};
            color: {text};
            font-family: "Segoe UI";
            font-size: 14px;
        }}
        QFrame#keyboard {{
            background: {panel};
            border: 1px solid #9ca3ad;
            border-radius: 12px;
        }}
        QLabel#backendStatus {{
            background: transparent;
            font-size: 12px;
            font-weight: 600;
            padding: 2px 4px 0 4px;
        }}
        QLabel#backendStatus[ready="true"] {{
            color: #355a3a;
        }}
        QLabel#backendStatus[ready="false"] {{
            color: #8b2d2d;
        }}
        QPushButton {{
            background: {key_fill};
            border: 1px solid {key_edge};
            border-bottom: 2px solid {key_shadow};
            border-radius: 8px;
            padding: 6px 4px;
            text-align: center;
            font-size: 14px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background: {surface};
        }}
        QPushButton:pressed {{
            background: #e2e6eb;
            border-bottom-width: 1px;
        }}
        QPushButton[latched="true"] {{
            background: {active_fill};
            color: white;
            border-color: {active_edge};
            border-bottom-color: {active_edge};
        }}
        QPushButton:disabled {{
            color: #6f7782;
            background: #dde2e8;
            border-color: #aab2bc;
            border-bottom-color: #bcc3cc;
        }}
        """
