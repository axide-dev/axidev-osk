"""Terminal launch helpers for Linux keyboard permission setup."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys


def open_permission_setup_terminal() -> bool:
    """Open a terminal running ``axidev-osk linux setup-permissions``.

    Returns:
        Whether a terminal launcher was found and started.
    """

    return launch_command_in_terminal([sys.executable, "-m", "axidev_osk", "linux", "setup-permissions"])


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
