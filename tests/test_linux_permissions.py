from __future__ import annotations

import unittest
from unittest.mock import patch

from axidev_osk.application.linux_permissions import (
    _build_terminal_shell_command,
    _terminal_launch_command,
    launch_command_in_terminal,
)


class LinuxPermissionTerminalTests(unittest.TestCase):
    def test_terminal_shell_command_runs_cli_and_waits_for_input(self) -> None:
        command = _build_terminal_shell_command(
            ["python", "-m", "axidev_osk", "linux", "setup-permissions"]
        )

        self.assertIn("axidev_osk linux setup-permissions", command)
        self.assertIn("Press Enter to close", command)
        self.assertIn("status=$?", command)

    def test_terminal_launch_command_prefers_x_terminal_emulator(self) -> None:
        with patch("axidev_osk.application.linux_permissions.shutil.which") as which:
            which.side_effect = lambda name: "/usr/bin/x-terminal-emulator" if name == "x-terminal-emulator" else None
            command = _terminal_launch_command(["axidev-osk", "linux", "setup-permissions"])

        self.assertIsNotNone(command)
        self.assertEqual(command[:4], ["x-terminal-emulator", "-e", "bash", "-lc"])

    def test_launch_command_returns_false_without_terminal(self) -> None:
        with (
            patch("axidev_osk.application.linux_permissions.os.name", "posix"),
            patch("axidev_osk.application.linux_permissions.shutil.which", return_value=None),
        ):
            launched = launch_command_in_terminal(["axidev-osk", "linux", "setup-permissions"])

        self.assertFalse(launched)


if __name__ == "__main__":
    unittest.main()
