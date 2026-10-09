"""Runtime ownership for live windows keyed by deterministic IDs."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping

from ..windows.builder import RuntimeWindow

_logger = logging.getLogger(__name__)

WindowFactory = Callable[[], RuntimeWindow]


class WindowManager:
    """Own live runtime windows keyed by profile window IDs.

    Windows are built lazily by the factories the runtime provides for the
    active profile. The manager is the only record of which windows are live:
    closing one releases and deletes it, and the next ``show`` builds it again.
    """

    def __init__(self, factories: Mapping[str, WindowFactory]) -> None:
        self._windows: dict[str, RuntimeWindow] = {}
        self._factories: dict[str, WindowFactory] = dict(factories)

    def get_or_create(self, window_id: str) -> RuntimeWindow:
        """Return a live window, building it from its factory if needed."""

        existing = self._windows.get(window_id)
        if existing is not None:
            return existing
        factory = self._factories.get(window_id)
        if factory is None:
            raise ValueError(f"No window named {window_id!r} in the active profile")
        _logger.info("Building runtime window %s", window_id)
        window = factory()
        self._windows[window_id] = window
        return window

    def get(self, window_id: str) -> RuntimeWindow | None:
        """Return an existing managed window without creating one."""

        return self._windows.get(window_id)

    def show(self, window_id: str) -> RuntimeWindow:
        """Show a window, restoring it if it is minimized.

        This applies on every platform; before profiles, only Windows restored
        minimized windows here.
        """

        window = self.get_or_create(window_id)
        _logger.info("Showing runtime window %s", window_id)
        if window.isMinimized():
            window.showNormal()
        else:
            window.show()
        return window

    def hide(self, window_id: str) -> None:
        window = self._windows.get(window_id)
        if window is not None:
            _logger.info("Hiding runtime window %s", window_id)
            window.hide()

    def set_opacity(self, window_id: str, opacity: float) -> None:
        """Set one built window's visible opacity; a window that was never built keeps its config."""

        window = self._windows.get(window_id)
        if window is not None:
            window.set_visual_opacity(opacity)

    def block_input(self, window_id: str, allowed_node_ids: frozenset[str]) -> None:
        """Ignore pointer input on a built window except inside the allowed nodes."""

        window = self._windows.get(window_id)
        if window is not None:
            window.block_input(allowed_node_ids)

    def unblock_input(self, window_id: str) -> None:
        """Remove a pointer-input block installed by ``block_input``."""

        window = self._windows.get(window_id)
        if window is not None:
            window.unblock_input()

    def move_by(self, window_id: str, dx: int, dy: int) -> None:
        window = self._windows.get(window_id)
        if window is not None:
            window.move_by(dx, dy)

    def close(self, window_id: str) -> None:
        """Release, hide, and delete a managed window without treating it as a quit request."""

        window = self._windows.pop(window_id, None)
        if window is not None:
            _logger.info("Closing runtime window %s", window_id)
            window.unblock_input()
            window.release_platform_resources()
            window.hide()
            window.deleteLater()

    def close_all(self) -> None:
        """Close every live window, for example at the end of shutdown."""

        for window_id in list(self._windows):
            self.close(window_id)

    def all_windows(self) -> list[RuntimeWindow]:
        return list(self._windows.values())

    def refresh_screen_configuration(self) -> None:
        """Recover existing windows without constructing additional instances."""

        for window in self.all_windows():
            window.refresh_screen_configuration()
