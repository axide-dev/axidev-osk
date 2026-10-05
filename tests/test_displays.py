from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from axidev_osk.runtime.dispatcher import Dispatcher
from axidev_osk.runtime.event_handlers import route_display_configuration_changed
from axidev_osk.runtime.events import DisplayConfigurationChanged
from axidev_osk.runtime.registries import ServiceRegistry
from axidev_osk.runtime.window_manager import WindowManager
from axidev_osk.services.displays import DisplayService


class Screen(QObject):
    geometryChanged = Signal()
    availableGeometryChanged = Signal()


class Application(QObject):
    screenAdded = Signal(object)
    screenRemoved = Signal(object)
    primaryScreenChanged = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.outputs = [Screen(), Screen()]

    def screens(self) -> list[Screen]:
        return self.outputs


class DisplayRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_output_events_coalesce_and_disconnect_removed_screens(self) -> None:
        dispatcher = Dispatcher()
        events = []
        dispatcher.add_event_handler(events.append)
        context = SimpleNamespace(dispatcher=dispatcher)
        app = Application()
        service = DisplayService()
        with patch("axidev_osk.services.displays.QGuiApplication.instance", return_value=app):
            try:
                service.start(context)
                self.app.processEvents()
                events.clear()
                removed = app.outputs.pop()
                app.screenRemoved.emit(removed)
                app.outputs[0].geometryChanged.emit()
                app.outputs[0].availableGeometryChanged.emit()
                app.primaryScreenChanged.emit(app.outputs[0])
                self.assertEqual(events, [])
                self.app.processEvents()
                self.assertEqual(events, [DisplayConfigurationChanged()])

                events.clear()
                removed.geometryChanged.emit()
                self.app.processEvents()
                self.assertEqual(events, [])

                replacement = Screen()
                app.outputs.append(replacement)
                app.screenAdded.emit(replacement)
                self.app.processEvents()
                self.assertEqual(events, [DisplayConfigurationChanged()])
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

    def test_runtime_refreshes_existing_windows_and_services_without_building_windows(self) -> None:
        context = SimpleNamespace(config=SimpleNamespace(windows=[]))
        manager = WindowManager(context)
        keyboard = Mock()
        other_window = Mock()
        manager._windows = {"keyboard": keyboard, "other": other_window}
        hot_corners = Mock()
        services = ServiceRegistry()
        services.register("hot_corner", hot_corners)
        runtime = SimpleNamespace(_window_manager=manager, _services=services)
        dispatcher = Dispatcher()
        dispatcher.add_event_handler(lambda event: route_display_configuration_changed(event, runtime))
        with patch("axidev_osk.runtime.window_manager.build_window") as build:
            dispatcher.dispatch_event(DisplayConfigurationChanged())
        build.assert_not_called()
        keyboard.refresh_screen_configuration.assert_called_once_with()
        other_window.refresh_screen_configuration.assert_called_once_with()
        hot_corners.refresh_screen_configuration.assert_called_once_with()
        self.assertIs(manager.get("keyboard"), keyboard)
