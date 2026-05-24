"""Windows event hook service for refreshing topmost overlay windows."""

from __future__ import annotations

import ctypes
import logging
import sys
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer

from ..runtime.context import Context


_logger = logging.getLogger(__name__)

_EVENT_MIN = 0x00000001
_EVENT_MAX = 0x7FFFFFFF
_WINEVENT_OUTOFCONTEXT = 0x0000
_WINEVENT_SKIPOWNPROCESS = 0x0002


class WindowsTopmostService(QObject):
    """Listen for Win32 window-manager events and refresh overlay z-order."""

    def __init__(
        self,
        reapply_always_on_top: Callable[[], None] | None = None,
        *,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._reapply_always_on_top = reapply_always_on_top
        self._hook: int | None = None
        self._callback: object | None = None
        self._pending = False

    def set_reapply_always_on_top(self, callback: Callable[[], None]) -> None:
        """Bind the runtime-owned topmost refresh callback."""

        self._reapply_always_on_top = callback

    def start(self, context: Context) -> None:
        """Install the Win32 event hook on Windows; no-op elsewhere."""

        del context
        if sys.platform != "win32":
            return
        if self._hook is not None:
            return

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
        self._hook = int(
            set_win_event_hook(
                _EVENT_MIN,
                _EVENT_MAX,
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
            _logger.warning("Unable to install Windows topmost event hook")

    def stop(self) -> None:
        """Remove the Win32 event hook if it was installed."""

        if sys.platform == "win32" and self._hook is not None:
            ctypes.windll.user32.UnhookWinEvent(ctypes.c_void_p(self._hook))
        self._hook = None
        self._callback = None
        self._pending = False

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
        del hook, event, hwnd, object_id, child_id, event_thread, event_time
        if self._pending:
            return
        self._pending = True
        QTimer.singleShot(50, self._refresh_topmost_windows)

    def _refresh_topmost_windows(self) -> None:
        self._pending = False
        if self._reapply_always_on_top is not None:
            self._reapply_always_on_top()
