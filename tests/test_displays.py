from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject, QRect, Signal
from PySide6.QtWidgets import QApplication

from axidev_osk.runtime.dispatcher import Dispatcher
from axidev_osk.runtime.engine_messages import (
    DISPLAY_CONFIGURATION_CHANGED,
    DisplayConfigurationArguments,
    display_configuration_changed,
    register_engine_events,
)
from axidev_osk.runtime.event_handlers import register_display_recovery
from axidev_osk.runtime.window_manager import WindowManager
from axidev_osk.services.displays import DisplayService


class Screen(QObject):
    geometryChanged = Signal()
    availableGeometryChanged = Signal()

    def __init__(self, name: str = "screen", x: int = 0) -> None:
        super().__init__()
        self._name = name
        self._x = x

    def name(self) -> str:
        return self._name

    def geometry(self) -> QRect:
        return QRect(self._x, 0, 1920, 1080)

    def availableGeometry(self) -> QRect:  # noqa: N802
        return QRect(self._x, 0, 1920, 1040)


class Application(QObject):
    screenAdded = Signal(object)
    screenRemoved = Signal(object)
    primaryScreenChanged = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.outputs = [Screen("left", 0), Screen("right", 1920)]

    def screens(self) -> list[Screen]:
        return self.outputs

    def primaryScreen(self) -> Screen:  # noqa: N802
        return self.outputs[0]


def _described(screen: Screen, primary: bool) -> dict[str, object]:
    x = screen.geometry().x()
    return {
        "name": screen.name(),
        "primary": primary,
        "x": x,
        "y": 0,
        "width": 1920,
        "height": 1080,
        "available": {"x": x, "y": 0, "width": 1920, "height": 1040},
    }


class DisplayRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_output_events_coalesce_and_disconnect_removed_screens(self) -> None:
        dispatcher = Dispatcher()
        register_engine_events(dispatcher)
        events = []
        dispatcher.add_event_handler(
            DISPLAY_CONFIGURATION_CHANGED,
            lambda event: events.append(event) or [],
        )
        app = Application()
        service = DisplayService()
        with patch("axidev_osk.services.displays.QGuiApplication.instance", return_value=app):
            try:
                service.start(dispatcher)
                self.app.processEvents()
                events.clear()
                removed = app.outputs.pop()
                app.screenRemoved.emit(removed)
                app.outputs[0].geometryChanged.emit()
                app.outputs[0].availableGeometryChanged.emit()
                app.primaryScreenChanged.emit(app.outputs[0])
                self.assertEqual(events, [])
                self.app.processEvents()
                self.assertEqual(
                    events, [DisplayConfigurationArguments(screens=(_described(app.outputs[0], primary=True),))]
                )

                events.clear()
                removed.geometryChanged.emit()
                self.app.processEvents()
                self.assertEqual(events, [])

                replacement = Screen("replacement", 1920)
                app.outputs.append(replacement)
                app.screenAdded.emit(replacement)
                self.app.processEvents()
                self.assertEqual(
                    events,
                    [
                        DisplayConfigurationArguments(
                            screens=(_described(app.outputs[0], primary=True), _described(replacement, primary=False))
                        )
                    ],
                )
                events.clear()
                replacement.geometryChanged.emit()
                service.stop()
                self.app.processEvents()
                self.assertEqual(events, [])
                app.screenAdded.emit(Screen())
                replacement.availableGeometryChanged.emit()
                self.app.processEvents()
                self.assertEqual(events, [])
            finally:
                service.stop()

    def test_runtime_refreshes_existing_windows_without_building_windows(self) -> None:
        keyboard = Mock()
        other_window = Mock()
        unbuilt = Mock()
        manager = WindowManager(
            {
                "keyboard": lambda: keyboard,
                "other": lambda: other_window,
                "unbuilt": unbuilt,
            }
        )
        manager.get_or_create("keyboard")
        manager.get_or_create("other")
        dispatcher = Dispatcher()
        register_engine_events(dispatcher)
        register_display_recovery(dispatcher, manager)
        dispatcher.dispatch(display_configuration_changed([]))
        unbuilt.assert_not_called()
        keyboard.refresh_screen_configuration.assert_called_once_with()
        other_window.refresh_screen_configuration.assert_called_once_with()
        self.assertIs(manager.get("keyboard"), keyboard)
        self.assertIsNone(manager.get("unbuilt"))
