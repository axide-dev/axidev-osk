#!/usr/bin/env python3
"""Repository build and packaging entry point."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LINUX_SUPPORT = ROOT / "packaging" / "linux" / "build_support"


def main() -> int:
    if str(LINUX_SUPPORT) not in sys.path:
        sys.path.insert(0, str(LINUX_SUPPORT))

    from cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
