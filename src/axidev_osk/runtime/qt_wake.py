"""Qt adapter that schedules dispatcher drains on the Qt thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal, Slot

from .dispatcher import Dispatcher


class QtDispatcherWake(QObject):
    """Turn wake requests from any thread into a queued drain on this object's thread."""

    requested = Signal()

    def __init__(self, dispatcher: Dispatcher, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dispatcher = dispatcher
        self.requested.connect(self._process_pending, Qt.ConnectionType.QueuedConnection)
        dispatcher.set_wake(self.requested.emit)

    @Slot()
    def _process_pending(self) -> None:
        self._dispatcher.process_pending()
