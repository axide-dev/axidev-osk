"""Runtime ownership for live windows keyed by deterministic IDs."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Mapping

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QWidget

from ..windows.builder import RuntimeWindow

_logger = logging.getLogger(__name__)

WindowFactory = Callable[[QWidget | None], RuntimeWindow]


class _WindowInputBlocker(QObject):
    """Swallow target-window mouse input except inside the allowed nodes."""

    _BLOCKED_EVENTS = {
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.MouseMove,
        QEvent.Type.Wheel,
        QEvent.Type.ContextMenu,
    }

    def __init__(self, window: QWidget, allowed_component_ids: frozenset[str]) -> None:
        super().__init__()
        self._window = window
        self._allowed_component_ids = allowed_component_ids

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """Return true for blocked mouse events within the target window."""

        if event.type() not in self._BLOCKED_EVENTS or not isinstance(watched, QWidget):
            return False
        if watched.window() is not self._window:
            return False

        current: QWidget | None = watched
        while current is not None:
            if current.property("componentId") in self._allowed_component_ids:
                return False
            if current is self._window:
                break
            current = current.parentWidget()
        return True


class WindowManager:
    """Own live runtime windows keyed by profile window IDs.

    Windows are built lazily by the factories the runtime provides for the
    active profile.
    """

    def __init__(self, factories: Mapping[str, WindowFactory] | None = None) -> None:
        self._windows: dict[str, RuntimeWindow] = {}
        self._factories: dict[str, WindowFactory] = dict(factories or {})
        self._input_blockers: dict[str, _WindowInputBlocker] = {}

    def set_factories(self, factories: Mapping[str, WindowFactory]) -> None:
        """Replace how windows are built, for example from a newly loaded profile."""

        self._factories = dict(factories)

    def get_or_create(self, window_id: str, *, parent: QWidget | None = None) -> RuntimeWindow:
        """Return a live window, building it from its factory if needed."""

        existing = self._windows.get(window_id)
        if existing is not None:
            return existing
        factory = self._factories.get(window_id)
        if factory is None:
            raise ValueError(f"No window named {window_id!r} in the active profile")
        _logger.info("Building runtime window %s", window_id)
        window = factory(parent)
        self._windows[window_id] = window
        return window

    def get(self, window_id: str) -> RuntimeWindow | None:
        """Return an existing managed window without creating one."""

        return self._windows.get(window_id)

    def show(self, window_id: str) -> RuntimeWindow:
        """Show a window, restoring it from minimized state on Windows."""

        window = self.get_or_create(window_id)
        _logger.info("Showing runtime window %s", window_id)
        if sys.platform == "win32" and window.isMinimized():
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
        """Set one window's visible opacity, building the window if needed."""

        self.get_or_create(window_id).set_visual_opacity(opacity)

    def block_input(self, window_id: str, allowed_node_ids: frozenset[str]) -> None:
        """Ignore pointer input on a window except inside the allowed nodes."""

        window = self.get_or_create(window_id)
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("Blocking window input requires a QApplication")
        self.unblock_input(window_id)
        blocker = _WindowInputBlocker(window, allowed_node_ids)
        app.installEventFilter(blocker)
        self._input_blockers[window_id] = blocker

    def unblock_input(self, window_id: str) -> None:
        """Remove a pointer-input block installed by ``block_input``."""

        blocker = self._input_blockers.pop(window_id, None)
        app = QApplication.instance()
        if blocker is not None and app is not None:
            app.removeEventFilter(blocker)

    def close(self, window_id: str) -> None:
        """Close and forget a managed window if it exists."""

        window = self._windows.pop(window_id, None)
        if window is not None:
            _logger.info("Closing runtime window %s", window_id)
            self.unblock_input(window_id)
            window.close()

    def move_by(self, window_id: str, dx: int, dy: int) -> None:
        window = self._windows.get(window_id)
        if window is not None:
            window.move_by(dx, dy)

    def destroy(self, window_id: str) -> None:
        """Hide and delete a managed window without treating it as an app quit request."""

        window = self._windows.pop(window_id, None)
        if window is not None:
            _logger.info("Destroying runtime window %s", window_id)
            self.unblock_input(window_id)
            window.release_platform_resources()
            window.hide()
            window.deleteLater()

    def all_windows(self) -> list[RuntimeWindow]:
        return list(self._windows.values())

    def refresh_screen_configuration(self) -> None:
        """Recover existing windows without constructing additional instances."""

        for window in self.all_windows():
            window.refresh_screen_configuration()
