"""Headless command-line entry point for Axidev OSK administration."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import linux


def build_parser() -> argparse.ArgumentParser:
    """Build the Axidev OSK command parser without importing the GUI runtime."""

    parser = argparse.ArgumentParser(prog="axidev-osk")
    platforms = parser.add_subparsers(dest="platform", required=True)
    linux.register_commands(platforms.add_parser("linux", help="manage Linux integration"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse and dispatch one headless Axidev OSK command."""

    args = list(sys.argv[1:] if argv is None else argv)
    namespace = build_parser().parse_args(args)
    return namespace.handler(namespace, args)


__all__ = ["build_parser", "main"]
