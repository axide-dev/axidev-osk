"""Service adapter for the hot-corner trigger controller."""

from __future__ import annotations

from PySide6.QtCore import QObject

from ..runtime.context import Context

from .controller import HotCornerWindowToggleController


class HotCornerService:
    """Owns hot-corner controller construction and lifecycle."""

    def __init__(self, *, parent: QObject | None = None) -> None:
        """Create an unstarted hot-corner service."""

        self._parent = parent
        self._controller: HotCornerWindowToggleController | None = None

    def start(self, context: Context) -> None:
        """Create and start the controller from runtime config."""

        self._controller = HotCornerWindowToggleController(
            context.dispatcher,
            config=context.config.hot_corner,
            parent=self._parent,
        )
        self._controller.start()

    def stop(self) -> None:
        """Stop the controller if it has been started."""

        if self._controller is not None:
            self._controller.stop()
