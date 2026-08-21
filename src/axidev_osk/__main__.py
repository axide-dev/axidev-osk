"""Process entry point for the Axidev OSK app and command line."""

from __future__ import annotations

import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Run the GUI without arguments, otherwise dispatch the headless CLI."""

    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        from .cli import main as cli_main

        return cli_main(args)

    from .app import main as app_main

    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
