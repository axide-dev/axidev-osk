"""Application entry point for the Axidev OSK executable."""

from __future__ import annotations

import ctypes
import logging
import sys
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .runtime.application import ApplicationRuntime
from .runtime.registries import ServiceRegistry
from .services.keyboard import KeyboardService
from .services.secure_input_panel import SecureInputPanelWorkerService
from .services.single_instance import ExistingInstanceActivated
from .windows.overlay import OverlayBackend, prepare_always_on_top_window_environment


_logger = logging.getLogger(__name__)


class ApplicationMode(Enum):
    """Explicit runtime role selected by an integration entry point."""

    DESKTOP = "desktop"
    PLASMA_LOCK = "plasma-lock"
    PLASMA_LOGIN = "plasma-login"


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


def _input_panel_services(
    app: QApplication,
    backend: OverlayBackend,
    *,
    mode: ApplicationMode,
) -> ServiceRegistry | None:
    if backend != OverlayBackend.WAYLAND_INPUT_PANEL:
        return None
    services = ServiceRegistry()
    services.register("keyboard", KeyboardService(), autostart=mode != ApplicationMode.PLASMA_LOCK)
    if mode == ApplicationMode.PLASMA_LOCK:
        services.register(
            "secure_input_panel_worker",
            SecureInputPanelWorkerService(parent=app),
        )
    return services


def main(*, mode: ApplicationMode = ApplicationMode.DESKTOP) -> int:
    """Run the Axidev OSK Qt application.

    Args:
        mode: Explicit desktop or Plasma integration role.

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
    overlay_backend = prepare_always_on_top_window_environment()
    if (
        mode != ApplicationMode.DESKTOP
        and overlay_backend != OverlayBackend.WAYLAND_INPUT_PANEL
    ):
        raise RuntimeError(f"{mode.value} requires KWin's privileged input-method connection")
    lock_lifecycle = mode == ApplicationMode.PLASMA_LOCK
    app = QApplication([sys.argv[0]])
    app.setApplicationName("axidev-osk")
    _set_application_icon(app)
    app.setQuitOnLastWindowClosed(False)
    runtime = ApplicationRuntime(
        app,
        services=_input_panel_services(app, overlay_backend, mode=mode),
        confirm_quit=overlay_backend != OverlayBackend.WAYLAND_INPUT_PANEL,
        show_startup_windows=not lock_lifecycle,
    )
    try:
        return runtime.start()
    except ExistingInstanceActivated:
        _logger.info("Activated the running Axidev OSK instance")
        return 0
