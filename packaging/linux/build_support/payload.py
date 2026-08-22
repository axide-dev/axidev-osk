"""Build, verify, and release the relocatable Linux payload."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from common import (
    DEFAULT_OUTPUT,
    LINUX_DIR,
    ROOT,
    BuildError,
    load_lock,
    project_version,
    require_commands,
    run,
    sha256,
)


PAYLOAD_NAME = "axidev-osk"
IMAGE_NAME = "axidev-osk-linux-builder"
OUTPUT_VOLUME = "axidev-osk-linux-output"
ELF_MAGIC = b"\x7fELF"
WINDOWS_BOOTSTRAP = ROOT / "packaging" / "windows" / "axidev-osk-windows-install.ps1"


def _output_root(raw: str | None) -> Path:
    return Path(raw).resolve() if raw else DEFAULT_OUTPUT


def build_payload(namespace: argparse.Namespace) -> int:
    output = _output_root(namespace.output)
    if namespace.inner:
        _build_payload_inner(output)
        return 0

    lock = load_lock()
    require_commands(namespace.engine)
    output.mkdir(parents=True, exist_ok=True)

    run(
        [
            namespace.engine,
            "build",
            "--build-arg",
            f"BUILD_IMAGE={lock['container']['image']}",
            "--build-arg",
            f"RUST_VERSION={lock['rust']['version']}",
            "--tag",
            IMAGE_NAME,
            "--file",
            str(LINUX_DIR / "container" / "Dockerfile"),
            str(ROOT),
        ]
    )
    run([namespace.engine, "volume", "create", OUTPUT_VOLUME])
    run(
        [
            namespace.engine,
            "run",
            "--rm",
            "--volume",
            f"{OUTPUT_VOLUME}:/output",
            IMAGE_NAME,
            "python",
            "packaging/build.py",
            "linux",
            "payload",
            "--inner",
            "--output",
            "/output",
        ]
    )
    _copy_payload_from_volume(namespace.engine, output)
    return 0


def _copy_payload_from_volume(engine: str, output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="axidev-osk-container-output-") as raw_temp:
        temporary = Path(raw_temp)
        archive = temporary / "payload.tar"
        command = [
            engine,
            "run",
            "--rm",
            "--volume",
            f"{OUTPUT_VOLUME}:/output:ro",
            IMAGE_NAME,
            "tar",
            "-C",
            "/output",
            "-cf",
            "-",
            PAYLOAD_NAME,
        ]
        print("+", " ".join(command), flush=True)
        try:
            with archive.open("wb") as stream:
                subprocess.run(command, check=True, stdout=stream)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise BuildError("cannot copy payload from the Docker output volume") from exc

        extracted = temporary / "extracted"
        extracted.mkdir()
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                path = Path(member.name)
                if path.is_absolute() or ".." in path.parts or path.parts[0] != PAYLOAD_NAME:
                    raise BuildError(f"unsafe path in Docker payload output: {member.name}")
                if member.issym() or member.islnk():
                    raise BuildError(f"links are not allowed in Docker payload output: {member.name}")
            bundle.extractall(extracted)

        destination = output / PAYLOAD_NAME
        if destination.exists() or destination.is_symlink():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        shutil.move(extracted / PAYLOAD_NAME, destination)
        print(destination)


def _build_payload_inner(output: Path) -> None:
    lock = load_lock()
    output.mkdir(parents=True, exist_ok=True)
    final_payload = output / PAYLOAD_NAME

    with tempfile.TemporaryDirectory(prefix="axidev-osk-payload-") as raw_temp:
        temp = Path(raw_temp)
        payload = temp / PAYLOAD_NAME
        python_root = payload / "lib" / "python"

        _install_python_tree(python_root, temp)
        _build_launcher(lock, payload, temp)
        _install_payload_resources(payload)
        _write_release_metadata(payload, lock)
        verify_payload_path(payload, lock)

        if final_payload.exists() or final_payload.is_symlink():
            if final_payload.is_dir() and not final_payload.is_symlink():
                shutil.rmtree(final_payload)
            else:
                final_payload.unlink()
        shutil.copytree(payload, final_payload, symlinks=True)
    print(final_payload)


def _install_python_tree(python_root: Path, temp: Path) -> None:
    python_root.mkdir(parents=True, exist_ok=True)
    wheelhouse = temp / "wheels"
    wheelhouse.mkdir()
    run(
        [
            "python",
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(wheelhouse),
            str(ROOT / "vendor" / "axidev-io-python"),
        ],
        cwd=temp,
    )
    run(
        [
            "python",
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(wheelhouse),
            str(ROOT),
        ],
        cwd=temp,
    )
    wheels = sorted(wheelhouse.glob("*.whl"))
    if len(wheels) != 2:
        raise BuildError("payload build did not produce both project wheels")

    run(
        [
            "python",
            "-m",
            "pip",
            "install",
            "--no-compile",
            "--no-index",
            "--no-deps",
            "--target",
            str(python_root),
            *map(str, wheels),
        ]
    )
    shutil.rmtree(python_root / "bin", ignore_errors=True)


def _is_elf(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with path.open("rb") as stream:
            return stream.read(4) == ELF_MAGIC
    except OSError as exc:
        raise BuildError(f"cannot inspect {path}: {exc}") from exc


def _build_launcher(lock: dict[str, Any], payload: Path, temp: Path) -> None:
    target_dir = temp / "cargo-target"
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(target_dir)
    run(
        [
            "cargo",
            "build",
            "--locked",
            "--release",
            "--manifest-path",
            str(LINUX_DIR / "launcher" / "Cargo.toml"),
            "--target",
            lock["rust"]["target"],
        ],
        env=env,
    )
    source = target_dir / lock["rust"]["target"] / "release" / "axidev-osk"
    target = payload / "bin" / "axidev-osk"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    target.chmod(0o755)


def _install_payload_resources(payload: Path) -> None:
    libexec = payload / "libexec"
    applications = payload / "share" / "applications"
    icons = payload / "share" / "icons" / "hicolor" / "scalable" / "apps"
    licenses = payload / "share" / "licenses"
    for directory in (libexec, applications, icons, licenses):
        directory.mkdir(parents=True, exist_ok=True)

    shutil.copy2(LINUX_DIR / "resources" / "launch.py", libexec / "launch.py")
    shutil.copy2(
        LINUX_DIR / "resources" / "axidev-osk.desktop",
        applications / "axidev-osk.desktop",
    )
    shutil.copy2(
        ROOT / "src" / "axidev_osk" / "assets" / "axidev-osk.svg",
        icons / "axidev-osk.svg",
    )
    shutil.copy2(ROOT / "LICENSE", licenses / "LICENSE.axidev-osk")
    shutil.copy2(
        ROOT / "vendor" / "axidev-io-python" / "LICENSE",
        licenses / "LICENSE.axidev-io-python",
    )
    vendor_licenses = ROOT / "vendor" / "axidev-io-python" / "vendor" / "axidev-io" / "vendor" / "licenses"
    shutil.copytree(vendor_licenses, licenses / "axidev-io-vendor", dirs_exist_ok=True)

    for package in (payload / "lib" / "python").glob("*.dist-info"):
        for candidate in (*package.glob("LICENSE*"), *package.glob("licenses/*")):
            if candidate.is_file():
                destination = licenses / package.name / candidate.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, destination)


def _write_release_metadata(payload: Path, lock: dict[str, Any]) -> None:
    files: dict[str, str] = {}
    for path in sorted(payload.rglob("*")):
        if path.is_file() and not path.is_symlink():
            files[path.relative_to(payload).as_posix()] = sha256(path)
    metadata = {
        "schema": 1,
        "version": project_version(),
        "architecture": lock["architecture"],
        "glibc_minimum": lock["glibc_minimum"],
        "host_runtime": {
            "python": ">=3.10",
            "pyside6": ">=6.7,<7",
            "qt": ">=6.7,<7",
            "layer_shell_qt": "matching Qt ABI",
        },
        "files": files,
    }
    (payload / "release.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def verify_payload(namespace: argparse.Namespace) -> int:
    path = Path(namespace.payload).resolve() if namespace.payload else DEFAULT_OUTPUT / PAYLOAD_NAME
    verify_payload_path(path, load_lock())
    print(f"verified {path}")
    return 0


def _elf_files(payload: Path) -> list[Path]:
    result: list[Path] = []
    for path in payload.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            with path.open("rb") as stream:
                magic = stream.read(4)
            if magic == ELF_MAGIC:
                result.append(path)
        except OSError as exc:
            raise BuildError(f"cannot inspect {path}: {exc}") from exc
    return result


def verify_payload_path(payload: Path, lock: dict[str, Any]) -> None:
    if not payload.is_dir():
        raise BuildError(f"payload directory does not exist: {payload}")
    metadata_path = payload / "release.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f"invalid payload metadata: {exc}") from exc

    for relative, expected in metadata.get("files", {}).items():
        candidate = payload / relative
        if not candidate.is_file() or sha256(candidate) != expected:
            raise BuildError(f"payload file failed verification: {relative}")

    launcher = payload / "bin" / "axidev-osk"
    dynamic = subprocess.run(["ldd", str(launcher)], capture_output=True, text=True)
    launcher_output = f"{dynamic.stdout}\n{dynamic.stderr}".lower()
    if "not a dynamic executable" not in launcher_output and "statically linked" not in launcher_output:
        raise BuildError("Rust launcher is not statically linked")

    allowed = set(lock["system_libraries"])
    private_roots = (payload.resolve(),)
    external_dependencies: dict[str, set[str]] = {}
    for elf in _elf_files(payload):
        if elf == launcher:
            continue
        result = subprocess.run(["ldd", str(elf)], capture_output=True, text=True)
        output = f"{result.stdout}\n{result.stderr}"
        for line in output.splitlines():
            match = re.match(r"\s*(\S+)\s+=>\s+(\S+)", line)
            if not match:
                continue
            library, resolved = match.groups()
            if resolved == "not":
                if library in allowed:
                    continue
                raise BuildError(f"unresolved dependency {library} for {elf}")
            resolved_path = Path(resolved)
            if any(root in resolved_path.resolve().parents for root in private_roots):
                continue
            if library not in allowed:
                external_dependencies.setdefault(library, set()).add(
                    elf.relative_to(payload).as_posix()
                )

    if external_dependencies:
        details = "\n".join(
            f"  {library}: {', '.join(sorted(users))}"
            for library, users in sorted(external_dependencies.items())
        )
        raise BuildError(f"external dependencies are not allowlisted:\n{details}")


def _archive_tree(source: Path, destination: Path, arcname: str) -> None:
    with tarfile.open(destination, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        archive.add(source, arcname=arcname, recursive=True)


def _repository_source_archives(output: Path, version: str) -> tuple[Path, Path]:
    versioned = output / f"axidev-osk-{version}-source.zip"
    stable = output / "axidev-osk-source.zip"
    try:
        result = subprocess.run(
            ["git", "ls-files", "--recurse-submodules", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BuildError("cannot enumerate tracked repository sources") from exc

    with zipfile.ZipFile(versioned, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for raw_relative in result.stdout.split(b"\0"):
            if not raw_relative:
                continue
            relative = Path(os.fsdecode(raw_relative))
            source = ROOT / relative
            if source.is_file():
                archive.write(source, (Path("axidev-osk") / relative).as_posix())
    shutil.copy2(versioned, stable)
    return versioned, stable


def build_release(namespace: argparse.Namespace) -> int:
    output = _output_root(namespace.output)
    payload_namespace = argparse.Namespace(output=str(output), engine=namespace.engine, inner=False)
    build_payload(payload_namespace)
    version = project_version()
    assets = output / "release-assets"
    assets.mkdir(parents=True, exist_ok=True)

    payload_archive = assets / f"axidev-osk-{version}-linux-x86_64.tar.gz"
    _archive_tree(output / PAYLOAD_NAME, payload_archive, PAYLOAD_NAME)
    stable_payload = assets / "axidev-osk-linux-x86_64.tar.gz"
    shutil.copy2(payload_archive, stable_payload)
    source_archives = _repository_source_archives(assets, version)
    installer = assets / "axidev-osk-install"
    installer.write_text(
        (LINUX_DIR / "install.sh").read_text(encoding="utf-8"), encoding="utf-8"
    )
    installer.chmod(0o755)
    windows_bootstrap = assets / WINDOWS_BOOTSTRAP.name
    shutil.copy2(WINDOWS_BOOTSTRAP, windows_bootstrap)

    release_assets = (
        payload_archive,
        stable_payload,
        *source_archives,
        installer,
        windows_bootstrap,
    )
    sums = assets / "SHA256SUMS"
    sums.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in release_assets),
        encoding="utf-8",
    )
    print(assets)
    return 0
