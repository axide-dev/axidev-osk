from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path


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
