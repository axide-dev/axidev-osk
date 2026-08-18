"""Runtime ownership for live windows keyed by deterministic IDs."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QWidget

from ..config.models import WindowConfig
from ..windows.builder import RuntimeWindow, build_window
from .context import Context

_logger = logging.getLogger(__name__)


class WindowManager:
    """Creates, stores, and controls runtime windows by ID."""

    def __init__(self, context: Context) -> None:
        """Create a window manager.

        Args:
            context: Runtime context used to build windows.

        Returns:
            None.

        Side effects:
            None.
        """

        self._context = context
        self._windows: dict[str, RuntimeWindow] = {}
        self._configs = {window.id: window for window in context.config.windows}

    def get_or_create(self, window_id: str, *, parent: QWidget | None = None) -> RuntimeWindow:
        """Return a live window, creating it from config if needed.

        Args:
            window_id: Deterministic window ID.
            parent: Optional Qt parent used when creating the window.

        Returns:
            Live runtime window.

        Side effects:
            May build and store a new Qt window.
        """

        existing = self._windows.get(window_id)
        if existing is not None:
            return existing
        config = self._configs.get(window_id)
        if config is None:
            raise ValueError(f"No window config registered for {window_id!r}")
        _logger.info("Building runtime window %s with surface %s", config.id, config.surface.id)
        window = build_window(config, self._context, parent=parent)
        self._windows[window_id] = window
        return window

    def create_transient(self, config: WindowConfig, *, parent: QWidget | None = None) -> RuntimeWindow:
        """Build a window that is not retained in the manager dict.

        Args:
            config: Window config to build.
            parent: Optional Qt parent.

        Returns:
            Runtime window.

        Side effects:
            Builds Qt widgets.
        """

        _logger.info("Building transient runtime window %s with surface %s", config.id, config.surface.id)
        return build_window(config, self._context, parent=parent)

    def show(self, window_id: str) -> RuntimeWindow:
        """Show a managed window.

        Args:
            window_id: Deterministic window ID.

        Returns:
            Shown window.

        Side effects:
            Creates and shows the window if necessary.
        """

        window = self.get_or_create(window_id)
        _logger.info("Showing runtime window %s", window_id)
        window.show()
        return window

    def hide(self, window_id: str) -> None:
        """Hide a managed window if it exists."""

        window = self._windows.get(window_id)
        if window is not None:
            _logger.info("Hiding runtime window %s", window_id)
            window.hide()

    def is_visible(self, window_id: str) -> bool:
        """Return whether a managed window currently exists and is visible."""

        window = self._windows.get(window_id)
        return window is not None and window.isVisible()

    def close(self, window_id: str) -> None:
        """Close and forget a managed window if it exists."""

        window = self._windows.pop(window_id, None)
        if window is not None:
            _logger.info("Closing runtime window %s", window_id)
            window.close()

    def all_windows(self) -> list[RuntimeWindow]:
        """Return all live managed windows."""

        return list(self._windows.values())

    def reapply_always_on_top_windows(self) -> None:
        """Reassert topmost state for live windows configured as overlays."""

        refreshed = 0
        for window in self._windows.values():
            if window.always_on_top:
                window.reapply_always_on_top()
                refreshed += 1
        _logger.debug("Reapplied topmost state for %d managed overlay window(s)", refreshed)
