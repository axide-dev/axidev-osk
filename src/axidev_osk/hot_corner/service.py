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
        self._controller: HotCornerWindowToggleController | None = None
        self._settings: HotCornerConfig | None = None
        self._corners: frozenset[str] | None = None

    def configure(self, settings: HotCornerConfig, corners: frozenset[str]) -> None:
        """Use a profile attachment's settings and corners at the next start."""

        self._settings = settings
        self._corners = corners

    def start(self, context: Context) -> None:
        """Start corner sensors when the profile configured a hot_corners attachment."""

        if self._settings is None:
            return
        self._controller = HotCornerWindowToggleController(
            context.dispatcher,
            config=self._settings,
            corners=self._corners,
            parent=self._parent,
        )
        self._controller.start()

    def stop(self) -> None:
        """Stop the controller if it has been started."""

        if self._controller is not None:
            self._controller.stop()

    def refresh_screen_configuration(self) -> None:
        """Apply the main runtime's display-change notification."""

        if self._controller is not None:
            self._controller.refresh_screen_configuration()
