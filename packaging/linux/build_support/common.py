"""Shared primitives for reproducible Linux packaging."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from urllib.error import URLError
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
LINUX_DIR = ROOT / "packaging" / "linux"
LOCK_PATH = LINUX_DIR / "release-lock.json"
DEFAULT_OUTPUT = ROOT / "dist" / "linux"
CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "axidev-osk"


class BuildError(RuntimeError):
    """Raised when a build command cannot produce a trustworthy result."""


def load_lock() -> dict[str, Any]:
    try:
        value = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f"cannot read release lock {LOCK_PATH}: {exc}") from exc
    if value.get("schema") != 1:
        raise BuildError(f"unsupported release lock schema: {value.get('schema')!r}")
    return value


def run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
    try:
        subprocess.run(command, cwd=cwd, env=env, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BuildError(f"command failed: {' '.join(command)}") from exc


def capture(command: list[str], *, cwd: Path = ROOT) -> str:
    try:
        result = subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BuildError(f"command failed: {' '.join(command)}") from exc
    return result.stdout.strip()


def require_commands(*commands: str) -> None:
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        raise BuildError(f"missing required commands: {', '.join(missing)}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected_sha256: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and sha256(destination) == expected_sha256:
        return destination

    temporary = destination.with_suffix(f"{destination.suffix}.part")
    temporary.unlink(missing_ok=True)
    print(f"download {url}", flush=True)
    try:
        with urllib.request.urlopen(url) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
    except (OSError, URLError) as exc:
        temporary.unlink(missing_ok=True)
        raise BuildError(f"download failed: {url}: {exc}") from exc

    actual = sha256(temporary)
    if actual != expected_sha256:
        temporary.unlink(missing_ok=True)
        raise BuildError(f"checksum mismatch for {url}: expected {expected_sha256}, got {actual}")
    temporary.replace(destination)
    return destination


def project_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for line in pyproject.splitlines():
        if line.startswith("version = "):
            return line.split('"', 2)[1]
    raise BuildError("project version is missing from pyproject.toml")


def fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1
