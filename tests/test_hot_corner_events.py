from __future__ import annotations

import time
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

from axidev_osk.messages import MessageResult, RuntimeAction
from axidev_osk.config.models import HotCornerConfig
from axidev_osk.hot_corner.controller import HotCornerWindowToggleController, ScreenCorner
from axidev_osk.runtime.application import ApplicationRuntime
from axidev_osk.runtime.actions import (
    WINDOW_TOGGLE_OPACITY,
    WINDOW_SHOW,
    WindowArguments,
    WindowToggleOpacityArguments,
    decode_window,
    decode_window_toggle_opacity,
    window_hide,
    window_show,
    window_toggle_opacity,
)
from axidev_osk.runtime.events import (
    HOT_CORNER_TRIGGERED,
    HotCornerTriggeredArguments,
    component_pressed,
    component_released,
    decode_component_pressed,
    hot_corner_triggered,
)
from axidev_osk.runtime.config_paths import surface_source_path
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

    def initialize(self) -> bool:
        return True

    def shutdown(self) -> None:
        return None

    def add_key_state_listener(self, listener):
        del listener
        return lambda: None

    def key_down(self, output, active_state_tags):
        del output, active_state_tags
        return SimpleNamespace(name="press")

    def key_up(self, handle) -> None:
        del handle

    def is_key_down(self, key_name: str) -> bool:
        del key_name
        return False

    def key_name_for_output(self, output) -> str:
        return output.output_key

    def state_tags_for_key(self, output_key: str) -> frozenset[str]:
        tags = {
            "ShiftLeft": frozenset({"shift"}),
            "ShiftRight": frozenset({"shift"}),
            "CapsLock": frozenset({"caps"}),
        }
        return tags.get(output_key, frozenset())


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
        events: list[HotCornerTriggeredArguments] = []

        def record_event(event: HotCornerTriggeredArguments) -> MessageResult:
            events.append(event)
            return []

        context.dispatcher.add_event_handler(HOT_CORNER_TRIGGERED, record_event)
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

            self.assertEqual(events, [HotCornerTriggeredArguments(corner="bottom_left")])
        finally:
            controller.stop()
            controller._indicator.close()

    def test_runtime_handler_dispatches_bound_window_command(self) -> None:
        context = make_test_context(FakeKeyboardBackend())
        config = replace(
            context.config,
            hot_corner=HotCornerConfig(bindings={"bottom_left": ["window:keyboard"]}),
        )
        class FakeWindowManager:
            def is_minimized(self, window_id: str) -> bool:
                return False

            def is_opacity_reduced(self, window_id: str) -> bool:
                return False

            def is_visible(self, window_id: str) -> bool:
                return False

        runtime = ApplicationRuntime.__new__(ApplicationRuntime)
        runtime._config = config
        runtime._dispatcher = context.dispatcher
        runtime._window_manager = FakeWindowManager()

        actions = runtime._handle_hot_corner_triggered(HotCornerTriggeredArguments(corner="bottom_left"))

        self.assertEqual(actions, [window_show("window:keyboard")])

    def test_runtime_handler_hides_visible_bound_window(self) -> None:
        context = make_test_context(FakeKeyboardBackend())
        config = replace(
            context.config,
            hot_corner=HotCornerConfig(bindings={"bottom_left": ["window:keyboard"]}),
        )
        class FakeWindowManager:
            def is_minimized(self, window_id: str) -> bool:
                return False

            def is_opacity_reduced(self, window_id: str) -> bool:
                return False

            def is_visible(self, window_id: str) -> bool:
                return True

        runtime = ApplicationRuntime.__new__(ApplicationRuntime)
        runtime._config = config
        runtime._dispatcher = context.dispatcher
        runtime._window_manager = FakeWindowManager()

        actions = runtime._handle_hot_corner_triggered(HotCornerTriggeredArguments(corner="bottom_left"))

        self.assertEqual(actions, [window_hide("window:keyboard")])

    def test_runtime_handler_restores_minimized_bound_window(self) -> None:
        context = make_test_context(FakeKeyboardBackend())
        config = replace(
            context.config,
            hot_corner=HotCornerConfig(bindings={"bottom_left": ["window:keyboard"]}),
        )
        class FakeWindowManager:
            def is_minimized(self, window_id: str) -> bool:
                return True

            def is_opacity_reduced(self, window_id: str) -> bool:
                return False

            def is_visible(self, window_id: str) -> bool:
                return True

        runtime = ApplicationRuntime.__new__(ApplicationRuntime)
        runtime._config = config
        runtime._dispatcher = context.dispatcher
        runtime._window_manager = FakeWindowManager()

        actions = runtime._handle_hot_corner_triggered(HotCornerTriggeredArguments(corner="bottom_left"))

        self.assertEqual(actions, [window_show("window:keyboard")])

    def test_runtime_handler_restores_ghosted_window_without_hiding_it(self) -> None:
        context = make_test_context(FakeKeyboardBackend())
        config = replace(
            context.config,
            hot_corner=HotCornerConfig(bindings={"bottom_left": ["window:keyboard"]}),
        )
        class FakeWindowManager:
            def is_minimized(self, window_id: str) -> bool:
                return False

            def is_opacity_reduced(self, window_id: str) -> bool:
                return True

            def is_visible(self, window_id: str) -> bool:
                return True

        runtime = ApplicationRuntime.__new__(ApplicationRuntime)
        runtime._config = config
        runtime._dispatcher = context.dispatcher
        runtime._window_manager = FakeWindowManager()

        actions = runtime._handle_hot_corner_triggered(HotCornerTriggeredArguments(corner="bottom_left"))

        self.assertEqual(actions, [window_show("window:keyboard")])

    def test_make_test_context_installs_default_event_handlers(self) -> None:
        config = replace(
            make_test_context(FakeKeyboardBackend()).config,
            hot_corner=HotCornerConfig(bindings={"bottom_left": ["window:keyboard"]}),
        )
        context = make_test_context(FakeKeyboardBackend(), config=config, event_handlers=True)
        actions: list[RuntimeAction] = []

        def record_action(arguments: WindowArguments) -> MessageResult:
            actions.append(window_show(arguments.window_id))
            return []

        context.dispatcher.register_action(WINDOW_SHOW, decode_window, record_action, override=True)

        context.dispatcher.dispatch_event(hot_corner_triggered("bottom_left"))

        self.assertEqual(actions, [window_show("window:keyboard")])

    def test_component_action_dispatches_configured_window_opacity_command(self) -> None:
        context = make_test_context(FakeKeyboardBackend())
        window = context.config.windows[0]
        keyboard = window.surface.components[0]
        grid = keyboard.layout.grids[0]
        ghost = next(
            component
            for component in grid.components
            if component.visual.label == "Ghost"
        )
        source = (
            surface_source_path(context.config, window.id, window.surface.id)
            .child("component", keyboard.id)
            .child("layout", keyboard.layout.id)
            .child("grid", grid.id)
            .child("component", ghost.id)
        )
        actions: list[WindowToggleOpacityArguments] = []

        def record_action(arguments: WindowToggleOpacityArguments) -> MessageResult:
            actions.append(arguments)
            return []

        context.dispatcher.register_action(
            WINDOW_TOGGLE_OPACITY,
            decode_window_toggle_opacity,
            record_action,
            override=True,
        )
        context.dispatcher.dispatch_event(component_pressed(source))
        context.dispatcher.dispatch_event(component_released(source))

        self.assertEqual(
            actions,
            [
                WindowToggleOpacityArguments(
                    window_id="window:keyboard",
                    component_id=ghost.id,
                    opacity=0.01,
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
