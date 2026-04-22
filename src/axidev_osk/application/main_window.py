from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from ..components.keyboard_widget import KeyboardWidget
from ..styles.theme import build_stylesheet


if sys.platform == "win32":
    _GWL_EXSTYLE = -20
    _HWND_TOPMOST = -1
    _SWP_NOMOVE = 0x0002
    _SWP_NOSIZE = 0x0001
    _SWP_NOACTIVATE = 0x0010
    _SWP_FRAMECHANGED = 0x0020
    _SWP_NOOWNERZORDER = 0x0200
    _WS_EX_NOACTIVATE = 0x08000000

    _user32 = ctypes.windll.user32
    _get_window_long_ptr = _user32.GetWindowLongPtrW
    _set_window_long_ptr = _user32.SetWindowLongPtrW
    _set_window_pos = _user32.SetWindowPos

    _get_window_long_ptr.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _get_window_long_ptr.restype = ctypes.c_longlong
    _set_window_long_ptr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong]
    _set_window_long_ptr.restype = ctypes.c_longlong
    _set_window_pos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    _set_window_pos.restype = ctypes.c_int


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AxiDev On-Screen Keyboard")
        self.resize(1160, 320)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(0)
        layout.addWidget(KeyboardWidget())

        self.setCentralWidget(central)
        self.setStyleSheet(build_stylesheet())

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if sys.platform == "win32":
            self._apply_windows_window_styles()

    def _apply_windows_window_styles(self) -> None:
        hwnd = int(self.winId())
        ex_style = _get_window_long_ptr(hwnd, _GWL_EXSTYLE)
        if ex_style & _WS_EX_NOACTIVATE == 0:
            _set_window_long_ptr(hwnd, _GWL_EXSTYLE, ex_style | _WS_EX_NOACTIVATE)

        _set_window_pos(
            hwnd,
            _HWND_TOPMOST,
            0,
            0,
            0,
            0,
            _SWP_NOMOVE
            | _SWP_NOSIZE
            | _SWP_NOACTIVATE
            | _SWP_FRAMECHANGED
            | _SWP_NOOWNERZORDER,
        )
