"""Service adapter for the hot-corner trigger controller."""

from __future__ import annotations

from PySide6.QtCore import QObject

from ..config.models import HotCornerConfig
from ..messages import MessageResult
from ..runtime.app_messages import DISPLAY_CONFIGURATION_CHANGED
from ..runtime.decoding import EmptyArguments
from ..runtime.dispatcher import Dispatcher, Unsubscribe
from .controller import HotCornerWindowToggleController


class HotCornerService:
    """Owns hot-corner controller construction and lifecycle."""

    def __init__(self, *, parent: QObject | None = None) -> None:
        """Create an unstarted hot-corner service."""

        self._parent = parent
        self._dispatcher: Dispatcher | None = None
        self._unsubscribe: Unsubscribe | None = None
        self._controller: HotCornerWindowToggleController | None = None
        self._settings: HotCornerConfig | None = None
        self._corners: frozenset[str] | None = None

    def configure(self, settings: HotCornerConfig, corners: frozenset[str]) -> None:
        """Use a profile attachment's settings and corners, restarting the sensors if they run."""

        self._settings = settings
        self._corners = corners
        if self._dispatcher is not None:
            self._restart()

    def clear(self) -> None:
        """Forget the profile's settings and stop the sensors, for a profile without hot corners."""

        self._settings = None
        self._corners = None
        self._stop_controller()

    def start(self, dispatcher: Dispatcher) -> None:
        """Start corner sensors when the profile configured a hot_corners attachment, and follow display changes."""

        self._dispatcher = dispatcher
        self._unsubscribe = dispatcher.add_event_handler(DISPLAY_CONFIGURATION_CHANGED, self._display_changed)
        self._restart()

    def stop(self) -> None:
        """Stop and forget the controller; ``start`` builds a new one."""

        self._dispatcher = None
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._stop_controller()

    def _display_changed(self, event: EmptyArguments) -> MessageResult:
        del event
        if self._controller is not None:
            self._controller.refresh_screen_configuration()
        return []

    def _restart(self) -> None:
        self._stop_controller()
        if self._dispatcher is None or self._settings is None or not self._settings.enabled:
            return
        self._controller = HotCornerWindowToggleController(
            self._dispatcher,
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
