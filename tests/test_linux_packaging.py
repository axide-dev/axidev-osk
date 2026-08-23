from __future__ import annotations

import importlib.util
import json
import sys
import tarfile
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


BUILD_SUPPORT = Path(__file__).resolve().parents[1] / "packaging" / "linux" / "build_support"
sys.path.insert(0, str(BUILD_SUPPORT))

import payload  # noqa: E402
import vm  # noqa: E402
from common import sha256  # noqa: E402


LAUNCH_PATH = BUILD_SUPPORT.parent / "resources" / "launch.py"
INSTALLER_PATH = BUILD_SUPPORT.parent / "install.sh"
LAUNCH_SPEC = importlib.util.spec_from_file_location("axidev_osk_linux_launch", LAUNCH_PATH)
assert LAUNCH_SPEC is not None and LAUNCH_SPEC.loader is not None
launch = importlib.util.module_from_spec(LAUNCH_SPEC)
LAUNCH_SPEC.loader.exec_module(launch)


class LinuxPackagingTests(unittest.TestCase):
    def test_vm_docs_require_visible_manual_acceptance(self) -> None:
        documentation = (BUILD_SUPPORT.parent / "README.md").read_text(encoding="utf-8")

        self.assertIn("manual acceptance test", documentation)
        self.assertIn("Do not replace the GTK display with `-display none`", documentation)
        self.assertIn("it must report the profile as untested", documentation)
        self.assertIn("GitHub issue #35", documentation)
        self.assertIn("hides the keyboard in the workspace switcher", documentation)

    def test_upgrade_releases_parent_lock_before_starting_new_installer(self) -> None:
        installer = INSTALLER_PATH.read_text(encoding="utf-8")

        self.assertLess(
            installer.index("flock -u 9"),
            installer.index('bash "${temp}/${INSTALLER_NAME}"'),
        )

    def test_rollback_verifies_retained_payload_before_swap(self) -> None:
        installer = INSTALLER_PATH.read_text(encoding="utf-8")

        self.assertLess(
            installer.index('"${BACKUP_PREFIX}/bin/axidev-osk" --verify-runtime'),
            installer.index('mv "${INSTALL_PREFIX}" "${temporary}"'),
        )

    def test_vm_cloud_config_authorizes_test_key(self) -> None:
        public_key = "ssh-ed25519 test-key test-comment"

        cloud_config = vm._cloud_config("hyprland", public_key, "a" * 64)

        self.assertIn(public_key, cloud_config)
        self.assertIn("axidev-osk-install install", cloud_config)
        self.assertIn("--checksum " + "a" * 64, cloud_config)
        self.assertIn("1920x1080@60", cloud_config)
        self.assertIn("monitor = Virtual-1,1920x1080@60,auto,1", cloud_config)
        self.assertIn("scale    = 1", cloud_config)
        self.assertIn("hl.exec_cmd(\\\"/usr/local/bin/axidev-osk\\\")", cloud_config)
        self.assertIn("mount -t 9p -o trans=virtio,ro", cloud_config)
        self.assertLess(cloud_config.index("mount -t 9p"), cloud_config.index("pacman -Syu"))
        self.assertLess(cloud_config.index("modprobe uinput"), cloud_config.index("pacman -Syu"))
        self.assertIn("umount /run/axidev-osk-install-source", cloud_config)
        self.assertIn(
            "[systemd-run, --on-active=5s, --unit=axidev-osk-vm-reboot, systemctl, reboot]",
            cloud_config,
        )
        self.assertNotIn("mounts:", cloud_config)
        self.assertNotIn("\\'", cloud_config)

    def test_kde_profile_installs_its_display_manager(self) -> None:
        self.assertIn("plasmalogin.service", " ".join(vm._desktop_commands("kde")))

    def test_xdg_desktops_configure_installed_autostart(self) -> None:
        for profile in ("kde", "gnome", "lightdm-x11"):
            with self.subTest(profile=profile):
                cloud_config = vm._cloud_config(profile, "ssh-ed25519 test", "a" * 64)
                self.assertIn("axidev-osk linux setup-autostart --user axidev", cloud_config)

        hyprland = vm._cloud_config("hyprland", "ssh-ed25519 test", "a" * 64)
        self.assertNotIn("linux setup-autostart", hyprland)

    def test_supported_profiles_configure_their_greeter(self) -> None:
        expected = {
            "hyprland": "greetd",
            "kde": "plasma-login",
            "lightdm-x11": "lightdm",
        }
        for profile, manager in expected.items():
            with self.subTest(profile=profile):
                cloud_config = vm._cloud_config(profile, "ssh-ed25519 test", "a" * 64)
                self.assertIn(
                    f"axidev-osk linux setup-greeter --manager {manager}", cloud_config
                )

        gnome = vm._cloud_config("gnome", "ssh-ed25519 test", "a" * 64)
        self.assertNotIn("linux setup-greeter", gnome)

    def test_lightdm_profile_installs_xorg_and_xfce(self) -> None:
        commands = " ".join(vm._desktop_commands("lightdm-x11"))

        self.assertIn("lightdm-gtk-greeter", commands)
        self.assertIn("xorg-server", commands)
        self.assertIn("xorg-xrandr", commands)
        self.assertIn("xfce4", commands)
        self.assertIn("display-setup-script", commands)

    def test_vm_prepare_install_source_archives_payload_and_installer(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload_tree = root / "payload"
            launcher = payload_tree / "bin" / "axidev-osk"
            launcher.parent.mkdir(parents=True)
            launcher.write_bytes(b"launcher")
            (payload_tree / "release.json").write_text("{}\n", encoding="utf-8")

            with patch.object(vm, "VM_ROOT", root / "vm"):
                checksum = vm._prepare_install_source("hyprland", payload_tree)
                source = vm.VM_ROOT / "hyprland" / vm.INSTALL_SOURCE_NAME

            archive = source / vm.PAYLOAD_ARCHIVE_NAME
            self.assertEqual(checksum, sha256(archive))
            self.assertTrue((source / vm.INSTALLER_NAME).is_file())
            with tarfile.open(archive) as bundle:
                self.assertIn("axidev-osk/bin/axidev-osk", bundle.getnames())

    def test_vm_ssh_command_uses_profile_port_and_cached_key(self) -> None:
        command = vm._ssh_command("kde", {"ssh_port": 22222}, ["--", "uname", "-a"])

        self.assertIn(str(vm.CACHED_PRIVATE_KEY), command)
        self.assertIn("22222", command)
        self.assertEqual(command[-2:], ["uname", "-a"])

    def test_release_lock_does_not_pin_host_qt(self) -> None:
        lock_path = BUILD_SUPPORT.parent / "release-lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))

        self.assertNotIn("qt", lock)
        self.assertNotIn("layer_shell_qt", lock)
        self.assertNotIn("compliance_sources", lock)

    def test_runtime_gate_accepts_supported_qt_versions(self) -> None:
        self.assertEqual(launch._require_supported_qt("Qt", "6.7.0"), (6, 7, 0))
        self.assertEqual(launch._require_supported_qt("Qt", "6.9.3"), (6, 9, 3))

    def test_runtime_gate_rejects_unsupported_qt_versions(self) -> None:
        for version in ("6.6.9", "7.0.0"):
            with self.subTest(version=version), self.assertRaisesRegex(
                SystemExit, "unsupported"
            ):
                launch._require_supported_qt("Qt", version)

    def test_repository_source_archives_include_tracked_submodule_files(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            source = root / "vendor" / "backend.c"
            output.mkdir()
            source.parent.mkdir()
            source.write_bytes(b"tracked source\n")
            completed = SimpleNamespace(stdout=b"vendor/backend.c\0")

            with (
                patch.object(payload, "ROOT", root),
                patch.object(payload.subprocess, "run", return_value=completed),
            ):
                versioned, stable = payload._repository_source_archives(output, "1.2.3")

            self.assertTrue(stable.is_file())
            self.assertEqual(versioned.read_bytes(), stable.read_bytes())
            with zipfile.ZipFile(versioned) as archive:
                self.assertEqual(
                    archive.read("axidev-osk/vendor/backend.c"), b"tracked source\n"
                )

    def test_release_assets_use_checksums_without_signing(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"

            def build_test_payload(namespace: SimpleNamespace) -> int:
                payload_tree = Path(namespace.output) / payload.PAYLOAD_NAME
                payload_tree.mkdir(parents=True)
                (payload_tree / "release.json").write_text("{}\n", encoding="utf-8")
                return 0

            def build_test_sources(assets: Path, version: str) -> tuple[Path, Path]:
                versioned = assets / f"axidev-osk-{version}-source.zip"
                stable = assets / "axidev-osk-source.zip"
                versioned.write_bytes(b"versioned source")
                stable.write_bytes(b"stable source")
                return versioned, stable

            namespace = SimpleNamespace(output=str(output), engine="docker")
            with (
                patch.object(payload, "build_payload", side_effect=build_test_payload),
                patch.object(payload, "project_version", return_value="1.2.3"),
                patch.object(
                    payload,
                    "_repository_source_archives",
                    side_effect=build_test_sources,
                ),
            ):
                result = payload.build_release(namespace)

            assets = output / "release-assets"
            manifest = (assets / "SHA256SUMS").read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertFalse((assets / "SHA256SUMS.minisig").exists())
            self.assertNotIn("MINISIGN", (assets / "axidev-osk-install").read_text())
            for filename in (
                "axidev-osk-1.2.3-linux-x86_64.tar.gz",
                "axidev-osk-linux-x86_64.tar.gz",
                "axidev-osk-1.2.3-source.zip",
                "axidev-osk-source.zip",
                "axidev-osk-install",
                "axidev-osk-windows-install.ps1",
            ):
                self.assertIn(f"{sha256(assets / filename)}  {filename}\n", manifest)

    def test_release_tag_must_match_project_version(self) -> None:
        namespace = SimpleNamespace(
            output=None,
            engine="docker",
            release_version="v2.0.0",
        )
        with (
            patch.object(payload, "project_version", return_value="1.2.3"),
            patch.object(payload, "build_payload") as build_payload,
            self.assertRaisesRegex(payload.BuildError, "does not match"),
        ):
            payload.build_release(namespace)

        build_payload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
