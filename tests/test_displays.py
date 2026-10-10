from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from axidev_osk.runtime.app_messages import (
    DISPLAY_CONFIGURATION_CHANGED,
    display_configuration_changed,
    register_app_events,
)
from axidev_osk.runtime.decoding import EmptyArguments
from axidev_osk.runtime.dispatcher import Dispatcher
from axidev_osk.runtime.event_handlers import register_display_recovery
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
        register_app_events(dispatcher)
        events = []
        dispatcher.add_event_handler(
            DISPLAY_CONFIGURATION_CHANGED,
            lambda event: events.append(event) or [],
        )
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
                self.assertEqual(events, [EmptyArguments()])

                events.clear()
                removed.geometryChanged.emit()
                self.app.processEvents()
                self.assertEqual(events, [])

                replacement = Screen()
                app.outputs.append(replacement)
                app.screenAdded.emit(replacement)
                self.app.processEvents()
                self.assertEqual(events, [EmptyArguments()])
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
        hot_corners = Mock()
        services = ServiceRegistry()
        services.register("hot_corner", hot_corners)
        dispatcher = Dispatcher()
        register_app_events(dispatcher)
        register_display_recovery(dispatcher, manager, services)
        dispatcher.dispatch(display_configuration_changed())
        unbuilt.assert_not_called()
        keyboard.refresh_screen_configuration.assert_called_once_with()
        other_window.refresh_screen_configuration.assert_called_once_with()
        hot_corners.refresh_screen_configuration.assert_called_once_with()
        self.assertIs(manager.get("keyboard"), keyboard)
        self.assertIsNone(manager.get("unbuilt"))
