from __future__ import annotations

import argparse
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from axidev_osk.cli import linux, linux_greeter


class GreeterParserTests(unittest.TestCase):
    def test_public_commands_match_existing_command_shape(self) -> None:
        parser = argparse.ArgumentParser()
        linux.register_commands(parser)

        namespace = parser.parse_args(["setup-greeter", "--manager", "plasma-login"])

        self.assertEqual(namespace.action, "setup")
        self.assertEqual(namespace.resource, "greeter")
        self.assertEqual(namespace.manager, "plasma-login")

    def test_selector_uses_arrow_keys(self) -> None:
        keys = iter(("down", "down", "enter"))
        output = io.StringIO()

        selected = linux_greeter._select_manager(
            ["plasma-login", "lightdm", "greetd"],
            key_reader=lambda: next(keys),
            output=output,
        )

        self.assertEqual(selected, "greetd")
        self.assertIn("Plasma Login Manager", output.getvalue())

    def test_selector_requires_flag_without_terminal(self) -> None:
        with self.assertRaisesRegex(linux.LinuxSetupError, "--manager"):
            linux_greeter._select_manager(["greetd"], output=io.StringIO())


class GreetdConfigTests(unittest.TestCase):
    CONFIG = (
        "# keep this comment\n"
        "[terminal]\n"
        "vt = 1\n"
        "[default_session]\n"
        'command = "dbus-run-session compositor -- greeter" # keep this too\n'
        'user = "greeter"\n'
    )

    def test_parse_returns_exact_command_line(self) -> None:
        parsed = linux_greeter._parse_greetd_config(self.CONFIG)

        self.assertEqual(parsed.account, "greeter")
        self.assertEqual(parsed.command, "dbus-run-session compositor -- greeter")
        self.assertEqual(
            parsed.original_line,
            'command = "dbus-run-session compositor -- greeter" # keep this too\n',
        )

    def test_multiline_command_is_rejected(self) -> None:
        config = '[default_session]\ncommand = """greeter"""\nuser = "greeter"\n'

        with self.assertRaisesRegex(linux.LinuxSetupError, "one-line"):
            linux_greeter._parse_greetd_config(config)

    def test_install_and_remove_restore_exact_config(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config.toml"
            state_path = root / "greeter.json"
            wrapper_path = root / "greetd-session-wrapper"
            config.write_text(self.CONFIG, encoding="utf-8")
            account = linux.Account("greeter", 981, 981, root)
            with (
                patch.object(linux_greeter, "GREETD_CONFIG_PATH", config),
                patch.object(linux_greeter, "STATE_PATH", state_path),
                patch.object(linux_greeter, "GREETD_WRAPPER_PATH", wrapper_path),
                patch.object(
                    linux_greeter,
                    "_runtime_launcher",
                    return_value=Path("/usr/local/bin/axidev-osk"),
                ),
                patch.object(linux, "_resolve_account", return_value=account),
            ):
                prepared_account, details = linux_greeter._prepare_greetd(
                    Path("/usr/local/bin/axidev-osk")
                )
                linux_greeter._install_manager(
                    "greetd",
                    linux_greeter._manager_adapter("greetd"),
                    prepared_account,
                    Path("/usr/local/bin/axidev-osk"),
                    details,
                )
                state = json.loads(state_path.read_text(encoding="utf-8"))
                self.assertNotIn("line_index", state)
                self.assertEqual(
                    linux_greeter._parse_greetd_config(config.read_text(encoding="utf-8")).command,
                    linux_greeter.MANAGED_GREETD_COMMAND,
                )
                managed = config.read_text(encoding="utf-8")
                self.assertIn(linux_greeter.MANAGED_GREETD_COMMENT, managed)
                managed_config = linux_greeter._parse_greetd_config(managed)
                self.assertLess(
                    managed.index(linux_greeter.MANAGED_GREETD_COMMENT),
                    managed.index(managed_config.original_line),
                )

                config.write_text("# added later\n" + managed, encoding="utf-8")

                linux_greeter._manager_adapter("greetd").remove(
                    Path("/usr/local/bin/axidev-osk"), state
                )

            self.assertEqual(prepared_account.name, account.name)
            self.assertEqual(config.read_text(encoding="utf-8"), "# added later\n" + self.CONFIG)


class NativeAdapterTests(unittest.TestCase):
    def test_plasma_service_stops_with_greeter_target(self) -> None:
        text = linux_greeter._plasma_service_text()

        self.assertIn("PartOf=plasma-login-wayland.target", text)
        self.assertIn(str(linux_greeter.NATIVE_SUPERVISOR_PATH), text)

    def test_lightdm_uses_native_greeter_wrapper(self) -> None:
        wrapper = linux_greeter._lightdm_wrapper_text(Path("/opt/axidev-osk/bin/axidev-osk"))

        self.assertLess(wrapper.index('"$@" &'), wrapper.index("run-greeter-keyboard"))
        self.assertIn("--parent-pid", wrapper)
        self.assertIn('"$@"', wrapper)

    def test_lightdm_reads_effective_config_from_stderr(self) -> None:
        completed = Mock(returncode=0, stdout="", stderr="A  greeter-wrapper=/managed/wrapper\n")

        with (
            patch.object(linux_greeter.shutil, "which", return_value="/usr/bin/lightdm"),
            patch.object(linux_greeter.subprocess, "run", return_value=completed),
        ):
            result = linux_greeter._lightdm_effective_wrapper()

        self.assertEqual(result, "/managed/wrapper")

    def test_greetd_wrapper_starts_original_command_first(self) -> None:
        wrapper = linux_greeter._greetd_wrapper_text(
            Path("/opt/axidev-osk/bin/axidev-osk"), "dbus-run-session compositor -- greeter"
        )

        self.assertLess(wrapper.index("/bin/sh -c"), wrapper.index("run-greeter-keyboard"))
        self.assertIn("--discover-display", wrapper)

    def test_conflicting_native_file_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "owned.conf"
            path.write_text("different\n", encoding="utf-8")

            with self.assertRaisesRegex(linux.LinuxSetupError, "conflicting"):
                linux_greeter._require_compatible_file(path, "expected\n")


class DisplayDiscoveryTests(unittest.TestCase):
    def test_discovers_unique_wayland_environment(self) -> None:
        environments = {
            11: {"XDG_RUNTIME_DIR": "/run/user/981", "WAYLAND_DISPLAY": "wayland-1"},
            12: {"XDG_RUNTIME_DIR": "/run/user/981", "WAYLAND_DISPLAY": "wayland-1"},
        }
        with (
            patch.object(linux_greeter, "_descendant_pids", return_value=[11, 12]),
            patch.object(
                linux_greeter,
                "_read_process_environment",
                side_effect=lambda pid: environments[pid],
            ),
            patch.dict(linux_greeter.os.environ, {}, clear=True),
        ):
            result = linux_greeter._discover_display_environment(10)

        assert result is not None
        self.assertEqual(result["WAYLAND_DISPLAY"], "wayland-1")

    def test_discovers_unique_x11_environment(self) -> None:
        environment = {"DISPLAY": ":0", "XAUTHORITY": "/run/lightdm/root/:0"}
        with (
            patch.object(linux_greeter, "_descendant_pids", return_value=[11]),
            patch.object(linux_greeter, "_read_process_environment", return_value=environment),
            patch.dict(linux_greeter.os.environ, {}, clear=True),
        ):
            result = linux_greeter._discover_display_environment(10)

        assert result is not None
        self.assertEqual(result["DISPLAY"], ":0")
        self.assertEqual(result["XAUTHORITY"], "/run/lightdm/root/:0")

    def test_multiple_displays_fail_closed(self) -> None:
        environments = {
            11: {"XDG_RUNTIME_DIR": "/run/user/981", "WAYLAND_DISPLAY": "wayland-1"},
            12: {"DISPLAY": ":0", "XAUTHORITY": "/run/lightdm/root/:0"},
        }
        with (
            patch.object(linux_greeter, "_descendant_pids", return_value=[11, 12]),
            patch.object(
                linux_greeter,
                "_read_process_environment",
                side_effect=lambda pid: environments[pid],
            ),
        ):
            with self.assertRaisesRegex(linux.LinuxSetupError, "multiple"):
                linux_greeter._discover_display_environment(10)


class SupervisorTests(unittest.TestCase):
    def test_process_identity_allows_spaces_in_command_name(self) -> None:
        stat = "123 (greeter process) S " + " ".join(str(value) for value in range(4, 30))
        with patch.object(linux_greeter, "Path") as path:
            path.return_value.read_text.return_value = stat

            identity = linux_greeter._process_identity(123)

        self.assertEqual(identity, "22")

    def test_keyboard_failure_uses_exponential_backoff(self) -> None:
        first = Mock()
        first.poll.return_value = 7
        second = Mock()
        second.poll.return_value = 8
        supervisor = linux_greeter._KeyboardSupervisor("plasma-login", {})
        supervisor.process = first
        supervisor.started_at = 0.0
        with patch.object(linux_greeter, "_log_error") as log:
            supervisor.tick(0.5)
            self.assertEqual(supervisor.next_start, 1.5)
            supervisor.process = second
            supervisor.started_at = 1.5
            supervisor.tick(2.0)

        self.assertEqual(supervisor.next_start, 4.0)
        self.assertEqual(log.call_count, 2)

    def test_healthy_runtime_resets_backoff(self) -> None:
        process = Mock()
        process.poll.return_value = 3
        supervisor = linux_greeter._KeyboardSupervisor("plasma-login", {})
        supervisor.process = process
        supervisor.started_at = 0.0
        supervisor.delay_index = 5
        with patch.object(linux_greeter, "_log_error"):
            supervisor.tick(linux_greeter.HEALTHY_RUNTIME_SECONDS)

        self.assertEqual(supervisor.next_start, linux_greeter.HEALTHY_RUNTIME_SECONDS + 1.0)

    def test_attached_supervisor_does_not_stop_parent(self) -> None:
        identities = iter(("100", "100", None))
        with (
            patch.object(linux_greeter, "_process_identity", side_effect=lambda _pid: next(identities)),
            patch.object(linux_greeter, "_install_signal_handlers", return_value={}),
            patch.object(linux_greeter, "_restore_signal_handlers"),
            patch.object(linux_greeter, "_log_error"),
            patch.object(linux_greeter.time, "sleep"),
        ):
            result = linux_greeter._run_attached_supervisor("lightdm", 42, {"DISPLAY": ":0"})

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
