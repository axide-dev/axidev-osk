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


if __name__ == "__main__":
    unittest.main()
