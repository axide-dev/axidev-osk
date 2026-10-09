"""Observe Qt display changes and report them through the runtime dispatcher."""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication, QScreen

from ..runtime.context import Context
from ..runtime.events import display_configuration_changed


class DisplayService(QObject):
    """Coalesce output changes until Qt has finished updating its screen list."""

    def __init__(self, *, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._context: Context | None = None
        self._screens: list[QScreen] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._notify)

    def start(self, context: Context) -> None:
        """Subscribe to connected outputs and application output-list changes."""

        if self._context is not None:
            return
        self._context = context
        app = cast(QGuiApplication, QGuiApplication.instance())
        app.screenAdded.connect(self._screen_added)
        app.screenRemoved.connect(self._screen_removed)
        app.primaryScreenChanged.connect(self._schedule)
        for screen in app.screens():
            self._screen_added(screen)

    def stop(self) -> None:
        """Disconnect observers and cancel any pending notification."""

        if self._context is None:
            return
        app = cast(QGuiApplication, QGuiApplication.instance())
        app.screenAdded.disconnect(self._screen_added)
        app.screenRemoved.disconnect(self._screen_removed)
        app.primaryScreenChanged.disconnect(self._schedule)
        for screen in tuple(self._screens):
            self._screen_removed(screen)
        self._timer.stop()
        self._context = None

    def _screen_added(self, screen: QScreen) -> None:
        if screen not in self._screens:
            self._screens.append(screen)
            screen.geometryChanged.connect(self._schedule)
            screen.availableGeometryChanged.connect(self._schedule)
        self._schedule()

    def _screen_removed(self, screen: QScreen) -> None:
        if screen in self._screens:
            screen.geometryChanged.disconnect(self._schedule)
            screen.availableGeometryChanged.disconnect(self._schedule)
            self._screens.remove(screen)
        self._schedule()

    def _schedule(self, *_args: object) -> None:
        self._timer.start(0)

    def _notify(self) -> None:
        if self._context is not None:
            self._context.dispatcher.dispatch_event(display_configuration_changed())
