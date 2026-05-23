from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QMessageBox, QWidget

from ..runtime.prompt import PromptResolutionWaiter

if TYPE_CHECKING:
    from ..config.models import AppConfig, WindowConfig
    from ..runtime.dispatcher import Dispatcher
    from ..runtime.window_manager import WindowManager
    from ..services.keyboard import KeyboardService


class LinuxPermissionController:
    """Owns application UI flow for Linux keyboard permission setup."""

    def __init__(
        self,
        *,
        config: "AppConfig",
        dispatcher: "Dispatcher",
        keyboard: "KeyboardService",
        window_manager: "WindowManager",
        build_prompt_window_config: Callable[[object], "WindowConfig"],
    ) -> None:
        self._config = config
        self._dispatcher = dispatcher
        self._keyboard = keyboard
        self._window_manager = window_manager
        self._build_prompt_window_config = build_prompt_window_config

    def prompt_if_needed(self) -> None:
        if self._keyboard.needs_permission_setup:
            QTimer.singleShot(0, self.show_prompt)

    def show_prompt(self) -> None:
        prompt_config = self._config.linux_permission_prompt
        parent = self._window_manager.get_or_create(self._config.keyboard_window_id)
        prompt_window = self._window_manager.create_transient(
            self._build_prompt_window_config(prompt_config),
            parent=parent,
        )
        event_loop = QEventLoop(prompt_window)
        waiter = PromptResolutionWaiter(self._dispatcher, prompt_config.id, event_loop, default="rejected")
        waiter.start()
        prompt_window.show()
        event_loop.exec()
        waiter.stop()
        prompt_window.close()

        if waiter.result == "open_terminal":
            self._open_terminal()
        elif waiter.result == "setup_here":
            self._run_setup()
        elif waiter.result == "already_configured":
            QMessageBox.information(
                parent,
                "Log Out Required",
                (
                    "The Linux permission setup may already be applied, but this desktop session "
                    "does not have the updated group membership yet.\n\n"
                    "Log out and back in, then relaunch axidev-osk and test keyboard output again."
                ),
            )

    def _open_terminal(self) -> None:
        script_path = self._keyboard.permission_setup_script_path
        parent = self._window_manager.get_or_create(self._config.keyboard_window_id)
        if script_path is None:
            QMessageBox.warning(parent, "Permission Helper Missing", self._keyboard.permission_setup_text)
            return
        if launch_permission_script_in_terminal(script_path):
            QMessageBox.information(
                parent,
                "Terminal Opened",
                (
                    "A terminal window was opened for the Linux permission helper.\n\n"
                    "Complete the sudo prompt there. When the script finishes, log out and back in, "
                    "then relaunch axidev-osk and test keyboard output again."
                ),
            )
            return
        QMessageBox.warning(parent, "No Terminal Launcher Found", self._keyboard.permission_setup_text)

    def _run_setup(self) -> None:
        outcome = self._keyboard.setup_permissions()
        parent = self._window_manager.get_or_create(self._config.keyboard_window_id)
        status_label = parent.findChild(QWidget, "statusLabel")
        if status_label is not None and hasattr(status_label, "setText"):
            status_label.setText(self._keyboard.status_text)  # type: ignore[attr-defined]
        if outcome.error_text is not None:
            QMessageBox.warning(parent, "Permission Setup Failed", f"{outcome.error_text}\n\n{self._keyboard.permission_setup_text}")
            return
        if outcome.requires_logout:
            detail = (
                "Linux permission setup finished, but the new group membership is not active "
                "in this session yet.\n\n"
                "Log out and back in, then relaunch axidev-osk and test keyboard output again."
            )
            if outcome.helper_path is not None:
                detail = f"{detail}\n\nHelper script: {outcome.helper_path}"
            QMessageBox.information(parent, "Log Out Required", detail)
            return
        if self._keyboard.ready:
            detail = "Linux keyboard permissions are available now. Keyboard output is ready."
            if outcome.already_granted:
                detail = "Linux keyboard permissions were already available in this session. Keyboard output is ready."
            QMessageBox.information(parent, "Permission Ready", detail)
            return
        QMessageBox.information(parent, "Permission Setup", self._keyboard.permission_setup_text)


def launch_permission_script_in_terminal(script_path: Path) -> bool:
    if os.name == "nt":
        return False

    command = _terminal_launch_command(script_path)
    if command is None:
        return False

    try:
        subprocess.Popen(command)
    except OSError:
        return False

    return True


def _terminal_launch_command(script_path: Path) -> list[str] | None:
    shell_command = _build_terminal_shell_command(script_path)

    candidates = (
        ("x-terminal-emulator", ["x-terminal-emulator", "-e", "bash", "-lc", shell_command]),
        ("gnome-terminal", ["gnome-terminal", "--", "bash", "-lc", shell_command]),
        ("konsole", ["konsole", "-e", "bash", "-lc", shell_command]),
        ("xfce4-terminal", ["xfce4-terminal", "--hold", "-e", f"bash -lc {shlex.quote(shell_command)}"]),
        ("kitty", ["kitty", "bash", "-lc", shell_command]),
        ("alacritty", ["alacritty", "-e", "bash", "-lc", shell_command]),
        ("wezterm", ["wezterm", "start", "--always-new-process", "bash", "-lc", shell_command]),
        ("xterm", ["xterm", "-hold", "-e", "bash", "-lc", shell_command]),
    )

    for executable, command in candidates:
        if shutil.which(executable):
            return command

    return None


def _build_terminal_shell_command(script_path: Path) -> str:
    quoted_script_path = shlex.quote(str(script_path))
    return (
        f"bash {quoted_script_path}; "
        "status=$?; "
        "printf '\\n'; "
        "if [ \"$status\" -eq 0 ]; then "
        "echo 'Setup finished. Log out and back in, then relaunch axidev-osk.'; "
        "else "
        "echo \"Setup failed with status $status.\"; "
        "fi; "
        "printf '\\nPress Enter to close...'; "
        "read -r _"
    )
