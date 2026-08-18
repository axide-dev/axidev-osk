"""Windows event hook service for refreshing topmost overlay windows."""

from __future__ import annotations

import ctypes
import logging
import sys

from PySide6.QtCore import QObject, QTimer

from ..runtime.context import Context
from ..runtime.dispatcher import Dispatcher
from ..runtime.events import WindowManagerEventObserved


_logger = logging.getLogger(__name__)

_EVENT_OBJECT_REORDER = 0x8004
_OBJID_CLIENT = -4
_CHILDID_SELF = 0
_WINEVENT_OUTOFCONTEXT = 0x0000
_WINEVENT_SKIPOWNPROCESS = 0x0002
_REFRESH_DELAY_MS = 100


class WindowsTopmostService(QObject):
    """Listen for Win32 window-manager events and refresh overlay z-order."""

    def __init__(
        self,
        *,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._dispatcher: Dispatcher | None = None
        self._hook: int | None = None
        self._callback: object | None = None
        self._desktop_window: int | None = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(_REFRESH_DELAY_MS)
        self._refresh_timer.timeout.connect(self._refresh_topmost_windows)

    def start(self, context: Context) -> None:
        """Install the Win32 event hook on Windows; no-op elsewhere."""

        if sys.platform != "win32":
            _logger.debug("Skipping Windows topmost service on platform %s", sys.platform)
            return
        if self._hook is not None:
            _logger.debug("Windows topmost event hook is already installed")
            return
        self._dispatcher = context.dispatcher

        callback_type = ctypes.WINFUNCTYPE(
            None,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.c_long,
            ctypes.c_uint,
            ctypes.c_uint,
        )
        self._callback = callback_type(self._handle_window_event)
        user32 = ctypes.windll.user32
        set_win_event_hook = user32.SetWinEventHook
        set_win_event_hook.argtypes = [
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_void_p,
            callback_type,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_uint,
        ]
        set_win_event_hook.restype = ctypes.c_void_p
        get_desktop_window = user32.GetDesktopWindow
        get_desktop_window.argtypes = []
        get_desktop_window.restype = ctypes.c_void_p
        self._desktop_window = int(get_desktop_window() or 0)
        self._hook = int(
            set_win_event_hook(
                _EVENT_OBJECT_REORDER,
                _EVENT_OBJECT_REORDER,
                None,
                self._callback,
                0,
                0,
                _WINEVENT_OUTOFCONTEXT | _WINEVENT_SKIPOWNPROCESS,
            )
            or 0
        )
        if self._hook == 0:
            self._hook = None
            self._callback = None
            self._desktop_window = None
            self._dispatcher = None
            _logger.warning("Unable to install Windows topmost event hook")
            return

        _logger.info("Installed Windows topmost event hook")

    def stop(self) -> None:
        """Remove the Win32 event hook if it was installed."""

        self._refresh_timer.stop()
        if sys.platform == "win32" and self._hook is not None:
            ctypes.windll.user32.UnhookWinEvent(ctypes.c_void_p(self._hook))
            _logger.info("Removed Windows topmost event hook")
        self._hook = None
        self._callback = None
        self._desktop_window = None
        self._dispatcher = None

    def _handle_window_event(
        self,
        hook: int,
        event: int,
        hwnd: int,
        object_id: int,
        child_id: int,
        event_thread: int,
        event_time: int,
    ) -> None:
        del hook, event_thread, event_time
        if (
            event != _EVENT_OBJECT_REORDER
            or int(hwnd or 0) != self._desktop_window
            or object_id != _OBJID_CLIENT
            or child_id != _CHILDID_SELF
        ):
            return
        if self._refresh_timer.isActive():
            return
        _logger.debug("Observed Windows desktop reorder; scheduling topmost refresh")
        self._refresh_timer.start()

    def _refresh_topmost_windows(self) -> None:
        if self._dispatcher is not None:
            _logger.debug("Dispatching window-manager observation for topmost refresh")
            self._dispatcher.dispatch_event(WindowManagerEventObserved())
