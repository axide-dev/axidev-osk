from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .application.main_window import MainWindow
from .application.overlay_window import prepare_always_on_top_window_environment


def main() -> int:
    prepare_always_on_top_window_environment()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
