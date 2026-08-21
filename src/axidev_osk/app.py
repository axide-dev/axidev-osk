"""Application entry point for the Axidev OSK executable."""

from __future__ import annotations

import ctypes
import logging
import sys
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .runtime.application import ApplicationRuntime
from .services.single_instance import ExistingInstanceActivated
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


def _set_application_icon(app: QApplication) -> None:
    suffix = ".ico" if sys.platform == "win32" else ".svg"
    icon_path = files("axidev_osk.assets").joinpath(f"axidev-osk{suffix}")
    icon = QIcon(str(icon_path))
    if icon.isNull():
        _logger.warning("Unable to load application icon from %s", icon_path)
        return
    app.setWindowIcon(icon)


def main() -> int:
    """Run the Axidev OSK Qt application.

    Args:
        None.

    Returns:
        QApplication exit code.

    Side effects:
        Initializes process metadata, overlay environment, runtime services, and Qt windows.
    """

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] (%(filename)s:%(lineno)d) %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _set_process_name("axidev-osk")
    _logger.info("Starting axidev-osk v%s", _package_version())
    prepare_always_on_top_window_environment()
    app = QApplication(sys.argv)
    app.setApplicationName("axidev-osk")
    _set_application_icon(app)
    app.setQuitOnLastWindowClosed(False)
    runtime = ApplicationRuntime(app)
    try:
        return runtime.start()
    except ExistingInstanceActivated:
        _logger.info("Activated the running Axidev OSK instance")
        return 0
