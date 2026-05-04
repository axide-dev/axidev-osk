from __future__ import annotations

from PySide6.QtCore import QEventLoop, QSize, Qt
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..styles.theme import apply_theme
from .overlay_window import (
    AlwaysOnTopWindowConfig,
    OverlayPlacement,
    configure_always_on_top_window,
)

_ACCEPT_BUTTON_QSS = """
QPushButton#confirmAcceptButton {
    background-color: rgba(38, 132, 70, 0.25);
    border: 1px solid rgba(80, 200, 120, 0.85);
    color: #d8ffe3;
}
QPushButton#confirmAcceptButton:hover {
    background-color: rgba(56, 168, 90, 0.45);
    border-color: rgba(120, 230, 150, 1.0);
}
QPushButton#confirmAcceptButton:pressed {
    background-color: rgba(30, 110, 58, 0.85);
}
"""

_REJECT_BUTTON_QSS = """
QPushButton#confirmRejectButton {
    background-color: rgba(160, 40, 50, 0.25);
    border: 1px solid rgba(220, 90, 100, 0.85);
    color: #ffe1e3;
}
QPushButton#confirmRejectButton:hover {
    background-color: rgba(190, 60, 70, 0.45);
    border-color: rgba(240, 130, 140, 1.0);
}
QPushButton#confirmRejectButton:pressed {
    background-color: rgba(140, 30, 40, 0.85);
}
"""


class ConfirmOverlayWindow(QMainWindow):
    """Confirmation surface configured like the main keyboard window."""

    def __init__(
        self,
        *,
        title: str,
        message: str,
        accept_label: str = "Yes",
        reject_label: str = "No",
        prompt_glyph: str = "!",
        accept_glyph: str = "\u2714",  # ✔
        reject_glyph: str = "\u2716",  # ✖
        hint: str | None = None,
        danger: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._result = QDialog.DialogCode.Rejected
        self._event_loop: QEventLoop | None = None

        self.setWindowTitle(title)
        self._overlay = configure_always_on_top_window(
            self,
            config=AlwaysOnTopWindowConfig(
                placement=OverlayPlacement.CENTER,
                screen_margin=16,
            ),
        )

        central = QWidget()
        central.setObjectName("rootSurface")
        central.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(14)

        message_row = QHBoxLayout()
        message_row.setContentsMargins(0, 0, 0, 0)
        message_row.setSpacing(14)

        glyph_label = QLabel(prompt_glyph, central)
        glyph_label.setFixedSize(40, 40)
        glyph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if danger:
            badge_bg = "#d83a3a"
            badge_fg = "#fff5f5"
        else:
            badge_bg = "#ffd866"
            badge_fg = "#1a1a1a"
        glyph_label.setStyleSheet(
            "QLabel {"
            f"  background-color: {badge_bg};"
            f"  color: {badge_fg};"
            "  border-radius: 20px;"
            "  font-size: 22px;"
            "  font-weight: 900;"
            "}"
        )
        message_row.addWidget(glyph_label, 0, Qt.AlignmentFlag.AlignVCenter)

        message_label = QLabel(message, central)
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        message_row.addWidget(message_label, 1)
        layout.addLayout(message_row)

        if hint:
            hint_label = QLabel(hint, central)
            hint_label.setWordWrap(True)
            hint_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            hint_label.setStyleSheet(
                "QLabel {"
                "  color: rgba(220, 220, 220, 0.65);"
                "  font-size: 11px;"
                "  font-style: italic;"
                "  padding: 6px 8px;"
                "  border-left: 2px solid rgba(180, 180, 180, 0.35);"
                "}"
            )
            layout.addWidget(hint_label)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(10)
        buttons.addStretch(1)

        accept_button = QPushButton(f"{accept_glyph}  {accept_label}", central)
        accept_button.setObjectName("confirmAcceptButton")
        accept_button.setStyleSheet(_ACCEPT_BUTTON_QSS)

        reject_button = QPushButton(f"{reject_glyph}  {reject_label}", central)
        reject_button.setObjectName("confirmRejectButton")
        reject_button.setStyleSheet(_REJECT_BUTTON_QSS)


        accept_button.clicked.connect(self.accept)
        reject_button.clicked.connect(self.reject)

        buttons.addWidget(accept_button)
        buttons.addWidget(reject_button)
        layout.addLayout(buttons)

        self.setCentralWidget(central)
        app = QApplication.instance()
        if app is not None:
            apply_theme(app)
        self._apply_startup_size()

    def exec(self) -> QDialog.DialogCode:
        self._result = QDialog.DialogCode.Rejected
        self.show()
        self._event_loop = QEventLoop(self)
        self._event_loop.exec()
        self._event_loop = None
        return self._result

    def accept(self) -> None:
        self._finish(QDialog.DialogCode.Accepted)

    def reject(self) -> None:
        self._finish(QDialog.DialogCode.Rejected)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._result = QDialog.DialogCode.Rejected
        if self._event_loop is not None and self._event_loop.isRunning():
            self._event_loop.quit()
        super().closeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._overlay.handle_show()

    def _finish(self, result: QDialog.DialogCode) -> None:
        self._result = result
        self.hide()
        if self._event_loop is not None and self._event_loop.isRunning():
            self._event_loop.quit()

    def _apply_startup_size(self) -> None:
        self.ensurePolished()
        central_widget = self.centralWidget()
        if central_widget is not None:
            central_widget.ensurePolished()
            central_layout = central_widget.layout()
            if central_layout is not None:
                central_layout.activate()

        minimum_size = self.minimumSizeHint().expandedTo(QSize(460, 0))
        self.setMinimumSize(minimum_size)
        self.resize(minimum_size)
