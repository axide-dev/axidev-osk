from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QMessageBox, QVBoxLayout, QWidget

from ..components.keyboard_widget import KeyboardWidget
from ..keyboard_io import AxidevIoKeyboardBackend
from ..styles.theme import build_stylesheet
from .overlay_window import (
    AlwaysOnTopWindowConfig,
    OverlayPlacement,
    configure_always_on_top_window,
)
from .window_chrome import install_overlay_chrome


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self._keyboard_backend = AxidevIoKeyboardBackend()
        self._keyboard_backend.initialize()

        self.setWindowTitle("axidev on-screen keyboard")
        self._overlay = configure_always_on_top_window(
            self,
            config=AlwaysOnTopWindowConfig(
                placement=OverlayPlacement.TOP_RIGHT,
                screen_margin=16,
            ),
        )

        central = QWidget()
        central.setObjectName("rootSurface")

        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(8)

        if self._overlay.uses_custom_chrome:
            install_overlay_chrome(
                layout,
                footer,
                title=self.windowTitle(),
                parent=central,
                on_move=self._overlay.move_by,
                on_resize=self._overlay.resize_by,
            )

        keyboard_widget = KeyboardWidget(self._keyboard_backend)
        layout.addWidget(keyboard_widget)

        if not self._keyboard_backend.ready:
            status_label = QLabel(self._keyboard_backend.status_text, central)
            status_label.setObjectName("statusLabel")
            status_label.setWordWrap(True)
            footer.addWidget(status_label, 1)
        else:
            footer.addStretch(1)

        layout.addLayout(footer)

        self.setCentralWidget(central)
        self.setStyleSheet(build_stylesheet())
        self._apply_startup_size()
        self._prompt_for_linux_permissions_if_needed()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._keyboard_backend.shutdown()
        super().closeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._overlay.handle_show()

    def _apply_startup_size(self) -> None:
        self.ensurePolished()
        minimum_size = self.minimumSizeHint().expandedTo(QSize(0, 0))
        self.setMinimumSize(minimum_size)
        self.resize(minimum_size)

    def _prompt_for_linux_permissions_if_needed(self) -> None:
        if not self._keyboard_backend.needs_permission_setup:
            return
        QTimer.singleShot(0, self._show_linux_permission_prompt)

    def _show_linux_permission_prompt(self) -> None:
        answer = QMessageBox.question(
            self,
            "Linux Input Permission",
            (
                "Keyboard output is blocked by Linux permissions.\n\n"
                "Have you already configured /dev/uinput access for this user?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.No:
            return

        QMessageBox.information(
            self,
            "Permission Setup",
            self._keyboard_backend.permission_setup_text,
        )
