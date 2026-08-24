from __future__ import annotations

import argparse
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from axidev_osk.cli import linux


class LinuxCliTests(unittest.TestCase):
    def test_public_help_describes_configuration_and_hides_runtime_command(self) -> None:
        parser = argparse.ArgumentParser()
        linux.register_commands(parser)
        output = io.StringIO()

        with patch("sys.stdout", output), self.assertRaises(SystemExit) as exit_context:
            parser.parse_args(["--help"])

        self.assertEqual(exit_context.exception.code, 0)
        help_text = output.getvalue()
        self.assertIn("setup-autostart", help_text)
        self.assertIn("configure desktop-session startup", help_text)
        self.assertIn("status-greeter", help_text)
        self.assertIn("check login-screen startup configuration", help_text)
        self.assertNotIn("run-greeter-keyboard", help_text)

    def test_status_command_reports_configuration_only_scope(self) -> None:
        namespace = argparse.Namespace(action="status", resource="permissions", user=None)
        account = linux.Account("alice", 1000, 1000, Path("/home/alice"))
        with (
            patch.object(linux.sys, "platform", "linux"),
            patch.object(linux, "_resolve_account", return_value=account),
            patch.object(linux, "_run_permissions", return_value=0),
            patch("builtins.print") as output,
        ):
            result = linux.run_command(namespace, ["linux", "status-permissions"])

        self.assertEqual(result, 0)
        output.assert_any_call(
            "Status scope: managed integration configuration and uinput checks where "
            "applicable; startup, rendering, and key input are not tested."
        )

    def test_service_account_does_not_require_home_directory(self) -> None:
        record = SimpleNamespace(
            pw_name="lightdm", pw_uid=42, pw_gid=42, pw_dir="/missing/lightdm"
        )
        fake_pwd = Mock()
        fake_pwd.getpwnam.return_value = record

        with patch.object(linux, "pwd", fake_pwd):
            account = linux._resolve_account("lightdm", require_home=False)

        self.assertEqual(account, linux.Account("lightdm", 42, 42, Path("/missing/lightdm")))

    def test_user_account_still_requires_home_directory(self) -> None:
        record = SimpleNamespace(pw_name="alice", pw_uid=1000, pw_gid=1000, pw_dir="/missing/alice")
        fake_pwd = Mock()
        fake_pwd.getpwnam.return_value = record

        with (
            patch.object(linux, "pwd", fake_pwd),
            self.assertRaisesRegex(linux.LinuxSetupError, "home directory does not exist"),
        ):
            linux._resolve_account("alice")

    def test_non_linux_command_stops_before_account_lookup(self) -> None:
        namespace = argparse.Namespace(action="status", resource="permissions", user=None)
        with (
            patch.object(linux.sys, "platform", "win32"),
            patch.object(linux, "_resolve_account") as resolve_account,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            result = linux.run_command(namespace, ["linux", "status-permissions"])

        self.assertEqual(result, 2)
        resolve_account.assert_not_called()

    def test_sudo_reexec_preserves_explicit_target_user(self) -> None:
        account = linux.Account("alice", 1000, 1000, Path("/home/alice"))
        completed = SimpleNamespace(returncode=4)
        with (
            patch.object(linux.shutil, "which", return_value="/usr/bin/sudo"),
            patch.object(linux.subprocess, "run", return_value=completed) as run,
        ):
            result = linux._sudo_reexec(["linux", "setup-permissions"], account)

        self.assertEqual(result, 4)
        self.assertEqual(run.call_args.args[0][-4:], ["linux", "setup-permissions", "--user", "alice"])

    def test_root_reexec_uses_runuser_for_target_account(self) -> None:
        account = linux.Account("alice", 1000, 1000, Path("/home/alice"))
        completed = SimpleNamespace(returncode=0)
        with (
            patch.object(linux, "_is_root", return_value=True),
            patch.object(linux.shutil, "which", return_value="/usr/sbin/runuser"),
            patch.object(linux.subprocess, "run", return_value=completed) as run,
            patch.dict(linux.os.environ, {"AXIDEV_OSK_ROOT": "/opt/axidev-osk"}),
            patch.object(linux.Path, "is_file", return_value=True),
        ):
            result = linux._sudo_reexec(["linux", "setup-autostart", "--user", "alice"], account, run_as_account=True)

        self.assertEqual(result, 0)
        self.assertEqual(run.call_args.args[0][:4], ["/usr/sbin/runuser", "--user", "alice", "--"])
        self.assertEqual(
            run.call_args.args[0][4], str(linux.Path("/opt/axidev-osk/bin/axidev-osk"))
        )
        self.assertNotIn("XDG_CONFIG_HOME", run.call_args.kwargs["env"])

    def test_payload_reexec_rejects_missing_launcher(self) -> None:
        account = linux.Account("alice", 1000, 1000, Path("/home/alice"))
        with (
            patch.dict(linux.os.environ, {"AXIDEV_OSK_ROOT": "/missing/payload"}),
            patch.object(linux.Path, "is_file", return_value=False),
            self.assertRaisesRegex(linux.LinuxSetupError, "payload launcher does not exist"),
        ):
            linux._sudo_reexec(["linux", "setup-autostart"], account, run_as_account=True)

    def test_autostart_reexecutes_as_target_account(self) -> None:
        account = linux.Account("alice", 1000, 1000, Path("/home/alice"))
        namespace = argparse.Namespace(action="setup", resource="autostart", user="alice")
        with (
            patch.object(linux.sys, "platform", "linux"),
            patch.object(linux, "_resolve_account", return_value=account),
            patch.object(linux, "_effective_uid", return_value=2000),
            patch.object(linux, "_sudo_reexec", return_value=0) as reexec,
        ):
            result = linux.run_command(namespace, ["linux", "setup-autostart", "--user", "alice"])

        self.assertEqual(result, 0)
        reexec.assert_called_once_with(
            ["linux", "setup-autostart", "--user", "alice"],
            account,
            run_as_account=True,
        )

    def test_remove_permissions_creates_udev_mask(self) -> None:
        rule_path = Mock()
        rule_path.parent = Mock()
        rule_path.exists.return_value = False
        rule_path.is_symlink.return_value = False
        with (
            patch.object(linux, "MODULES_LOAD_PATH", Path("/missing/modules-load.conf")),
            patch.object(linux, "UDEV_RULE_PATH", rule_path),
            patch.object(linux, "_reload_udev"),
        ):
            linux._remove_permissions()

        rule_path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        rule_path.symlink_to.assert_called_once_with("/dev/null")

    def test_owned_module_file_setup_and_remove(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "axidev-osk-uinput.conf"

            linux._ensure_owned_file(path, linux.MODULES_LOAD_TEXT)
            self.assertEqual(path.read_text(encoding="utf-8"), "uinput\n")

            linux._remove_owned_file(path, linux.MODULES_LOAD_TEXT)
            self.assertFalse(path.exists())

    def test_owned_module_file_preserves_conflicting_content(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "axidev-osk-uinput.conf"
            path.write_text("different\n", encoding="utf-8")

            with self.assertRaisesRegex(linux.LinuxSetupError, "conflicting"):
                linux._ensure_owned_file(path, linux.MODULES_LOAD_TEXT)
            with self.assertRaisesRegex(linux.LinuxSetupError, "conflicting"):
                linux._remove_owned_file(path, linux.MODULES_LOAD_TEXT)

            self.assertEqual(path.read_text(encoding="utf-8"), "different\n")

    def test_permission_status_requires_owned_module_file(self) -> None:
        account = linux.Account("alice", 1000, 1000, Path("/home/alice"))
        group = SimpleNamespace(gr_gid=991, gr_mem=["alice"])
        fake_grp = Mock()
        fake_grp.getgrnam.return_value = group
        with (
            patch.object(linux, "grp", fake_grp),
            patch.object(linux, "MODULES_LOAD_PATH", Path("/missing/modules-load.conf")),
            patch.object(linux, "_permission_rule_is_enabled", return_value=True),
            patch.object(linux, "_uinput_mode_is_ready", return_value=True),
            patch.object(linux, "_effective_uid", return_value=0),
            patch("builtins.print") as output,
        ):
            result = linux._status_permissions(account)

        self.assertEqual(result, 1)
        output.assert_any_call("missing: module load")

    def test_autostart_setup_and_remove_exact_file(self) -> None:
        with TemporaryDirectory() as temporary:
            account = linux.Account("alice", 1000, 1000, Path(temporary))
            with (
                patch.dict(linux.os.environ, {"XDG_CONFIG_HOME": ""}),
                patch.object(linux.shutil, "which", return_value="/usr/local/bin/axidev-osk"),
                patch.object(linux, "_is_root", return_value=False),
                patch("builtins.print"),
            ):
                linux._setup_autostart(account)
                path = account.home / linux.AUTOSTART_RELATIVE_PATH
                contents = path.read_text(encoding="utf-8")
                executable = str(linux.Path("/usr/local/bin/axidev-osk").resolve())
                self.assertIn(f"Exec={linux._desktop_exec_arg(executable)}", contents)
                self.assertIn(linux.AUTOSTART_MANAGED_LINE, contents)
                self.assertEqual(linux._status_autostart(account), 0)
                linux._remove_autostart(account)

            self.assertFalse(path.exists())

    def test_autostart_remove_works_without_executable_on_path(self) -> None:
        with TemporaryDirectory() as temporary:
            account = linux.Account("alice", 1000, 1000, Path(temporary))
            path = account.home / linux.AUTOSTART_RELATIVE_PATH
            path.parent.mkdir(parents=True)
            path.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Axidev OSK\n"
                "Exec=\"/removed/axidev-osk\"\n"
                f"{linux.AUTOSTART_MANAGED_LINE}",
                encoding="utf-8",
            )

            with (
                patch.dict(linux.os.environ, {"XDG_CONFIG_HOME": ""}),
                patch.object(linux.shutil, "which", return_value=None),
            ):
                linux._remove_autostart(account)

            self.assertFalse(path.exists())

    def test_autostart_honors_absolute_xdg_config_home(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            account = linux.Account("alice", 1000, 1000, root / "home")
            account.home.mkdir()
            config_home = root / "xdg"
            with patch.dict(linux.os.environ, {"XDG_CONFIG_HOME": str(config_home)}):
                path = linux._autostart_path(account)

            self.assertEqual(path, config_home / "autostart" / "axidev-osk.desktop")

    def test_autostart_remove_preserves_conflicting_file(self) -> None:
        with TemporaryDirectory() as temporary:
            account = linux.Account("alice", 1000, 1000, Path(temporary))
            path = account.home / linux.AUTOSTART_RELATIVE_PATH
            path.parent.mkdir(parents=True)
            path.write_text("different\n", encoding="utf-8")
            with (
                patch.dict(linux.os.environ, {"XDG_CONFIG_HOME": ""}),
                patch.object(linux.shutil, "which", return_value="/usr/local/bin/axidev-osk"),
            ):
                with self.assertRaises(linux.LinuxSetupError):
                    linux._remove_autostart(account)

            self.assertEqual(path.read_text(encoding="utf-8"), "different\n")

    def test_permission_setup_adds_missing_membership(self) -> None:
        account = linux.Account("alice", 1000, 1000, Path("/home/alice"))
        group = SimpleNamespace(gr_gid=991, gr_mem=[])
        fake_grp = Mock()
        fake_grp.getgrnam.return_value = group
        with (
            patch.object(linux, "grp", fake_grp),
            patch.object(linux, "_ensure_owned_file") as ensure_module,
            patch.object(linux, "_write_atomic"),
            patch.object(linux, "_run_checked") as run,
            patch.object(linux, "_reload_udev") as reload_udev,
            patch.object(linux, "UINPUT_PATH") as input_path,
            patch("builtins.print"),
        ):
            input_path.exists.return_value = True
            linux._setup_permissions(account)

        run.assert_called_once_with(["usermod", "-aG", "uinput", "alice"])
        ensure_module.assert_called_once_with(linux.MODULES_LOAD_PATH, linux.MODULES_LOAD_TEXT)
        reload_udev.assert_called_once_with(ensure_device=True)

    def test_reload_udev_loads_module_when_static_device_node_exists(self) -> None:
        input_path = Mock()
        input_path.exists.return_value = True
        with (
            patch.object(linux, "UINPUT_PATH", input_path),
            patch.object(linux, "_run_checked") as run,
        ):
            linux._reload_udev(ensure_device=True)

        self.assertEqual(
            run.call_args_list,
            [
                unittest.mock.call(["udevadm", "control", "--reload-rules"]),
                unittest.mock.call(["modprobe", "uinput"]),
                unittest.mock.call(["udevadm", "settle"]),
                unittest.mock.call(["udevadm", "trigger", str(input_path)]),
                unittest.mock.call(["udevadm", "settle"]),
            ],
        )


if __name__ == "__main__":
    unittest.main()
