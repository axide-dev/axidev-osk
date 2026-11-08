"""``axidev-osk check``: explore the bundled config's states and report every problem found."""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def register_command(parser: argparse.ArgumentParser) -> None:
    """Set up the ``check`` command, which checks the bundled config."""

    parser.add_argument(
        "--depth",
        type=_depth,
        help="how many state units may differ from the start; overrides every profile's check_depth",
    )
    parser.set_defaults(handler=run_check)


def _depth(text: str) -> int:
    depth = int(text)
    if depth < 0:
        raise argparse.ArgumentTypeError("the depth must be at least 0")
    return depth


def run_check(namespace: argparse.Namespace, argv: Sequence[str]) -> int:
    """Print every problem in the bundled config and how many states were explored; return 1 on a problem."""

    del argv
    # Imported here so the parser stays free of the engine; nothing starts the GUI.
    from ..config_check import check_config, format_report
    from ..python_defaults.default_profile import build_default_config

    report = check_config(build_default_config(), namespace.depth)
    print(format_report(report))
    return 0 if report.ok else 1
