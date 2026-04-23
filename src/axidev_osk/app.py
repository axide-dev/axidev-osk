from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .application.hot_corner import HotCornerConfig, HotCornerWindowToggleController
from .application.main_window import MainWindow
from .application.overlay_window import prepare_always_on_top_window_environment
from .styles.theme import apply_theme


def main() -> int:
    prepare_always_on_top_window_environment()
    app = QApplication(sys.argv)
    apply_theme(app)
    hot_corner = HotCornerWindowToggleController(
        app,
        config=HotCornerConfig(),
        parent=app,
    )
    window = MainWindow()
    hot_corner.start()
    window.show()
    return app.exec()
