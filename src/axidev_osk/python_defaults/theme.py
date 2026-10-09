"""Default profile look, stored as plain data like a Lua config would."""

DEFAULT_PALETTE = {
    "window": "#0B0B10",
    "base": "#0B0B10",
    "alternate_base": "#12121A",
    "window_text": "#F5F6FA",
    "text": "#F5F6FA",
    "button": "#151520",
    "button_text": "#F5F6FA",
    "highlight": "#E61E8C",
    "highlighted_text": "#0B0B10",
    "placeholder_text": "#B9BBC7",
}

DEFAULT_FONT = {
    "families": [
        "Segoe UI Variable Text",
        "Segoe UI Variable",
        "Inter",
        "Segoe UI",
        "SF Pro Text",
        "Ubuntu",
        "Noto Sans",
        "Cantarell",
        "Arial",
    ],
    "pixel_size": 14,
    "weight": "medium",
}

HOT_CORNER_INDICATOR = {
    "indicator_background": "#0B0B10",
    "indicator_track": "#242433",
    "indicator_progress": "#E61E8C",
    "indicator_center": "#2A1421",
}

DEFAULT_QSS = """
QMainWindow {
    background: transparent;
}
QWidget {
    color: #f5f6fa;
    font-size: 14px;
}
QWidget#rootSurface {
    background-color: qlineargradient(
        x1: 0,
        y1: 0,
        x2: 1,
        y2: 1,
        stop: 0 #0b0b10,
        stop: 0.74 #0b0b10,
        stop: 1 #12121a
    );
    border: 1px solid #242433;
    border-radius: 14px;
}
QFrame#layerShellTitleBar {
    background-color: qlineargradient(
        x1: 0,
        y1: 0,
        x2: 1,
        y2: 1,
        stop: 0 #12121a,
        stop: 0.8 #12121a,
        stop: 1 rgba(230, 30, 140, 32)
    );
    border: 1px solid #242433;
    border-radius: 10px;
}
QFrame#layerShellTitleBar:hover {
    background-color: qlineargradient(
        x1: 0,
        y1: 0,
        x2: 1,
        y2: 1,
        stop: 0 #171723,
        stop: 0.76 #171723,
        stop: 1 rgba(230, 30, 140, 48)
    );
}
QLabel#layerShellTitleLabel {
    color: #f5f6fa;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
QPushButton#layerShellCloseButton {
    background-color: #151520;
    border: 1px solid #2e2a3f;
    border-radius: 10px;
    padding: 0px;
    font-size: 13px;
    font-weight: 700;
    min-width: 28px;
    max-width: 28px;
}
QPushButton#layerShellCloseButton:hover {
    background-color: rgba(230, 30, 140, 32);
    border-color: rgba(230, 30, 140, 110);
}
QPushButton#layerShellCloseButton:pressed {
    background-color: #2a1421;
    border-color: #e61e8c;
}
QLabel#statusLabel {
    color: #b9bbc7;
    font-size: 13px;
}
QFrame#layerShellResizeHandle {
    background-color: qlineargradient(
        x1: 0,
        y1: 1,
        x2: 1,
        y2: 0,
        stop: 0 #12121a,
        stop: 0.45 #12121a,
        stop: 1 rgba(230, 30, 140, 32)
    );
    border: 1px solid #2e2a3f;
    border-radius: 8px;
}
QWidget#keyboard {
    background: transparent;
    border: none;
}
QPushButton {
    background-color: qlineargradient(
        x1: 0,
        y1: 0,
        x2: 1,
        y2: 1,
        stop: 0 #12121a,
        stop: 1 #151520
    );
    border: 1px solid #2e2a3f;
    border-radius: 12px;
    padding: 8px 4px;
    text-align: center;
    font-size: 18px;
    font-weight: 600;
    color: #f5f6fa;
}
QPushButton:hover {
    background-color: qlineargradient(
        x1: 0,
        y1: 0,
        x2: 1,
        y2: 1,
        stop: 0 #1d1a27,
        stop: 1 rgba(230, 30, 140, 32)
    );
    border-color: rgba(230, 30, 140, 110);
}
QPushButton:pressed {
    background-color: #101018;
    border-color: #e61e8c;
}
QPushButton[interactionState="pressed"],
QPushButton[interactionState="latched_pressed"] {
    background-color: #101018;
    border-color: #e61e8c;
}
QPushButton[latched="true"] {
    background-color: qlineargradient(
        x1: 0,
        y1: 0,
        x2: 1,
        y2: 1,
        stop: 0 #2a1421,
        stop: 1 rgba(230, 30, 140, 32)
    );
    color: #f5f6fa;
    border-color: #e61e8c;
}
QPushButton[latched="true"]:hover {
    background-color: qlineargradient(
        x1: 0,
        y1: 0,
        x2: 1,
        y2: 1,
        stop: 0 #2a1421,
        stop: 1 rgba(230, 30, 140, 48)
    );
}
QPushButton:disabled {
    color: #b9bbc7;
    background-color: #0f0f16;
    border-color: #242433;
}
QWidget[pointerLocatorEnabled="true"] QPushButton {
    background-color: qlineargradient(
        x1: 0,
        y1: 0,
        x2: 1,
        y2: 1,
        stop: 0 rgba(18, 18, 26, 153),
        stop: 1 rgba(21, 21, 32, 153)
    );
}
QWidget[pointerLocatorEnabled="true"] QPushButton:hover {
    background-color: qlineargradient(
        x1: 0,
        y1: 0,
        x2: 1,
        y2: 1,
        stop: 0 rgba(29, 26, 39, 153),
        stop: 1 rgba(42, 20, 33, 153)
    );
}
QWidget[pointerLocatorEnabled="true"] QPushButton:pressed,
QWidget[pointerLocatorEnabled="true"] QPushButton[interactionState="pressed"],
QWidget[pointerLocatorEnabled="true"] QPushButton[interactionState="latched_pressed"] {
    background-color: rgba(16, 16, 24, 153);
}
QWidget[pointerLocatorEnabled="true"] QPushButton[latched="true"] {
    background-color: qlineargradient(
        x1: 0,
        y1: 0,
        x2: 1,
        y2: 1,
        stop: 0 rgba(42, 20, 33, 153),
        stop: 1 rgba(29, 26, 39, 153)
    );
}
QWidget[pointerLocatorEnabled="true"] QPushButton:disabled {
    background-color: rgba(15, 15, 22, 153);
}

"""
