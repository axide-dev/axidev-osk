from __future__ import annotations

import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from axidev_osk import __main__
from axidev_osk.cli import build_parser, main


class EntryPointTests(unittest.TestCase):
    def test_direct_file_execution_dispatches_cli(self) -> None:
        result = subprocess.run(
            [sys.executable, str(Path(__main__.__file__)), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: axidev-osk", result.stdout)

    def test_arguments_dispatch_cli_without_importing_app(self) -> None:
        with patch("axidev_osk.cli.main", return_value=7) as cli_main:
            result = __main__.main(["linux", "status-permissions"])

        self.assertEqual(result, 7)
        cli_main.assert_called_once_with(["linux", "status-permissions"])

    def test_no_arguments_dispatch_current_app(self) -> None:
        with patch("axidev_osk.app.main", return_value=9) as app_main:
            result = __main__.main([])

        self.assertEqual(result, 9)
        app_main.assert_called_once_with()


class ParserTests(unittest.TestCase):
    def test_linux_command_dispatches_with_original_arguments(self) -> None:
        arguments = ["linux", "setup-autostart", "--user", "alice"]
        with patch("axidev_osk.cli.linux.run_command", return_value=0) as handler:
            result = main(arguments)

        self.assertEqual(result, 0)
        namespace = handler.call_args.args[0]
        self.assertEqual(namespace.action, "setup")
        self.assertEqual(namespace.resource, "autostart")
        self.assertEqual(namespace.user, "alice")
        self.assertEqual(handler.call_args.args[1], arguments)

    def test_unknown_command_is_rejected(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as raised:
                build_parser().parse_args(["unknown"])

        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
