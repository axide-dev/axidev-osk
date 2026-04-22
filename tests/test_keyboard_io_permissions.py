from __future__ import annotations

import unittest
from types import ModuleType, SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from axidev_osk.keyboard_io import AxidevIoKeyboardBackend


class KeyboardIoPermissionTests(unittest.TestCase):
    def test_permission_script_prefers_bundle_root_helper(self) -> None:
        backend = AxidevIoKeyboardBackend()

        with TemporaryDirectory() as temp_dir:
            bundle_root = Path(temp_dir)
            script_path = bundle_root / "setup_uinput_permissions.sh"
            script_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            with (
                patch.object(AxidevIoKeyboardBackend, "_application_root", return_value=bundle_root),
                patch.object(AxidevIoKeyboardBackend, "_repo_root", return_value=bundle_root / "repo"),
            ):
                self.assertEqual(backend._permission_script_path(), script_path)

    def test_permission_setup_text_uses_root_level_bundle_command(self) -> None:
        backend = AxidevIoKeyboardBackend()

        with TemporaryDirectory() as temp_dir:
            bundle_root = Path(temp_dir)
            script_path = bundle_root / "setup_uinput_permissions.sh"
            script_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            with (
                patch.object(AxidevIoKeyboardBackend, "_application_root", return_value=bundle_root),
                patch.object(AxidevIoKeyboardBackend, "_repo_root", return_value=bundle_root / "repo"),
            ):
                text = backend.permission_setup_text
                command = backend.permission_setup_command

        self.assertIn("bash ./setup_uinput_permissions.sh", text)
        self.assertIn("Run that command from a real terminal so sudo can prompt there.", text)
        self.assertEqual(command, "bash ./setup_uinput_permissions.sh")

    def test_setup_permissions_prefers_local_linux_helper(self) -> None:
        backend = AxidevIoKeyboardBackend()
        fake_keyboard = SimpleNamespace(
            has_required_permissions=Mock(return_value=False),
            setup_permissions=Mock(side_effect=AssertionError("library helper should not run")),
        )
        fake_module = ModuleType("axidev_io")
        fake_module.keyboard = fake_keyboard

        with (
            patch.dict("sys.modules", {"axidev_io": fake_module}),
            patch("axidev_osk.keyboard_io.sys.platform", "linux"),
            patch.object(backend, "_permission_script_path", return_value=Path("/tmp/setup_uinput_permissions.sh")),
            patch.object(backend, "_run_permission_setup_script", return_value="/tmp/setup_uinput_permissions.sh") as run_helper,
        ):
            outcome = backend.setup_permissions()

        self.assertTrue(outcome.helper_applied)
        self.assertTrue(outcome.requires_logout)
        self.assertEqual(outcome.helper_path, "/tmp/setup_uinput_permissions.sh")
        run_helper.assert_called_once_with()
        fake_keyboard.setup_permissions.assert_not_called()


if __name__ == "__main__":
    unittest.main()
