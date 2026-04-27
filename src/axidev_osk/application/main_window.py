from __future__ import annotations

from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QVBoxLayout, QWidget

from ..components.keyboard_widget import KeyboardWidget
from ..keyboard_io import AxidevIoKeyboardBackend
from ..styles.theme import apply_theme
from .overlay_window import (
    AlwaysOnTopWindowConfig,
    OverlayPlacement,
    configure_always_on_top_window,
)
from .linux_permissions import launch_permission_script_in_terminal
from .window_chrome import install_overlay_chrome


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self._keyboard_backend = AxidevIoKeyboardBackend()
        self._status_label: QLabel | None = None
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
        central.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        if self._overlay.uses_custom_chrome:
            install_overlay_chrome(
                layout,
                title=self.windowTitle(),
                parent=central,
                on_move=self._overlay.move_by,
                on_resize=self._overlay.resize_by,
            )

        keyboard_widget = KeyboardWidget(self._keyboard_backend)
        layout.addWidget(keyboard_widget)

        if not self._keyboard_backend.ready:
            footer = QHBoxLayout()
            footer.setContentsMargins(0, 0, 0, 0)
            footer.setSpacing(8)
            self._status_label = QLabel(self._keyboard_backend.status_text, central)
            self._status_label.setObjectName("statusLabel")
            self._status_label.setWordWrap(True)
            footer.addWidget(self._status_label, 1)
            layout.addLayout(footer)

        self.setCentralWidget(central)
        app = QApplication.instance()
        if app is not None:
            apply_theme(app)
        self._apply_startup_size()
        self._prompt_for_linux_permissions_if_needed()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._keyboard_backend.shutdown()
        super().closeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._overlay.handle_show()

    def prepare_overlay_show(self) -> None:
        self._overlay.prepare_show()

    def _apply_startup_size(self) -> None:
        self.ensurePolished()
        minimum_size = self.minimumSizeHint().expandedTo(QSize(0, 0))
        startup_size = self.sizeHint().expandedTo(minimum_size)
        self.setMinimumSize(minimum_size)
        self.resize(startup_size)

    def _prompt_for_linux_permissions_if_needed(self) -> None:
        if not self._keyboard_backend.needs_permission_setup:
            return
        QTimer.singleShot(0, self._show_linux_permission_prompt)

    def _show_linux_permission_prompt(self) -> None:
        prompt = QMessageBox(self)
        prompt.setWindowTitle("Linux Input Permission")
        prompt.setIcon(QMessageBox.Icon.Question)
        prompt.setText("Keyboard output is blocked by Linux permissions.")
        prompt.setInformativeText(
            "Choose Open In Terminal to run the bundled helper in a real terminal window so sudo can prompt there. "
            "Run Setup Here still tries the helper directly from the app, but some desktops do not surface that prompt correctly. "
            "If you already ran setup, this session may just need a log out and back in."
        )
        terminal_button = prompt.addButton("Open In Terminal", QMessageBox.ButtonRole.AcceptRole)
        setup_button = prompt.addButton("Run Setup Here", QMessageBox.ButtonRole.ActionRole)
        already_configured_button = prompt.addButton(
            "Already Configured",
            QMessageBox.ButtonRole.ActionRole,
        )
        cancel_button = prompt.addButton(QMessageBox.StandardButton.Cancel)
        prompt.setDefaultButton(terminal_button)
        prompt.exec()

        clicked_button = prompt.clickedButton()
        if clicked_button is terminal_button:
            self._open_linux_permission_terminal()
            return

        if clicked_button is setup_button:
            self._run_linux_permission_setup()
            return

        if clicked_button is already_configured_button:
            QMessageBox.information(
                self,
                "Log Out Required",
                (
                    "The Linux permission setup may already be applied, but this desktop session "
                    "does not have the updated group membership yet.\n\n"
                    "Log out and back in, then relaunch axidev-osk and test keyboard output again."
                ),
            )
            return

        if clicked_button is cancel_button:
            return

    def _open_linux_permission_terminal(self) -> None:
        script_path = self._keyboard_backend.permission_setup_script_path
        if script_path is None:
            QMessageBox.warning(
                self,
                "Permission Helper Missing",
                self._keyboard_backend.permission_setup_text,
            )
            return

        if launch_permission_script_in_terminal(script_path):
            QMessageBox.information(
                self,
                "Terminal Opened",
                (
                    "A terminal window was opened for the Linux permission helper.\n\n"
                    "Complete the sudo prompt there. When the script finishes, log out and back in, "
                    "then relaunch axidev-osk and test keyboard output again."
                ),
            )
            return

        QMessageBox.warning(
            self,
            "No Terminal Launcher Found",
            self._keyboard_backend.permission_setup_text,
        )

    def _run_linux_permission_setup(self) -> None:
        outcome = self._keyboard_backend.setup_permissions()
        self._refresh_status_label()

        if outcome.error_text is not None:
            QMessageBox.warning(
                self,
                "Permission Setup Failed",
                f"{outcome.error_text}\n\n{self._keyboard_backend.permission_setup_text}",
            )
            return

        if outcome.requires_logout:
            detail = (
                "Linux permission setup finished, but the new group membership is not active "
                "in this session yet.\n\n"
                "Log out and back in, then relaunch axidev-osk and test keyboard output again."
            )
            if outcome.helper_path is not None:
                detail = f"{detail}\n\nHelper script: {outcome.helper_path}"
            QMessageBox.information(self, "Log Out Required", detail)
            return

        if self._keyboard_backend.ready:
            detail = "Linux keyboard permissions are available now. Keyboard output is ready."
            if outcome.already_granted:
                detail = (
                    "Linux keyboard permissions were already available in this session. "
                    "Keyboard output is ready."
                )
            QMessageBox.information(self, "Permission Ready", detail)
            return

        QMessageBox.information(
            self,
            "Permission Setup",
            self._keyboard_backend.permission_setup_text,
        )

    def _refresh_status_label(self) -> None:
        if self._status_label is None:
            return
        self._status_label.setText(self._keyboard_backend.status_text)
