from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

VoidCallback = Callable[[], None]


@dataclass(frozen=True)
class KeySpec:
    label: str
    width: float = 1.0
    secondary_label: str | None = None
    key_id: str | None = None
    latchable: bool = False


def format_key_label(label: str, secondary_label: str | None = None) -> str:
    if secondary_label is None:
        return label
    return f"{secondary_label}\n{label}"


def refresh_key_button(button: QPushButton, latched: bool) -> None:
    button.setProperty("latched", latched)
    button.setChecked(latched)
    button.style().unpolish(button)
    button.style().polish(button)
    button.update()


def create_key_button(
    label: str,
    *,
    width: float = 1.0,
    secondary_label: str | None = None,
    key_id: str | None = None,
    latchable: bool = False,
    latched: bool = False,
    on_press: VoidCallback | None = None,
    on_latch: VoidCallback | None = None,
    on_unlatch: VoidCallback | None = None,
) -> QPushButton:
    button = QPushButton(format_key_label(label, secondary_label))
    button.setProperty("keyId", key_id or label)
    button.setProperty("keyWidth", width)
    button.setProperty("latched", latched)
    button.setProperty("latchable", latchable)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCheckable(latchable)
    button.setMinimumHeight(56)
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    refresh_key_button(button, latched)

    def handle_click() -> None:
        if latchable:
            next_latched = not bool(button.property("latched"))
            refresh_key_button(button, next_latched)
            if next_latched:
                if on_latch is not None:
                    on_latch()
            elif on_unlatch is not None:
                on_unlatch()

        if on_press is not None:
            on_press()

    button.clicked.connect(handle_click)
    return button


class KeyboardWidget(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self._latched_keys: dict[str, bool] = {"shift": False, "caps": False}
        self._latch_groups: dict[str, list[QPushButton]] = {"shift": [], "caps": []}

        self.setObjectName("keyboard")
        self.setFrameShape(QFrame.Shape.NoFrame)

        container = QVBoxLayout(self)
        container.setContentsMargins(18, 18, 18, 18)
        container.setSpacing(10)

        for row in self._layout_definition():
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)

            for spec in row:
                button = self._build_key(spec)
                row_layout.addWidget(button, int(spec.width * 10))

            container.addLayout(row_layout)

    def _layout_definition(self) -> list[list[KeySpec]]:
        return [
            [
                KeySpec("`", secondary_label="~"),
                KeySpec("1", secondary_label="!"),
                KeySpec("2", secondary_label="@"),
                KeySpec("3", secondary_label="#"),
                KeySpec("4", secondary_label="$"),
                KeySpec("5", secondary_label="%"),
                KeySpec("6", secondary_label="^"),
                KeySpec("7", secondary_label="&"),
                KeySpec("8", secondary_label="*"),
                KeySpec("9", secondary_label="("),
                KeySpec("0", secondary_label=")"),
                KeySpec("-", secondary_label="_"),
                KeySpec("=", secondary_label="+"),
                KeySpec("Backspace", width=2.2, key_id="backspace"),
            ],
            [
                KeySpec("Tab", width=1.7, key_id="tab"),
                KeySpec("Q"),
                KeySpec("W"),
                KeySpec("E"),
                KeySpec("R"),
                KeySpec("T"),
                KeySpec("Y"),
                KeySpec("U"),
                KeySpec("I"),
                KeySpec("O"),
                KeySpec("P"),
                KeySpec("[", secondary_label="{"),
                KeySpec("]", secondary_label="}"),
                KeySpec("\\", width=1.5, secondary_label="|"),
            ],
            [
                KeySpec("Caps", width=2.1, key_id="caps", latchable=True),
                KeySpec("A"),
                KeySpec("S"),
                KeySpec("D"),
                KeySpec("F"),
                KeySpec("G"),
                KeySpec("H"),
                KeySpec("J"),
                KeySpec("K"),
                KeySpec("L"),
                KeySpec(";", secondary_label=":"),
                KeySpec("'", secondary_label='"'),
                KeySpec("Enter", width=2.6, key_id="enter"),
            ],
            [
                KeySpec("Shift", width=2.6, key_id="shift", latchable=True),
                KeySpec("<", secondary_label=">"),
                KeySpec("Z"),
                KeySpec("X"),
                KeySpec("C"),
                KeySpec("V"),
                KeySpec("B"),
                KeySpec("N"),
                KeySpec("M"),
                KeySpec(",", secondary_label="<"),
                KeySpec(".", secondary_label=">"),
                KeySpec("/", secondary_label="?"),
                KeySpec("Shift", width=3.0, key_id="shift", latchable=True),
            ],
            [
                KeySpec("Ctrl", width=1.7, key_id="ctrl"),
                KeySpec("Alt", width=1.5, key_id="alt"),
                KeySpec("Space", width=7.2, key_id="space"),
                KeySpec("AltGr", width=1.7, key_id="altgr"),
                KeySpec("Left", width=1.4, key_id="left"),
                KeySpec("Right", width=1.7, key_id="right"),
            ],
        ]

    def _build_key(self, spec: KeySpec) -> QPushButton:
        on_latch = None
        on_unlatch = None
        latched = False

        if spec.latchable and spec.key_id is not None:
            on_latch = lambda key_id=spec.key_id: self.set_latched_state(key_id, True)
            on_unlatch = lambda key_id=spec.key_id: self.set_latched_state(key_id, False)
            latched = self._latched_keys.get(spec.key_id, False)

        button = create_key_button(
            spec.label,
            width=spec.width,
            secondary_label=spec.secondary_label,
            key_id=spec.key_id,
            latchable=spec.latchable,
            latched=latched,
            on_latch=on_latch,
            on_unlatch=on_unlatch,
        )

        if spec.latchable and spec.key_id is not None:
            self._latch_groups.setdefault(spec.key_id, []).append(button)

        return button

    def set_latched_state(self, key_id: str, latched: bool) -> None:
        self._latched_keys[key_id] = latched
        for button in self._latch_groups.get(key_id, []):
            refresh_key_button(button, latched)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AxiDev On-Screen Keyboard")
        self.resize(1160, 320)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(0)
        layout.addWidget(KeyboardWidget())

        self.setCentralWidget(central)
        self.apply_styles()

    def apply_styles(self) -> None:
        chrome = QColor("#d8dbe0").name()
        panel = QColor("#c4c9d1").name()
        surface = QColor("#eef1f4").name()
        key_fill = QColor("#f7f8fa").name()
        key_edge = QColor("#8f97a3").name()
        key_shadow = QColor("#b3b8c0").name()
        active_fill = QColor("#5d6b7d").name()
        active_edge = QColor("#445161").name()
        text = QColor("#1f2329").name()

        self.setStyleSheet(
            f"""
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
            """
        )


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
