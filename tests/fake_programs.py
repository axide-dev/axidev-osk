"""Fake system programs for Linux setup tests: each one logs its arguments and exits with a chosen status."""

from __future__ import annotations

from pathlib import Path


class FakePrograms:
    """A directory of fake programs to put alone on ``PATH``, with one shared call log."""

    def __init__(self, root: Path) -> None:
        self.directory = root / "bin"
        self.directory.mkdir()
        self.log = root / "calls.log"

    def add(self, name: str, status: int = 0) -> None:
        program = self.directory / name
        program.write_text(
            "#!/bin/sh\n"
            f"printf '%s %s\\n' \"${{0##*/}}\" \"$*\" >> '{self.log}'\n"
            f"exit {status}\n",
            encoding="utf-8",
        )
        program.chmod(0o755)

    def calls(self) -> list[str]:
        if not self.log.exists():
            return []
        return self.log.read_text(encoding="utf-8").splitlines()
