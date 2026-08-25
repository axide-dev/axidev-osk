"""Runtime ownership for live windows keyed by deterministic IDs."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QWidget

from ..config.models import WindowConfig
from ..windows.builder import RuntimeWindow, build_window
from .context import Context

_logger = logging.getLogger(__name__)


class _WindowInputBlocker(QObject):
    """Swallow target-window mouse input except for one control component."""

    _BLOCKED_EVENTS = {
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.MouseMove,
        QEvent.Type.Wheel,
        QEvent.Type.ContextMenu,
    }

    def __init__(self, window: QWidget, allowed_component_id: str) -> None:
        super().__init__()
        self._window = window
        self._allowed_component_id = allowed_component_id

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """Return true for blocked mouse events within the target window."""

        if event.type() not in self._BLOCKED_EVENTS or not isinstance(watched, QWidget):
            return False
        if watched.window() is not self._window:
            return False

        current: QWidget | None = watched
        while current is not None:
            if current.property("componentId") == self._allowed_component_id:
                return False
            if current is self._window:
                break
            current = current.parentWidget()
        return True


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
        self._input_blockers: dict[str, _WindowInputBlocker] = {}

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
        self._restore_interaction(window_id, window)
        if sys.platform == "win32" and window.isMinimized():
            window.showNormal()
        else:
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

    def is_minimized(self, window_id: str) -> bool:
        """Return whether a managed Windows window is currently minimized."""

        window = self._windows.get(window_id)
        return sys.platform == "win32" and window is not None and window.isMinimized()

    def is_opacity_reduced(self, window_id: str) -> bool:
        """Return whether a managed window is in low-opacity input-blocking mode."""

        return window_id in self._input_blockers

    def toggle_opacity(self, window_id: str, *, component_id: str, opacity: float) -> None:
        """Toggle low-opacity mode while preserving one recovery control."""

        window = self.get_or_create(window_id)
        if window_id in self._input_blockers:
            self._restore_interaction(window_id, window)
            return

        app = QApplication.instance()
        if app is None:
            raise RuntimeError("Window opacity mode requires a QApplication")
        blocker = _WindowInputBlocker(window, component_id)
        app.installEventFilter(blocker)
        self._input_blockers[window_id] = blocker
        window.set_visual_opacity(opacity)

    def _restore_interaction(self, window_id: str, window: QWidget) -> None:
        """Restore configured opacity and remove any temporary input blocker."""

        blocker = self._input_blockers.pop(window_id, None)
        app = QApplication.instance()
        if blocker is not None and app is not None:
            app.removeEventFilter(blocker)
        window.set_visual_opacity(self._configs[window_id].opacity)

    def close(self, window_id: str) -> None:
        """Close and forget a managed window if it exists."""

        window = self._windows.pop(window_id, None)
        if window is not None:
            _logger.info("Closing runtime window %s", window_id)
            self._restore_interaction(window_id, window)
            window.close()

    def destroy(self, window_id: str) -> None:
        """Hide and delete a managed window without treating it as an app quit request."""

        window = self._windows.pop(window_id, None)
        if window is not None:
            _logger.info("Destroying runtime window %s", window_id)
            self._restore_interaction(window_id, window)
            window.release_platform_resources()
            window.hide()
            window.deleteLater()

    def all_windows(self) -> list[RuntimeWindow]:
        """Return all live managed windows."""

        return list(self._windows.values())
