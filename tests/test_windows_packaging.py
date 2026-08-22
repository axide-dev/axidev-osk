from __future__ import annotations

import ast
import unittest
from pathlib import Path
from xml.etree import ElementTree


REPO_ROOT = Path(__file__).resolve().parent.parent
WINDOWS_PACKAGING = REPO_ROOT / "packaging" / "windows"


class WindowsPackagingTests(unittest.TestCase):
    def test_manifest_requests_uiaccess_without_elevation(self) -> None:
        manifest = ElementTree.parse(WINDOWS_PACKAGING / "axidev-osk.manifest")
        requested_level = manifest.find(
            ".//{urn:schemas-microsoft-com:asm.v3}requestedExecutionLevel"
        )

        self.assertIsNotNone(requested_level)
        self.assertEqual(requested_level.attrib["level"], "asInvoker")
        self.assertEqual(requested_level.attrib["uiAccess"], "true")

    def test_pyinstaller_spec_enables_uiaccess(self) -> None:
        spec_path = WINDOWS_PACKAGING / "axidev-osk.spec"
        spec_tree = ast.parse(spec_path.read_text(encoding="utf-8"), filename=str(spec_path))
        executable_call = next(
            node
            for node in ast.walk(spec_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "EXE"
        )
        keywords = {keyword.arg: keyword.value for keyword in executable_call.keywords}

        self.assertIsInstance(keywords["uac_uiaccess"], ast.Constant)
        self.assertIs(keywords["uac_uiaccess"].value, True)
        self.assertIn("icon", keywords)

    def test_application_icon_assets_are_packaged(self) -> None:
        assets = REPO_ROOT / "src" / "axidev_osk" / "assets"

        self.assertTrue((assets / "axidev-osk.svg").is_file())
        self.assertTrue((assets / "axidev-osk.ico").is_file())

    def test_release_bootstrap_uses_latest_release_source(self) -> None:
        bootstrap = (
            WINDOWS_PACKAGING / "axidev-osk-windows-install.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("/releases/latest/download", bootstrap)
        self.assertIn("axidev-osk-source.zip", bootstrap)
        self.assertIn('vendor\\axidev-io-python', bootstrap)
        self.assertNotIn("refs/heads/main", bootstrap)

    def test_release_workflow_publishes_windows_bootstrap(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "cp packaging/windows/axidev-osk-windows-install.ps1 release-assets/",
            workflow,
        )

    def test_development_installer_manages_start_menu_shortcut_transaction(self) -> None:
        admin_script = (WINDOWS_PACKAGING / "development-admin.ps1").read_text(encoding="utf-8")
        install_script = (WINDOWS_PACKAGING / "install-development.ps1").read_text(encoding="utf-8")
        uninstall_script = (WINDOWS_PACKAGING / "uninstall-development.ps1").read_text(encoding="utf-8")

        self.assertIn('GetFolderPath("Programs")', install_script)
        self.assertIn('GetFolderPath("Programs")', uninstall_script)
        self.assertIn('New-Object -ComObject "WScript.Shell"', admin_script)
        self.assertIn("$ShortcutNewPath", admin_script)
        self.assertIn("$ShortcutOldPath", admin_script)
        self.assertIn("Remove-Item -LiteralPath $ShortcutPath", admin_script)

    def test_development_installer_registers_one_accessibility_application(self) -> None:
        admin_script = (WINDOWS_PACKAGING / "development-admin.ps1").read_text(encoding="utf-8")
        install_script = (WINDOWS_PACKAGING / "install-development.ps1").read_text(encoding="utf-8")

        self.assertIn('"Axidev_AxidevOSK_Development_v1.0"', admin_script)
        self.assertNotIn("SecureDesktopAccommodation", admin_script)
        self.assertNotIn("StartParams", admin_script)
        self.assertNotIn("--secure-desktop", admin_script)
        self.assertIn("Install-AccessibilityRegistration", admin_script)
        for property_name in (
            "ApplicationName",
            "Description",
            "ATExe",
            "StartExe",
            "Profile",
            "SimpleProfile",
            "TerminateOnDesktopSwitch",
        ):
            self.assertIn(f'-Name "{property_name}"', admin_script)
        self.assertIn("Backup-AccessibilityRegistration", admin_script)
        self.assertIn("Restore-AccessibilityRegistration", admin_script)
        registration_function = admin_script.split("function Install-AccessibilityRegistration", 1)[1].split(
            "function New-StartMenuShortcut", 1
        )[0]
        self.assertLess(
            registration_function.index("Remove-Item -LiteralPath $RegistrationPath"),
            registration_function.index("New-Item -ItemType Directory -Path $RegistrationPath"),
        )
        self.assertIn("Enable-AxidevAccessibilityAutoStart", install_script)
        self.assertEqual(install_script.count("-Verb RunAs"), 1)
        self.assertIn('Join-Path $TransactionPath "ready"', install_script)
        self.assertIn('Join-Path $TransactionPath "commit"', install_script)
        self.assertIn('Join-Path $TransactionPath "rollback"', install_script)

    def test_development_uninstaller_removes_only_axidev_auto_start(self) -> None:
        admin_script = (WINDOWS_PACKAGING / "development-admin.ps1").read_text(encoding="utf-8")
        uninstall_script = (WINDOWS_PACKAGING / "uninstall-development.ps1").read_text(encoding="utf-8")

        self.assertIn("Disable-AxidevAccessibilityAutoStart", uninstall_script)
        self.assertIn("$_ -ne $NormalRegistrationName", uninstall_script)
        self.assertNotIn('Join-Path $AccessibilityRoot "osk"', uninstall_script)
        self.assertLess(
            uninstall_script.rindex("Disable-AxidevAccessibilityAutoStart"),
            uninstall_script.index("$AdminProcess = Start-Process"),
        )
        uninstall_block = admin_script.split('if ($Mode -eq "Uninstall")', 1)[1].split(
            "if (-not $SourceDirectory", 1
        )[0]
        self.assertLess(
            uninstall_block.index("Remove-Item -LiteralPath $RegistrationPath"),
            uninstall_block.index("Stop-AxidevOsk"),
        )
        self.assertIn("Restore-AccessibilityRegistration $TransactionPath", uninstall_block)
        self.assertIn('Join-Path $TransactionPath "restore-configuration"', uninstall_block)
        self.assertIn('Join-Path $NativeStage "restore-configuration"', uninstall_script)


if __name__ == "__main__":
    unittest.main()
