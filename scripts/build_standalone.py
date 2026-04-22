#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "build" / "standalone"
PACKAGES_DIR = ROOT / "packages"
APP_NAME = "axidev-osk"
TOP_LEVEL_LICENSE = ROOT / "LICENSE"
TOP_LEVEL_README = ROOT / "README.md"
AXIDEV_IO_PYTHON_ROOT = ROOT / "vendor" / "axidev-io-python"
AXIDEV_IO_DOCS_ROOT = (
    ROOT
    / "vendor"
    / "axidev-io-python"
    / "src"
    / "axidev_io"
    / "vendor"
    / "axidev-io"
)


def detect_arch() -> str:
    machine = platform.machine().lower()
    mapping = {
        "amd64": "x64",
        "x86_64": "x64",
        "x64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    return mapping.get(machine, machine or "unknown")


def detect_platform_tag() -> str:
    return "windows" if os.name == "nt" else "linux"


def run_command(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, check=True, cwd=ROOT)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def copy_file(source: Path, destination: Path) -> None:
    ensure_parent(destination)
    shutil.copy2(source, destination)


def copy_tree(source_dir: Path, destination_dir: Path) -> None:
    shutil.copytree(source_dir, destination_dir, dirs_exist_ok=True)


def write_zip_tree(archive_path: Path, source_dir: Path) -> None:
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in source_dir.rglob("*"):
            if not file_path.is_file():
                continue

            archive_name = file_path.relative_to(source_dir).as_posix()
            info = zipfile.ZipInfo.from_file(file_path, archive_name)
            info.create_system = 3
            info.external_attr = (file_path.stat().st_mode & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED

            with file_path.open("rb") as handle:
                archive.writestr(info, handle.read())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a standalone axidev-osk archive.")
    parser.add_argument("--version", default="dev", help="Version label for the archive name.")
    parser.add_argument("--arch", default=detect_arch(), help="Architecture label for the archive name.")
    parser.add_argument("--clean", action="store_true", help="Remove previous standalone build outputs first.")
    return parser.parse_args()


def clean_outputs() -> None:
    for path in (BUILD_ROOT, PACKAGES_DIR):
        if path.exists():
            print(f"Removing {path}")
            shutil.rmtree(path)


def build_pyinstaller_dist(dist_dir: Path, work_dir: Path, spec_dir: Path) -> Path:
    entrypoint = ROOT / "src" / "axidev_osk" / "__main__.py"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        "--paths",
        str(ROOT / "src"),
        "--collect-all",
        "axidev_io",
        str(entrypoint),
    ]
    run_command(command)
    return dist_dir / APP_NAME


def populate_bundle_root(source_dir: Path, bundle_root: Path) -> None:
    copy_tree(source_dir, bundle_root)
    copy_file(TOP_LEVEL_README, bundle_root / "README.md")
    if TOP_LEVEL_LICENSE.is_file():
        copy_file(TOP_LEVEL_LICENSE, bundle_root / "LICENSE")

    copy_file(
        AXIDEV_IO_PYTHON_ROOT / "LICENSE",
        bundle_root / "third_party" / "axidev-io-python" / "LICENSE",
    )
    copy_file(
        AXIDEV_IO_PYTHON_ROOT / "README.md",
        bundle_root / "third_party" / "axidev-io-python" / "README.md",
    )
    copy_file(AXIDEV_IO_DOCS_ROOT / "LICENSE", bundle_root / "third_party" / "axidev-io" / "LICENSE")
    copy_file(AXIDEV_IO_DOCS_ROOT / "README.md", bundle_root / "third_party" / "axidev-io" / "README.md")
    copy_file(
        AXIDEV_IO_DOCS_ROOT / "docs" / "consumers" / "README.md",
        bundle_root / "docs" / "axidev-io" / "consumers.md",
    )
    copy_tree(
        AXIDEV_IO_DOCS_ROOT / "vendor" / "licenses",
        bundle_root / "third_party" / "axidev-io" / "vendor" / "licenses",
    )

    if os.name != "nt":
        copy_file(
            AXIDEV_IO_DOCS_ROOT / "scripts" / "setup_uinput_permissions.sh",
            bundle_root / "setup_uinput_permissions.sh",
        )


def build_archive(version: str, arch: str) -> Path:
    platform_tag = detect_platform_tag()
    archive_base = f"axidev-osk-{version}-{platform_tag}-{arch}"
    dist_dir = BUILD_ROOT / "pyinstaller-dist"
    work_dir = BUILD_ROOT / "pyinstaller-work"
    spec_dir = BUILD_ROOT / "pyinstaller-spec"
    stage_root = BUILD_ROOT / "stage"
    bundle_root = stage_root / archive_base

    if BUILD_ROOT.exists():
        shutil.rmtree(BUILD_ROOT)
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    pyinstaller_dir = build_pyinstaller_dist(dist_dir, work_dir, spec_dir)
    populate_bundle_root(pyinstaller_dir, bundle_root)

    archive_path = PACKAGES_DIR / f"{archive_base}.zip"
    write_zip_tree(archive_path, stage_root)
    print(f"Created {archive_path}")
    return archive_path


def main() -> int:
    args = parse_args()
    if args.clean:
        clean_outputs()

    build_archive(args.version, args.arch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
