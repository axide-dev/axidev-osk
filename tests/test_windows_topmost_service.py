from __future__ import annotations

import sys
import unittest
from unittest.mock import Mock, patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from axidev_osk.runtime.application import ApplicationRuntime
from axidev_osk.runtime.dispatcher import Dispatcher
from axidev_osk.runtime.event_handlers import register_event_handlers
from axidev_osk.runtime.events import WindowManagerEventObserved
from axidev_osk.runtime.registries import EventHandlerRegistry
from axidev_osk.runtime.window_manager import WindowManager
from axidev_osk.services.windows_topmost import (
    _CHILDID_SELF,
    _EVENT_OBJECT_REORDER,
    _OBJID_CLIENT,
    WindowsTopmostService,
)
from axidev_osk.windows.overlay.always_on_top import AlwaysOnTopWindowController, OverlayBackend


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class WindowsTopmostServiceTests(unittest.TestCase):
    def test_window_manager_reapplies_only_always_on_top_windows(self) -> None:
        manager = WindowManager.__new__(WindowManager)
        topmost_window = Mock(always_on_top=True)
        plain_window = Mock(always_on_top=False)
        manager._windows = {"topmost": topmost_window, "plain": plain_window}

        manager.reapply_always_on_top_windows()

        topmost_window.reapply_always_on_top.assert_called_once_with()
        plain_window.reapply_always_on_top.assert_not_called()

    def test_start_is_noop_off_windows(self) -> None:
        service = WindowsTopmostService()

        with patch("axidev_osk.services.windows_topmost.sys.platform", "linux"):
            service.start(Mock())

        self.assertIsNone(service._hook)

    def test_window_event_rate_limits_desktop_reorder_refresh(self) -> None:
        _app()
        service = WindowsTopmostService()
        service._desktop_window = 123
        timer = Mock()
        timer.isActive.side_effect = [False, True]
        service._refresh_timer = timer

        service._handle_window_event(1, _EVENT_OBJECT_REORDER, 123, _OBJID_CLIENT, _CHILDID_SELF, 6, 7)
        service._handle_window_event(1, _EVENT_OBJECT_REORDER, 123, _OBJID_CLIENT, _CHILDID_SELF, 6, 7)

        timer.start.assert_called_once_with()

    def test_window_event_ignores_unrelated_reorders(self) -> None:
        service = WindowsTopmostService()
        service._desktop_window = 123
        timer = Mock()
        service._refresh_timer = timer

        service._handle_window_event(1, 3, 123, _OBJID_CLIENT, _CHILDID_SELF, 6, 7)
        service._handle_window_event(1, _EVENT_OBJECT_REORDER, 456, _OBJID_CLIENT, _CHILDID_SELF, 6, 7)
        service._handle_window_event(1, _EVENT_OBJECT_REORDER, 123, 0, _CHILDID_SELF, 6, 7)
        service._handle_window_event(1, _EVENT_OBJECT_REORDER, 123, _OBJID_CLIENT, 1, 6, 7)

        timer.start.assert_not_called()

    def test_stop_cancels_pending_refresh(self) -> None:
        _app()
        dispatcher = Dispatcher()
        events: list[object] = []
        dispatcher.add_event_handler(events.append)
        service = WindowsTopmostService()
        service._dispatcher = dispatcher
        service._desktop_window = 123

        service._handle_window_event(1, _EVENT_OBJECT_REORDER, 123, _OBJID_CLIENT, _CHILDID_SELF, 6, 7)
        self.assertTrue(service._refresh_timer.isActive())

        service.stop()
        QTest.qWait(150)

        self.assertFalse(service._refresh_timer.isActive())
        self.assertEqual(events, [])

    def test_timer_dispatches_window_manager_observation(self) -> None:
        dispatcher = Dispatcher()
        events: list[object] = []
        dispatcher.add_event_handler(events.append)
        service = WindowsTopmostService()
        service._dispatcher = dispatcher

        service._refresh_topmost_windows()

        self.assertEqual(events, [WindowManagerEventObserved()])

    def test_window_manager_observation_routes_to_window_manager(self) -> None:
        dispatcher = Dispatcher()
        handlers = EventHandlerRegistry()
        register_event_handlers(handlers)
        window_manager = Mock()
        runtime = ApplicationRuntime.__new__(ApplicationRuntime)
        runtime._window_manager = window_manager
        runtime._app = Mock()
        handlers.install(dispatcher, runtime)

        dispatcher.dispatch_event(WindowManagerEventObserved())

        window_manager.reapply_always_on_top_windows.assert_called_once_with()

    @unittest.skipUnless(sys.platform == "win32", "Windows-native overlay test")
    def test_native_refresh_only_reasserts_z_order(self) -> None:
        controller = AlwaysOnTopWindowController.__new__(AlwaysOnTopWindowController)
        controller._backend = OverlayBackend.WINDOWS_NATIVE
        controller._window = Mock()
        controller._window.isVisible.return_value = True
        controller._window.winId.return_value = 123

        with patch("axidev_osk.windows.overlay.always_on_top._set_window_pos") as set_window_pos:
            controller.reapply_always_on_top()

        set_window_pos.assert_called_once()
        self.assertEqual(set_window_pos.call_args.args[0], 123)
        self.assertEqual(set_window_pos.call_args.args[1], -1)
        self.assertEqual(set_window_pos.call_args.args[-1] & 0x0020, 0)


if __name__ == "__main__":
    unittest.main()
