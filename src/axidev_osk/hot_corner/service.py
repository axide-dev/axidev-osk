"""Service adapter for the hot-corner trigger controller."""

from __future__ import annotations

from PySide6.QtCore import QObject

from ..config.models import HotCornerConfig
from ..runtime.context import Context
from .controller import HotCornerWindowToggleController


class HotCornerService:
    """Owns hot-corner controller construction and lifecycle."""

    def __init__(self, *, parent: QObject | None = None) -> None:
        """Create an unstarted hot-corner service."""

        self._parent = parent
        self._context: Context | None = None
        self._controller: HotCornerWindowToggleController | None = None
        self._settings: HotCornerConfig | None = None
        self._corners: frozenset[str] | None = None

    def configure(self, settings: HotCornerConfig, corners: frozenset[str]) -> None:
        """Use a profile attachment's settings and corners, restarting the sensors if they run."""

        self._settings = settings
        self._corners = corners
        if self._context is not None:
            self._restart()

    def start(self, context: Context) -> None:
        """Start corner sensors when the profile configured a hot_corners attachment."""

        self._context = context
        self._restart()

    def stop(self) -> None:
        """Stop and forget the controller; ``start`` builds a new one."""

        self._context = None
        self._stop_controller()

    def refresh_screen_configuration(self) -> None:
        """Apply the main runtime's display-change notification."""

        if self._controller is not None:
            self._controller.refresh_screen_configuration()

    def _restart(self) -> None:
        self._stop_controller()
        if self._context is None or self._settings is None:
            return
        self._controller = HotCornerWindowToggleController(
            self._context.dispatcher,
            config=self._settings,
            corners=self._corners,
            parent=self._parent,
        )
        self._controller.start()

    def _stop_controller(self) -> None:
        controller = self._controller
        self._controller = None
        if controller is not None:
            controller.stop()
