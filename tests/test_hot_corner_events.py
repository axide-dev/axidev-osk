from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

from axidev_osk.hot_corner.controller import HotCornerWindowToggleController, ScreenCorner
from axidev_osk.hot_corner.service import HotCornerService
from axidev_osk.messages import MessageResult
from axidev_osk.runtime.app_messages import HOT_CORNER_TRIGGERED, HotCornerTriggeredArguments, display_configuration_changed
from axidev_osk.windows.overlay.always_on_top import OverlayBackend
from support import RecordingBackend, hot_corner_config, make_test_engine


class FakeOverlayController:
    def __init__(self, backend: OverlayBackend = OverlayBackend.X11_UTILITY) -> None:
        self.backend = backend

    def move_to(self, position: QPoint, *, screen_geometry: QRect | None = None) -> None:
        del position, screen_geometry

    def handle_show(self) -> bool:
        return True

    def set_screen(self, screen: object) -> None:
        del screen

    def move_to_anchored(
        self,
        position: QPoint,
        *,
        anchors: int,
        screen_geometry: QRect | None = None,
    ) -> None:
        del anchors
        self.move_to(position, screen_geometry=screen_geometry)

    def release_resources(self) -> None:
        return None


class HotCornerEventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.closeAllWindows()
        cls.app.processEvents()
        cls.app.quit()
        cls.app.processEvents()

    def test_dwell_completion_emits_hot_corner_triggered(self) -> None:
        engine = make_test_engine(RecordingBackend())
        events: list[HotCornerTriggeredArguments] = []

        def record_event(event: HotCornerTriggeredArguments) -> MessageResult:
            events.append(event)
            return []

        engine.dispatcher.add_event_handler(HOT_CORNER_TRIGGERED, record_event)
        overlay = FakeOverlayController(backend=OverlayBackend.X11_UTILITY_BRIDGE)

        with patch(
            "axidev_osk.hot_corner.controller.configure_hot_corner_overlay",
            return_value=overlay,
        ):
            controller = HotCornerWindowToggleController(
                engine.dispatcher,
                config=hot_corner_config(dwell_ms=1),
            )

        try:
            controller._active_corner = ScreenCorner.BOTTOM_LEFT
            controller._active_screen = self.app.primaryScreen()
            controller._entered_at = time.monotonic() - 1
            with patch.object(controller, "_show_indicator_for_screen"):
                controller._poll_active_sensor()
                controller._poll_active_sensor()

            self.assertEqual(events, [HotCornerTriggeredArguments(corner="bottom_left")])
        finally:
            controller.stop()
            controller._indicator.close()


class HotCornerServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_start_without_configuration_builds_no_controller(self) -> None:
        engine = make_test_engine(RecordingBackend())
        service = HotCornerService()

        with patch("axidev_osk.hot_corner.service.HotCornerWindowToggleController") as controller_type:
            service.start(engine.dispatcher)
            engine.dispatcher.dispatch(display_configuration_changed())
            service.stop()

        controller_type.assert_not_called()

    def test_configured_start_runs_controller_with_profile_settings(self) -> None:
        engine = make_test_engine(RecordingBackend())
        service = HotCornerService()
        settings = hot_corner_config(dwell_ms=150)
        corners = frozenset({"top_left", "bottom_right"})
        service.configure(settings, corners)

        with patch("axidev_osk.hot_corner.service.HotCornerWindowToggleController") as controller_type:
            service.start(engine.dispatcher)
            engine.dispatcher.dispatch(display_configuration_changed())
            service.stop()

        controller_type.assert_called_once_with(
            engine.dispatcher,
            config=settings,
            corners=corners,
            parent=None,
        )
        controller = controller_type.return_value
        controller.start.assert_called_once_with()
        controller.refresh_screen_configuration.assert_called_once_with()
        controller.stop.assert_called_once_with()

    def test_configuring_after_start_restarts_the_sensors_and_stop_forgets_them(self) -> None:
        engine = make_test_engine(RecordingBackend())
        service = HotCornerService()

        with patch("axidev_osk.hot_corner.service.HotCornerWindowToggleController") as controller_type:
            service.start(engine.dispatcher)
            service.configure(hot_corner_config(dwell_ms=150), frozenset({"top_left"}))
            service.configure(hot_corner_config(dwell_ms=300), frozenset({"top_left"}))
            service.stop()
            engine.dispatcher.dispatch(display_configuration_changed())

        self.assertEqual([call.kwargs["config"].dwell_ms for call in controller_type.call_args_list], [150, 300])
        self.assertEqual(controller_type.return_value.stop.call_count, 2)
        controller_type.return_value.refresh_screen_configuration.assert_not_called()


if __name__ == "__main__":
    unittest.main()
