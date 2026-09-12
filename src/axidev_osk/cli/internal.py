"""Hidden commands used by installed integration entry points."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    """Build the parser reachable only through the reserved internal prefix."""

    parser = argparse.ArgumentParser(prog="axidev-osk internal")
    register_commands(parser.add_subparsers(dest="internal_command", required=True))
    return parser


def register_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register commands that are intentionally absent from public help."""

    worker = commands.add_parser("plasma-lock-worker")
    worker.set_defaults(handler=run_worker, application_mode="plasma-lock")

    login = commands.add_parser("plasma-login-worker")
    login.set_defaults(handler=run_worker, application_mode="plasma-login")


def main(argv: Sequence[str] | None = None) -> int:
    """Parse and run one reserved integration command."""

    args = list(sys.argv[1:] if argv is None else argv)
    namespace = build_parser().parse_args(args)
    return namespace.handler(namespace, args)


def run_worker(namespace: argparse.Namespace, argv: list[str]) -> int:
    """Start one integration-owned graphical worker."""

    del argv
    from ..app import ApplicationMode, main

    return main(mode=ApplicationMode(namespace.application_mode))
