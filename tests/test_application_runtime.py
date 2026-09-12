from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from axidev_osk.app import _set_application_icon
from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.config.models import WindowConfig
from axidev_osk.runtime.application import ApplicationRuntime
from axidev_osk.runtime.commands import SecureInputPanelPrepare, SecureInputPanelRelease
from axidev_osk.runtime.events import PointerMotionObserved, PromptResolved, WindowDragEnded, WindowDragStarted
from axidev_osk.runtime.registries import ServiceRegistry
from axidev_osk.services.keyboard import KeyboardService


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _runtime_without_platform_services() -> ApplicationRuntime:
    services = ServiceRegistry()
    services.register("keyboard", KeyboardService(Mock()), autostart=False)
    return ApplicationRuntime(_app(), services=services, show_startup_windows=False)


class FakePromptWindow(QWidget):
    def __init__(self, config: WindowConfig, runtime: ApplicationRuntime, result: str) -> None:
        super().__init__()
        self.config = config
        self._runtime = runtime
        self._result = result

    def show(self) -> None:
        prompt = self.config.surface.components[0]
        QTimer.singleShot(
            0,
            lambda: self._runtime.context.dispatcher.dispatch_event(
                PromptResolved(prompt_id=prompt.id, result=self._result),
            ),
        )


class ApplicationRuntimePromptTests(unittest.TestCase):
    def test_compositor_pointer_motion_moves_only_active_drag(self) -> None:
        runtime = _runtime_without_platform_services()
        window_id = runtime.context.config.keyboard_window_id
        window = Mock()
        window.isVisible.return_value = True
        window.winId.return_value = 123

        with (
            patch.object(runtime._window_manager, "get", return_value=window),
            patch.object(runtime._window_manager, "move_by") as move_by,
        ):
            runtime.context.dispatcher.dispatch_event(WindowDragStarted(window_id))
            runtime.context.dispatcher.dispatch_event(PointerMotionObserved(4.25, -5.5))
            runtime.context.dispatcher.dispatch_event(PointerMotionObserved(5.75, 7.5))
            runtime.context.dispatcher.dispatch_event(WindowDragEnded(window_id))
            runtime.context.dispatcher.dispatch_event(PointerMotionObserved(10, 10))

        self.assertEqual(move_by.call_args_list, [unittest.mock.call(window_id, 4, -5), unittest.mock.call(window_id, 6, 7)])

    def test_pointer_motion_moves_before_committing_current_surface(self) -> None:
        service = Mock()
        services = ServiceRegistry()
        services.register("keyboard", KeyboardService(Mock()), autostart=False)
        services.register("relative-pointer", service, autostart=False)
        runtime = ApplicationRuntime(_app(), services=services, show_startup_windows=False)
        window_id = runtime.context.config.keyboard_window_id
        window = Mock()
        window.isVisible.return_value = True
        window.winId.return_value = 123
        calls: list[object] = []
        runtime._window_manager.get = Mock(return_value=window)
        runtime._window_manager.move_by = Mock(side_effect=lambda *args: calls.append(("move", args)))
        service.commit_surface.side_effect = lambda surface: calls.append(("commit", surface))

        runtime.context.dispatcher.dispatch_event(WindowDragStarted(window_id))
        runtime.context.dispatcher.dispatch_event(PointerMotionObserved(4, 5))

        self.assertEqual(calls, [("move", (window_id, 4, 5)), ("commit", 123)])

    def test_pointer_motion_cancels_drag_when_window_is_no_longer_live(self) -> None:
        service = Mock()
        services = ServiceRegistry()
        services.register("keyboard", KeyboardService(Mock()), autostart=False)
        services.register("relative-pointer", service, autostart=False)
        runtime = ApplicationRuntime(_app(), services=services, show_startup_windows=False)
        window_id = runtime.context.config.keyboard_window_id
        runtime._window_manager.get = Mock(return_value=None)

        runtime.context.dispatcher.dispatch_event(WindowDragStarted(window_id))
        runtime.context.dispatcher.dispatch_event(PointerMotionObserved(4, 5))

        self.assertIsNone(runtime._active_pointer_drag_window_id)
        service.end_drag.assert_called_once_with()
        service.commit_surface.assert_not_called()

    def test_pointer_motion_cancels_drag_when_move_fails(self) -> None:
        runtime, service, window_id, window = self._runtime_with_pointer_service()
        runtime._window_manager.get = Mock(return_value=window)
        runtime._window_manager.move_by = Mock(side_effect=RuntimeError("move failed"))

        runtime.context.dispatcher.dispatch_event(WindowDragStarted(window_id))
        with self.assertRaisesRegex(RuntimeError, "move failed"):
            runtime.context.dispatcher.dispatch_event(PointerMotionObserved(4, 5))

        self.assertIsNone(runtime._active_pointer_drag_window_id)
        service.end_drag.assert_called_once_with()
        service.commit_surface.assert_not_called()

    def test_pointer_motion_cancels_drag_when_surface_lookup_fails(self) -> None:
        runtime, service, window_id, window = self._runtime_with_pointer_service()
        runtime._window_manager.get = Mock(return_value=window)
        window.winId.side_effect = RuntimeError("surface failed")

        runtime.context.dispatcher.dispatch_event(WindowDragStarted(window_id))
        with self.assertRaisesRegex(RuntimeError, "surface failed"):
            runtime.context.dispatcher.dispatch_event(PointerMotionObserved(4, 5))

        self.assertIsNone(runtime._active_pointer_drag_window_id)
        service.end_drag.assert_called_once_with()
        service.commit_surface.assert_not_called()

    def test_pointer_motion_cancels_drag_when_commit_fails(self) -> None:
        runtime, service, window_id, window = self._runtime_with_pointer_service()
        runtime._window_manager.get = Mock(return_value=window)
        service.commit_surface.side_effect = RuntimeError("commit failed")

        runtime.context.dispatcher.dispatch_event(WindowDragStarted(window_id))
        with self.assertRaisesRegex(RuntimeError, "commit failed"):
            runtime.context.dispatcher.dispatch_event(PointerMotionObserved(4, 5))

        self.assertIsNone(runtime._active_pointer_drag_window_id)
        service.end_drag.assert_called_once_with()

    def _runtime_with_pointer_service(
        self,
    ) -> tuple[ApplicationRuntime, Mock, str, Mock]:
        service = Mock()
        services = ServiceRegistry()
        services.register("keyboard", KeyboardService(Mock()), autostart=False)
        services.register("relative-pointer", service, autostart=False)
        runtime = ApplicationRuntime(_app(), services=services, show_startup_windows=False)
        window_id = runtime.context.config.keyboard_window_id
        window = Mock()
        window.isVisible.return_value = True
        window.winId.return_value = 123
        return runtime, service, window_id, window

    def test_drag_end_stops_compositor_pointer_movement(self) -> None:
        runtime = _runtime_without_platform_services()
        window_id = runtime.context.config.keyboard_window_id

        with patch.object(runtime._window_manager, "move_by") as move_by:
            runtime.context.dispatcher.dispatch_event(WindowDragStarted(window_id))
            runtime.context.dispatcher.dispatch_event(WindowDragEnded(window_id))
            runtime.context.dispatcher.dispatch_event(PointerMotionObserved(4, 5))

        move_by.assert_not_called()

    def test_linux_permission_prompt_has_one_setup_action(self) -> None:
        prompt = build_default_app_config().linux_permission_prompt

        roles = [button.role for button in prompt.buttons]

        self.assertEqual(roles.count("open_terminal"), 1)
        self.assertNotIn("setup_here", roles)

    def test_prompt_windows_remain_fully_opaque(self) -> None:
        config = build_default_app_config()
        runtime = ApplicationRuntime(_app(), config=config)

        prompt_window = runtime._build_prompt_window_config(config.quit_prompt)

        self.assertEqual(config.windows[0].opacity, 0.85)
        self.assertEqual(prompt_window.opacity, 1.0)

    def test_application_icon_loads_from_packaged_assets(self) -> None:
        app = _app()

        _set_application_icon(app)

        self.assertFalse(app.windowIcon().isNull())

    def test_quit_prompt_uses_configured_title(self) -> None:
        sentinel = "Sentinel Quit Prompt"
        config = build_default_app_config()
        config = replace(config, quit_prompt=replace(config.quit_prompt, title=sentinel))
        runtime = ApplicationRuntime(_app(), config=config)
        created: list[WindowConfig] = []

        def create_transient(window_config: WindowConfig, *, parent: QWidget | None = None) -> FakePromptWindow:
            del parent
            created.append(window_config)
            return FakePromptWindow(window_config, runtime, "rejected")

        with patch.object(runtime._window_manager, "create_transient", side_effect=create_transient):
            self.assertFalse(runtime._show_quit_prompt(None))

        self.assertEqual(created[0].title, sentinel)

    def test_linux_permission_prompt_uses_configured_title(self) -> None:
        sentinel = "Sentinel Permission Prompt"
        config = build_default_app_config()
        config = replace(
            config,
            linux_permission_prompt=replace(config.linux_permission_prompt, title=sentinel),
        )
        runtime = ApplicationRuntime(_app(), config=config)
        created: list[WindowConfig] = []
        parent = QWidget()

        def create_transient(window_config: WindowConfig, *, parent: QWidget | None = None) -> FakePromptWindow:
            del parent
            created.append(window_config)
            return FakePromptWindow(window_config, runtime, "rejected")

        with (
            patch.object(runtime._window_manager, "get_or_create", return_value=parent),
            patch.object(runtime._window_manager, "create_transient", side_effect=create_transient),
        ):
            runtime._linux_permissions.show_prompt()

        self.assertEqual(created[0].title, sentinel)


class SecureInputPanelLifecycleTests(unittest.TestCase):
    def test_repeated_prepare_release_cycles_rebuild_window_and_restart_keyboard(self) -> None:
        backend = Mock()
        backend.initialize.return_value = True
        backend.add_key_state_listener.return_value = lambda: None
        keyboard = KeyboardService(backend)
        services = ServiceRegistry()
        services.register("keyboard", keyboard, autostart=False)
        runtime = ApplicationRuntime(_app(), services=services, show_startup_windows=False)
        lock_window = Mock()

        with (
            patch.object(runtime._window_manager, "show", return_value=lock_window) as show,
            patch.object(runtime._window_manager, "destroy") as destroy,
            patch.object(keyboard, "reset_state") as reset_state,
        ):
            runtime.context.dispatcher.dispatch_command(SecureInputPanelPrepare())
            runtime.context.dispatcher.dispatch_command(SecureInputPanelPrepare())
            runtime.context.dispatcher.dispatch_command(SecureInputPanelRelease())
            runtime.context.dispatcher.dispatch_command(SecureInputPanelPrepare())

        self.assertEqual(backend.initialize.call_count, 2)
        backend.shutdown.assert_not_called()
        reset_state.assert_called_once_with()
        self.assertEqual(show.call_count, 2)
        self.assertEqual(
            lock_window.set_close_enabled.call_args_list,
            [unittest.mock.call(False), unittest.mock.call(False)],
        )
        destroy.assert_called_once_with(runtime._config.keyboard_window_id)

    def test_failed_panel_creation_rolls_back_and_remains_retryable(self) -> None:
        backend = Mock()
        backend.initialize.return_value = True
        backend.add_key_state_listener.return_value = lambda: None
        keyboard = KeyboardService(backend)
        services = ServiceRegistry()
        services.register("keyboard", keyboard, autostart=False)
        runtime = ApplicationRuntime(_app(), services=services, show_startup_windows=False)

        with (
            patch.object(
                runtime._window_manager,
                "show",
                side_effect=(RuntimeError("window failed"), Mock()),
            ) as show,
            patch.object(runtime._window_manager, "destroy") as destroy,
        ):
            with self.assertRaisesRegex(RuntimeError, "window failed"):
                runtime.context.dispatcher.dispatch_command(SecureInputPanelPrepare())
            self.assertFalse(runtime._secure_input_panel_prepared)

            runtime.context.dispatcher.dispatch_command(SecureInputPanelPrepare())

        self.assertEqual(show.call_count, 2)
        destroy.assert_called_once_with(runtime._config.keyboard_window_id)
        self.assertEqual(backend.initialize.call_count, 2)
        backend.shutdown.assert_called_once_with()
        self.assertTrue(runtime._secure_input_panel_prepared)

    def test_failed_key_reset_still_destroys_released_panel(self) -> None:
        runtime = ApplicationRuntime(_app(), show_startup_windows=False)
        runtime._secure_input_panel_prepared = True

        with (
            patch.object(
                runtime._keyboard,
                "reset_state",
                side_effect=RuntimeError("reset failed"),
            ),
            patch.object(runtime._window_manager, "destroy") as destroy,
            self.assertRaisesRegex(RuntimeError, "reset failed"),
        ):
            runtime.context.dispatcher.dispatch_command(SecureInputPanelRelease())

        destroy.assert_called_once_with(runtime._config.keyboard_window_id)
        self.assertFalse(runtime._secure_input_panel_prepared)

    def test_failed_panel_prepare_preserves_error_when_cleanup_also_fails(self) -> None:
        backend = Mock()
        backend.initialize.return_value = True
        backend.add_key_state_listener.return_value = lambda: None
        keyboard = KeyboardService(backend)
        services = ServiceRegistry()
        services.register("keyboard", keyboard, autostart=False)
        runtime = ApplicationRuntime(_app(), services=services, show_startup_windows=False)

        with (
            patch.object(
                runtime._window_manager,
                "show",
                side_effect=RuntimeError("window failed"),
            ),
            patch.object(
                runtime._window_manager,
                "destroy",
                side_effect=RuntimeError("cleanup failed"),
            ),
            patch("axidev_osk.runtime.application._logger") as logger,
            self.assertRaisesRegex(RuntimeError, "window failed"),
        ):
            runtime.context.dispatcher.dispatch_command(SecureInputPanelPrepare())

        backend.shutdown.assert_called_once_with()
        logger.exception.assert_called_once_with(
            "Failed to destroy a partially prepared secure input panel"
        )
        self.assertFalse(runtime._secure_input_panel_prepared)


if __name__ == "__main__":
    unittest.main()
