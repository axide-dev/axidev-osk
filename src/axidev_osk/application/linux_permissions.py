"""Linux keyboard permission setup prompt and terminal launch helpers."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QMessageBox

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
        """Schedule the permission prompt when the keyboard service requires setup."""

        if self._keyboard.needs_permission_setup:
            QTimer.singleShot(0, self.show_prompt)

    def show_prompt(self) -> None:
        """Show the configured permission prompt and apply the selected action."""

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
        parent = self._window_manager.get_or_create(self._config.keyboard_window_id)
        command = [sys.executable, "-m", "axidev_osk", "linux", "setup-permissions"]
        if launch_command_in_terminal(command):
            QMessageBox.information(
                parent,
                "Terminal Opened",
                (
                    "A terminal window was opened for Linux permission setup.\n\n"
                    "Complete the sudo prompt there. When setup finishes, log out and back in, "
                    "then relaunch axidev-osk and test keyboard output again."
                ),
            )
            return
        QMessageBox.warning(parent, "No Terminal Launcher Found", self._keyboard.permission_setup_text)


def launch_command_in_terminal(command: list[str]) -> bool:
    """Launch a command in an available terminal emulator."""

    if os.name == "nt":
        return False

    terminal_command = _terminal_launch_command(command)
    if terminal_command is None:
        return False

    try:
        subprocess.Popen(terminal_command)
    except OSError:
        return False

    return True


def _terminal_launch_command(command: list[str]) -> list[str] | None:
    shell_command = _build_terminal_shell_command(command)

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


def _build_terminal_shell_command(command: list[str]) -> str:
    quoted_command = shlex.join(command)
    return (
        f"{quoted_command}; "
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
