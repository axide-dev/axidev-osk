from __future__ import annotations

import time
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

from axidev_osk.config.models import HotCornerConfig
from axidev_osk.hot_corner.controller import HotCornerWindowToggleController, ScreenCorner
from axidev_osk.runtime.application import ApplicationRuntime
from axidev_osk.runtime.commands import WindowHide, WindowShow
from axidev_osk.runtime.events import HotCornerTriggered
from axidev_osk.runtime.testing import make_test_context
from axidev_osk.windows.overlay.always_on_top import OverlayBackend


class FakeOverlayController:
    def __init__(self, backend: OverlayBackend = OverlayBackend.X11_UTILITY) -> None:
        self.backend = backend

    def move_to(self, position: QPoint, *, screen_geometry: QRect | None = None) -> None:
        del position, screen_geometry

    def handle_show(self) -> bool:
        return True


class FakeKeyboardBackend:
    ready = True
    status_text = "ready"
    needs_permission_setup = False
    permission_setup_text = ""
    permission_setup_script_path = None

    def initialize(self) -> bool:
        return True

    def shutdown(self) -> None:
        return None

    def setup_permissions(self) -> None:
        return None

    def add_key_state_listener(self, listener):
        del listener
        return lambda: None

    def key_down(self, spec):
        del spec
        return SimpleNamespace(name="press")

    def key_up(self, handle) -> None:
        del handle

    def sync_latched_key(self, spec, latched: bool):
        del spec, latched
        return None

    def is_key_down(self, key_name: str) -> bool:
        del key_name
        return False

    def key_name_for_spec(self, spec) -> str | None:
        return getattr(spec, "io_key", None)


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
        context = make_test_context(FakeKeyboardBackend())
        events: list[object] = []
        context.dispatcher.add_event_handler(events.append)
        overlay = FakeOverlayController(backend=OverlayBackend.X11_UTILITY_BRIDGE)

        with patch(
            "axidev_osk.hot_corner.controller.configure_hot_corner_overlay",
            return_value=overlay,
        ):
            controller = HotCornerWindowToggleController(
                context.dispatcher,
                config=HotCornerConfig(dwell_ms=1),
            )

        try:
            controller._active_corner = ScreenCorner.BOTTOM_LEFT
            controller._active_screen = self.app.primaryScreen()
            controller._entered_at = time.monotonic() - 1
            with patch.object(controller, "_show_indicator_for_screen"):
                controller._poll_active_sensor()

            self.assertEqual(events, [HotCornerTriggered(corner="bottom_left")])
        finally:
            controller.stop()
            controller._indicator.close()

    def test_runtime_handler_dispatches_bound_window_command(self) -> None:
        context = make_test_context(FakeKeyboardBackend())
        config = replace(
            context.config,
            hot_corner=HotCornerConfig(bindings={"bottom_left": ["window:keyboard"]}),
        )
        commands: list[object] = []
        context.dispatcher.add_command_handler(WindowShow, lambda command: commands.append(command))
        context.dispatcher.add_command_handler(WindowHide, lambda command: commands.append(command))

        class FakeWindowManager:
            def is_visible(self, window_id: str) -> bool:
                return False

        runtime = ApplicationRuntime.__new__(ApplicationRuntime)
        runtime._config = config
        runtime._dispatcher = context.dispatcher
        runtime._window_manager = FakeWindowManager()

        runtime._handle_hot_corner_triggered(HotCornerTriggered(corner="bottom_left"))

        self.assertEqual(commands, [WindowShow("window:keyboard")])

    def test_runtime_handler_hides_visible_bound_window(self) -> None:
        context = make_test_context(FakeKeyboardBackend())
        config = replace(
            context.config,
            hot_corner=HotCornerConfig(bindings={"bottom_left": ["window:keyboard"]}),
        )
        commands: list[object] = []
        context.dispatcher.add_command_handler(WindowShow, lambda command: commands.append(command))
        context.dispatcher.add_command_handler(WindowHide, lambda command: commands.append(command))

        class FakeWindowManager:
            def is_visible(self, window_id: str) -> bool:
                return True

        runtime = ApplicationRuntime.__new__(ApplicationRuntime)
        runtime._config = config
        runtime._dispatcher = context.dispatcher
        runtime._window_manager = FakeWindowManager()

        runtime._handle_hot_corner_triggered(HotCornerTriggered(corner="bottom_left"))

        self.assertEqual(commands, [WindowHide("window:keyboard")])


if __name__ == "__main__":
    unittest.main()
