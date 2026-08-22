"""Process entry point for the Axidev OSK app and command line."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path


if not __package__:
    package_root = Path(__file__).resolve().parent.parent
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the GUI without arguments, otherwise dispatch the headless CLI."""

    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        if __package__:
            from .cli import main as cli_main
        else:
            from axidev_osk.cli import main as cli_main

        return cli_main(args)

    if __package__:
        from .app import main as app_main
    else:
        from axidev_osk.app import main as app_main

    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
