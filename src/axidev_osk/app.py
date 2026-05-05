from __future__ import annotations

import ctypes
import logging
import sys
from importlib.metadata import PackageNotFoundError, version

from PySide6.QtWidgets import QApplication

from .runtime.application import ApplicationRuntime
from .windows.overlay import prepare_always_on_top_window_environment


_logger = logging.getLogger(__name__)


def _set_process_name(name: str) -> None:
    if not sys.platform.startswith("linux"):
        return

    try:
        libc = ctypes.CDLL(None)
        pr_set_name = 15
        libc.prctl(pr_set_name, name.encode("utf-8")[:15], 0, 0, 0)
    except Exception:
        _logger.debug("Unable to set process name", exc_info=True)


def _package_version() -> str:
    try:
        return version("axidev-osk")
    except PackageNotFoundError:
        return "unknown"


def main() -> int:
    """Run the Axidev OSK Qt application.

    Args:
        None.

    Returns:
        QApplication exit code.

    Side effects:
        Initializes process metadata, overlay environment, runtime services, and Qt windows.
    """

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    _set_process_name("axidev-osk")
    _logger.info("Starting axidev-osk v%s", _package_version())
    prepare_always_on_top_window_environment()
    app = QApplication(sys.argv)
    app.setApplicationName("axidev-osk")
    app.setQuitOnLastWindowClosed(False)
    runtime = ApplicationRuntime(app)
    return runtime.start()
