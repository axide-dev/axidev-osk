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
    PLASMA_KWIN_UNIT = (
        "[Unit]\n"
        "Description=KDE Window Manager\n"
        "[Service]\n"
        "ExecStart=/usr/bin/kwin_wayland --no-lockscreen --inputmethod plasma-keyboard --locale1\n"
    )

    def test_installed_launcher_resolves_fallback_symlink_outside_path(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = root / "opt" / "axidev-osk"
            installed.parent.mkdir()
            installed.write_text("launcher", encoding="utf-8")
            fallback = root / "usr" / "local" / "bin" / "axidev-osk"
            fallback.parent.mkdir(parents=True)
            fallback.symlink_to(installed)

            with (
                patch.object(linux_greeter, "DEFAULT_LAUNCHER_PATH", fallback),
                patch.object(linux_greeter.shutil, "which", return_value=None),
            ):
                self.assertEqual(linux_greeter._installed_launcher(), installed)
                self.assertEqual(linux_greeter._runtime_launcher(), installed)

    def test_plasma_input_method_uses_installed_launcher(self) -> None:
        launcher = Path("/opt/axidev-osk/bin/axidev-osk")
        text = linux_greeter._plasma_input_method_text(launcher)

        self.assertIn(f"Exec={launcher} internal plasma-lock-supervisor\n", text)
        self.assertIn("X-KDE-Wayland-VirtualKeyboard=true", text)

    def test_plasma_upgrade_accepts_only_exact_previous_launcher_files(self) -> None:
        launcher = Path("/opt/axidev-osk/bin/axidev-osk")
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "input-method.desktop"
            path.write_text(
                linux_greeter._previous_plasma_input_method_text(launcher),
                encoding="utf-8",
            )

            linux_greeter._require_compatible_file(
                path,
                linux_greeter._plasma_input_method_text(launcher),
                linux_greeter._previous_plasma_input_method_text(launcher),
            )
            path.write_text("unmanaged\n", encoding="utf-8")
            with self.assertRaisesRegex(linux.LinuxSetupError, "conflicting file"):
                linux_greeter._require_compatible_file(
                    path,
                    linux_greeter._plasma_input_method_text(launcher),
                    linux_greeter._previous_plasma_input_method_text(launcher),
                )

    def test_plasma_supervisor_upgrade_replaces_exact_previous_files(self) -> None:
        launcher = Path("/opt/axidev-osk/bin/axidev-osk")
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_method = root / "input-method.desktop"
            dropin = root / "kwin.service.d" / "50-axidev-osk.conf"
            unit = root / "kwin.service"
            unit.write_text(self.PLASMA_KWIN_UNIT, encoding="utf-8")
            dropin.parent.mkdir()
            with (
                patch.object(linux_greeter, "PLASMA_INPUT_METHOD_PATH", input_method),
                patch.object(linux_greeter, "PLASMA_KWIN_DROPIN_PATH", dropin),
                patch.object(linux_greeter, "PLASMA_KWIN_UNIT_PATHS", (unit,)),
            ):
                input_method.write_text(
                    linux_greeter._previous_plasma_input_method_text(launcher),
                    encoding="utf-8",
                )
                dropin.write_text(
                    linux_greeter._previous_plasma_kwin_dropin_text(launcher),
                    encoding="utf-8",
                )

                self.assertTrue(
                    linux_greeter._upgrade_plasma_supervisor_files(launcher)
                )
                self.assertEqual(
                    input_method.read_text(encoding="utf-8"),
                    linux_greeter._plasma_input_method_text(launcher),
                )
                self.assertEqual(
                    dropin.read_text(encoding="utf-8"),
                    linux_greeter._plasma_kwin_dropin_text(launcher),
                )
                self.assertFalse(
                    linux_greeter._upgrade_plasma_supervisor_files(launcher)
                )

    def test_plasma_kwin_config_preserves_unmanaged_content(self) -> None:
        original = (
            "# keep\n"
            "[Wayland]\n"
            "InputMethod=/usr/share/applications/other.desktop\n"
            "Unmanaged=value\n"
            "[Other]\n"
            "VirtualKeyboardMode=1\n"
        )

        managed = linux_greeter._plasma_kwin_config_text(original)

        self.assertIn("# keep\n", managed)
        self.assertIn("Unmanaged=value\n", managed)
        self.assertIn("[Other]\nVirtualKeyboardMode=1\n", managed)
        self.assertEqual(managed.count("InputMethod="), 1)
        self.assertIn(f"InputMethod={linux_greeter.PLASMA_INPUT_METHOD_PATH}\n", managed)
        self.assertIn("VirtualKeyboardMode=2\n", managed)

    def test_plasma_kwin_dropin_replaces_only_input_method(self) -> None:
        with TemporaryDirectory() as temporary:
            unit = Path(temporary) / "plasma-login-kwin_wayland.service"
            unit.write_text(self.PLASMA_KWIN_UNIT, encoding="utf-8")
            launcher = Path("/opt/axidev-osk/bin/axidev-osk")

            with patch.object(linux_greeter, "PLASMA_KWIN_UNIT_PATHS", (unit,)):
                dropin = linux_greeter._plasma_kwin_dropin_text(launcher)

        self.assertIn("ExecStart=\n", dropin)
        self.assertIn("--inputmethod", dropin)
        self.assertIn(f"{launcher} internal plasma-login-worker", dropin)
        self.assertNotIn("AXIDEV_OSK_GREETER", dropin)
        self.assertIn("--no-lockscreen", dropin)
        self.assertIn("--locale1", dropin)
        self.assertNotIn("--inputmethod plasma-keyboard", dropin)

    def test_plasma_lock_screen_patch_is_additive_and_reversible(self) -> None:
        original = (
            "Item {\n"
            "    MouseArea {\n"
            "        id: lockScreenRoot\n\n"
            "        property bool uiVisible: false\n"
            "    }\n"
            "    Item {\n"
            "    }\n"
            "    RowLayout {\n"
            "            PlasmaComponents3.ToolButton {\n"
            "                id: virtualKeyboardButton\n"
            "            }\n"
            "    }\n"
            "}\n"
        )

        managed = linux_greeter._plasma_lock_screen_ui_text(original)

        self.assertIn(linux_greeter.PLASMA_LOCK_SCREEN_IMPORT_PATCH, managed)
        self.assertIn(linux_greeter.PLASMA_LOCK_SCREEN_ROOT_PATCH, managed)
        self.assertIn(linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH, managed)
        self.assertLess(managed.index("id: axidevOskButton"), managed.index("id: virtualKeyboardButton"))
        self.assertEqual(linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH.count("inputPanel.showHide()"), 1)
        self.assertIn("DBus.SessionBus.asyncCall", linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH)
        self.assertEqual(
            linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH.count(
                'iface: "org.axidev.OSK.LockScreen"'
            ),
            2,
        )
        self.assertIn('member: "prepare"', linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH)
        self.assertIn('member: "release"', linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH)
        self.assertIn("reply.error.message", linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH)
        self.assertIn("target: mainBlock", linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH)
        self.assertIn("function onPasswordResult(password)", linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH)
        self.assertIn(
            "Keyboards.KWinVirtualKeyboard.mode = 2",
            linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH,
        )
        self.assertIn("onVisibleChanged", linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH)
        self.assertIn(
            "previousVirtualKeyboardMode",
            linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH,
        )
        self.assertIn(
            "inputPanel.keyboardActive || previousVirtualKeyboardMode >= 0",
            linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH,
        )
        self.assertIn("target: authenticator", linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH)
        self.assertIn("function onSucceeded()", linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH)
        self.assertNotIn("target: root", linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH)
        self.assertNotIn("Component.onDestruction", linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH)
        self.assertEqual(linux_greeter._plasma_lock_screen_ui_text(managed), managed)
        self.assertEqual(linux_greeter._plasma_lock_screen_ui_without_patch(managed), original)

        changed = managed.replace(
            "import org.kde.plasma.workspace.dbus as DBus\n",
            "changed import\n",
        ).replace(
            "            target: lockScreenRoot\n",
            "            changed root\n",
        ).replace(
            "                text: \"Axidev OSK\"\n",
            "                changed button\n",
        )
        self.assertEqual(linux_greeter._plasma_lock_screen_ui_text(changed), managed)
        self.assertEqual(linux_greeter._plasma_lock_screen_ui_without_patch(changed), original)

    def test_plasma_lock_screen_patch_migrates_v0173_block(self) -> None:
        original = (
            "Item {\n"
            "    MouseArea {\n"
            "        id: lockScreenRoot\n"
            "    }\n"
            "    RowLayout {\n"
            "            PlasmaComponents3.ToolButton {\n"
            "                id: virtualKeyboardButton\n"
            "            }\n"
            "    }\n"
            "}\n"
        )
        v0173 = original.replace(
            "        id: lockScreenRoot\n",
            "        id: lockScreenRoot\n\n" + linux_greeter.PLASMA_LOCK_SCREEN_V0173_PATCH,
        )

        managed = linux_greeter._plasma_lock_screen_ui_text(v0173)

        self.assertNotIn(linux_greeter.PLASMA_LOCK_SCREEN_V0173_PATCH, managed)
        self.assertIn(linux_greeter.PLASMA_LOCK_SCREEN_IMPORT_PATCH, managed)
        self.assertIn(linux_greeter.PLASMA_LOCK_SCREEN_ROOT_PATCH, managed)
        self.assertIn(linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH, managed)
        self.assertEqual(linux_greeter._plasma_lock_screen_ui_without_patch(v0173), original)

    def test_plasma_lock_screen_patch_rejects_incomplete_markers(self) -> None:
        changed = (
            "Item {\n"
            "    MouseArea {\n"
            "        id: lockScreenRoot\n"
            "        // BEGIN AXIDEV OSK ROOT MANAGED\n"
            "        changed content\n"
            "    }\n"
            "}\n"
        )

        with self.assertRaisesRegex(linux.LinuxSetupError, "marker pair"):
            linux_greeter._plasma_lock_screen_ui_text(changed)
        with self.assertRaisesRegex(linux.LinuxSetupError, "marker pair"):
            linux_greeter._plasma_lock_screen_ui_without_patch(changed)

    def test_file_transaction_restores_regular_files_atomically(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed.conf"
            path.write_text("before\n", encoding="utf-8")
            transaction = linux_greeter._FileTransaction()
            transaction.write(path, "after\n")

            with patch.object(linux, "_write_atomic", wraps=linux._write_atomic) as write:
                transaction.rollback()

        write.assert_called_once_with(path, "before\n", 0o644)

    def test_file_transaction_continues_after_atomic_restore_failure(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.conf"
            second = root / "second.conf"
            first.write_text("first before\n", encoding="utf-8")
            second.write_text("second before\n", encoding="utf-8")
            transaction = linux_greeter._FileTransaction()
            transaction.write(first, "first after\n")
            transaction.write(second, "second after\n")
            real_write = linux._write_atomic

            def restore(path: Path, contents: str, mode: int) -> None:
                if path == second:
                    raise linux.LinuxSetupError("restore failed")
                real_write(path, contents, mode)

            with patch.object(linux, "_write_atomic", side_effect=restore):
                transaction.rollback()

            self.assertEqual(first.read_text(encoding="utf-8"), "first before\n")

    def test_plasma_version_is_read_from_owning_rpm(self) -> None:
        completed = Mock(returncode=0, stdout="6.7.4")
        with (
            patch.object(
                linux_greeter.shutil,
                "which",
                side_effect=lambda command: "/usr/bin/rpm" if command == "rpm" else None,
            ),
            patch.object(linux_greeter.subprocess, "run", return_value=completed),
        ):
            version = linux_greeter._plasma_version()

        self.assertEqual(version, (6, 7, 4))

    def test_plasma_lock_screen_version_range_excludes_plasma_7(self) -> None:
        with patch.object(linux_greeter, "_plasma_version", return_value=(6, 7, 0)):
            self.assertTrue(linux_greeter._plasma_lock_screen_version_supported())
        with patch.object(linux_greeter, "_plasma_version", return_value=(6, 6, 5)):
            self.assertFalse(linux_greeter._plasma_lock_screen_version_supported())
        with patch.object(linux_greeter, "_plasma_version", return_value=(7, 0, 0)):
            self.assertFalse(linux_greeter._plasma_lock_screen_version_supported())
            with self.assertRaisesRegex(linux.LinuxSetupError, "<7.0.0"):
                linux_greeter._require_supported_plasma_lock_screen_version()

    def test_plasma_install_and_remove_restore_kwin_config(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_method = root / "axidev-osk-input-panel.desktop"
            kwin_dropin = root / "50-axidev-osk.conf"
            kwin_unit = root / "plasma-login-kwin_wayland.service"
            kwinrc = root / "kwinrc"
            lock_screen_ui = root / "LockScreenUi.qml"
            state_path = root / "greeter.json"
            original = "[Wayland]\nUnmanaged=value\n"
            original_lock_screen_ui = (
                "Item {\n"
                "    MouseArea {\n"
                "        id: lockScreenRoot\n\n"
                "        property bool uiVisible: false\n"
                "    }\n"
                "    RowLayout {\n"
                "            PlasmaComponents3.ToolButton {\n"
                "                id: virtualKeyboardButton\n"
                "            }\n"
                "    }\n"
                "}\n"
            )
            kwinrc.write_text(original, encoding="utf-8")
            lock_screen_ui.write_text(original_lock_screen_ui, encoding="utf-8")
            kwin_unit.write_text(self.PLASMA_KWIN_UNIT, encoding="utf-8")
            launcher = Path("/opt/axidev-osk/bin/axidev-osk")
            account = linux.Account("plasmalogin", 981, 981, root)

            with (
                patch.object(linux_greeter, "PLASMA_INPUT_METHOD_PATH", input_method),
                patch.object(linux_greeter, "PLASMA_KWIN_DROPIN_PATH", kwin_dropin),
                patch.object(linux_greeter, "PLASMA_KWIN_UNIT_PATHS", (kwin_unit,)),
                patch.object(linux_greeter, "KWIN_CONFIG_PATH", kwinrc),
                patch.object(linux_greeter, "PLASMA_LOCK_SCREEN_UI_PATH", lock_screen_ui),
                patch.object(linux_greeter, "STATE_PATH", state_path),
                patch.object(linux_greeter, "_plasma_version", return_value=(6, 7, 4)),
                patch.object(linux, "_resolve_account", return_value=account),
            ):
                prepared_account, details = linux_greeter._prepare_plasma(launcher)
                linux_greeter._install_manager(
                    "plasma-login",
                    linux_greeter._manager_adapter("plasma-login"),
                    prepared_account,
                    launcher,
                    details,
                )
                state = json.loads(state_path.read_text(encoding="utf-8"))
                self.assertIn("VirtualKeyboardMode=2", kwinrc.read_text(encoding="utf-8"))
                self.assertTrue(input_method.is_file())
                self.assertTrue(kwin_dropin.is_file())
                self.assertIn(
                    linux_greeter.PLASMA_LOCK_SCREEN_ROOT_PATCH,
                    lock_screen_ui.read_text(encoding="utf-8"),
                )
                self.assertIn(
                    linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH,
                    lock_screen_ui.read_text(encoding="utf-8"),
                )

                lock_screen_ui.write_text(original_lock_screen_ui, encoding="utf-8")
                kwin_dropin.write_text("changed after setup\n", encoding="utf-8")
                with patch.object(linux_greeter, "_runtime_launcher", return_value=launcher):
                    self.assertTrue(linux_greeter._repair_plasma_lock_screen_patch(state))
                self.assertIn(
                    linux_greeter.PLASMA_LOCK_SCREEN_ROOT_PATCH,
                    lock_screen_ui.read_text(encoding="utf-8"),
                )
                self.assertIn(
                    linux_greeter.PLASMA_LOCK_SCREEN_BUTTON_PATCH,
                    lock_screen_ui.read_text(encoding="utf-8"),
                )

                kwin_dropin.write_text(
                    linux_greeter._plasma_kwin_dropin_text(launcher),
                    encoding="utf-8",
                )
                linux_greeter._remove_plasma(launcher, state)

            self.assertEqual(prepared_account.name, "plasmalogin")
            self.assertEqual(kwinrc.read_text(encoding="utf-8"), original)
            self.assertFalse(input_method.exists())
            self.assertFalse(kwin_dropin.exists())
            self.assertEqual(lock_screen_ui.read_text(encoding="utf-8"), original_lock_screen_ui)

    def test_v0173_plasma_remove_keeps_working(self) -> None:
        launcher = Path("/opt/axidev-osk/bin/axidev-osk")
        state = {"schema": 1, "manager": "plasma-login", "account": "plasmalogin"}
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            supervisor = root / "supervisor"
            service = root / "service"
            wants = root / "wants"
            lock_screen_ui = root / "LockScreenUi.qml"
            original_lock_screen_ui = "Item {\n    id: lockScreenRoot\n}\n"
            with (
                patch.object(linux_greeter, "NATIVE_SUPERVISOR_PATH", supervisor),
                patch.object(linux_greeter, "PLASMA_SERVICE_PATH", service),
                patch.object(linux_greeter, "PLASMA_WANTS_PATH", wants),
                patch.object(linux_greeter, "PLASMA_LOCK_SCREEN_UI_PATH", lock_screen_ui),
            ):
                supervisor.write_text(
                    linux_greeter._native_supervisor_text(launcher), encoding="utf-8"
                )
                service.write_text(linux_greeter._plasma_service_text(), encoding="utf-8")
                wants.symlink_to(service)
                lock_screen_ui.write_text(
                    original_lock_screen_ui.replace(
                        "    id: lockScreenRoot\n",
                        "    id: lockScreenRoot\n\n"
                        + linux_greeter.PLASMA_LOCK_SCREEN_V0173_PATCH,
                    ),
                    encoding="utf-8",
                )

                linux_greeter._remove_plasma(launcher, state)

            self.assertFalse(supervisor.exists())
            self.assertFalse(service.exists())
            self.assertFalse(wants.exists())
            self.assertEqual(lock_screen_ui.read_text(encoding="utf-8"), original_lock_screen_ui)

    def test_v0173_plasma_install_migrates_owned_files_and_qml(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            supervisor = root / "supervisor"
            service = root / "service"
            wants = root / "wants"
            input_method = root / "axidev-osk-input-panel.desktop"
            kwin_dropin = root / "50-axidev-osk.conf"
            kwin_unit = root / "plasma-login-kwin_wayland.service"
            kwinrc = root / "kwinrc"
            lock_screen_ui = root / "LockScreenUi.qml"
            state_path = root / "greeter.json"
            launcher = Path("/opt/axidev-osk/bin/axidev-osk")
            account = linux.Account("plasmalogin", 981, 981, root)
            original_lock_screen_ui = (
                "Item {\n"
                "    MouseArea {\n"
                "        id: lockScreenRoot\n"
                "    }\n"
                "    RowLayout {\n"
                "            PlasmaComponents3.ToolButton {\n"
                "                id: virtualKeyboardButton\n"
                "            }\n"
                "    }\n"
                "}\n"
            )
            v0173_lock_screen_ui = original_lock_screen_ui.replace(
                "        id: lockScreenRoot\n",
                "        id: lockScreenRoot\n\n"
                + linux_greeter.PLASMA_LOCK_SCREEN_V0173_PATCH,
            )
            kwin_unit.write_text(self.PLASMA_KWIN_UNIT, encoding="utf-8")
            lock_screen_ui.write_text(v0173_lock_screen_ui, encoding="utf-8")

            with (
                patch.object(linux_greeter, "NATIVE_SUPERVISOR_PATH", supervisor),
                patch.object(linux_greeter, "PLASMA_SERVICE_PATH", service),
                patch.object(linux_greeter, "PLASMA_WANTS_PATH", wants),
                patch.object(linux_greeter, "PLASMA_INPUT_METHOD_PATH", input_method),
                patch.object(linux_greeter, "PLASMA_KWIN_DROPIN_PATH", kwin_dropin),
                patch.object(linux_greeter, "PLASMA_KWIN_UNIT_PATHS", (kwin_unit,)),
                patch.object(linux_greeter, "KWIN_CONFIG_PATH", kwinrc),
                patch.object(linux_greeter, "PLASMA_LOCK_SCREEN_UI_PATH", lock_screen_ui),
                patch.object(linux_greeter, "STATE_PATH", state_path),
                patch.object(linux_greeter, "_plasma_version", return_value=(6, 7, 4)),
                patch.object(linux, "_resolve_account", return_value=account),
            ):
                supervisor.write_text(
                    linux_greeter._native_supervisor_text(launcher), encoding="utf-8"
                )
                service.write_text(linux_greeter._plasma_service_text(), encoding="utf-8")
                wants.symlink_to(service)
                prepared_account, details = linux_greeter._prepare_plasma(launcher)
                details["v0173_plasma"] = True
                linux_greeter._install_manager(
                    "plasma-login",
                    linux_greeter._manager_adapter("plasma-login"),
                    prepared_account,
                    launcher,
                    details,
                )

            managed_lock_screen_ui = lock_screen_ui.read_text(encoding="utf-8")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertFalse(supervisor.exists())
            self.assertFalse(service.exists())
            self.assertFalse(wants.exists())
            self.assertTrue(input_method.is_file())
            self.assertTrue(kwin_dropin.is_file())
            self.assertNotIn(linux_greeter.PLASMA_LOCK_SCREEN_V0173_PATCH, managed_lock_screen_ui)
            self.assertIn(linux_greeter.PLASMA_LOCK_SCREEN_ROOT_PATCH, managed_lock_screen_ui)
            self.assertIn("original_kwinrc", state)

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
