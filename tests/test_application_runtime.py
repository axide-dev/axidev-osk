from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

from axidev_osk.app import _set_application_icon
from axidev_osk.messages import DataMap, MessageResult, RuntimeAction
from axidev_osk.python_defaults import osk
from axidev_osk.runtime.actions import (
    LINUX_OPEN_PERMISSION_SETUP,
    app_quit,
    secure_input_panel_prepare,
    secure_input_panel_release,
)
from axidev_osk.runtime.application import ApplicationRuntime
from axidev_osk.runtime.engine_messages import APP_QUIT_REQUESTED, LINUX_PERMISSION_SETUP_OPENED
from axidev_osk.runtime.events import (
    ACTION_FAILED,
    ActionFailedArguments,
    app_activated,
    pointer_motion_observed,
    window_close_requested,
    window_drag_ended,
    window_drag_started,
)
from axidev_osk.runtime.registries import ServiceRegistry
from axidev_osk.services.keyboard import KeyboardService

_KEYBOARD_WINDOW = "keyboard"


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _keyboard_backend() -> Mock:
    backend = Mock()
    backend.initialize.return_value = True
    backend.add_observation_listener.return_value = lambda: None
    backend.ready = True
    backend.status_text = "ready"
    backend.needs_permission_setup = False
    backend.permission_setup_text = ""
    return backend


def _runtime_without_platform_services(
    root_config: osk.Map | None = None,
    **options: Any,
) -> ApplicationRuntime:
    services = ServiceRegistry()
    services.register("keyboard", KeyboardService(_keyboard_backend()), autostart=False)
    return ApplicationRuntime(
        _app(),
        root_config=root_config,
        services=services,
        show_startup_windows=False,
        **options,
    )


def _start_profile(runtime: ApplicationRuntime) -> None:
    """Start the profile and attachments the way ``start`` does, without the Qt loop."""

    runtime.context.engine.profile.start(runtime.profile)
    runtime._attachments.start(runtime.profile)


def _bare_root(on: dict[str, Any] | None = None) -> osk.Map:
    return osk.config(
        active_profile="p",
        profiles={
            "p": osk.profile(
                windows=[osk.window(id="pad", title="pad", content=osk.box(id="pad:root"))],
                on=on,
            )
        },
    )


def _record_failures(runtime: ApplicationRuntime) -> list[ActionFailedArguments]:
    failures: list[ActionFailedArguments] = []

    def record(event: ActionFailedArguments) -> list[object]:
        failures.append(event)
        return []

    runtime.context.dispatcher.add_event_handler(ACTION_FAILED, record)
    return failures


def _record_raw_events(runtime: ApplicationRuntime, name: str) -> list[DataMap]:
    events: list[DataMap] = []

    def record(arguments: DataMap) -> MessageResult:
        events.append(arguments)
        return []

    runtime.context.dispatcher.add_raw_event_handler(name, record)
    return events


class ApplicationRuntimePointerDragTests(unittest.TestCase):
    def test_compositor_pointer_motion_moves_only_active_drag(self) -> None:
        runtime = _runtime_without_platform_services()
        window = Mock()
        window.isVisible.return_value = True
        window.winId.return_value = 123
        dispatcher = runtime.context.dispatcher

        with (
            patch.object(runtime._window_manager, "get", return_value=window),
            patch.object(runtime._window_manager, "move_by") as move_by,
        ):
            dispatcher.dispatch_event(window_drag_started(_KEYBOARD_WINDOW))
            dispatcher.dispatch_event(pointer_motion_observed(4.25, -5.5))
            dispatcher.dispatch_event(pointer_motion_observed(5.75, 7.5))
            dispatcher.dispatch_event(window_drag_ended(_KEYBOARD_WINDOW))
            dispatcher.dispatch_event(pointer_motion_observed(10, 10))

        self.assertEqual(
            move_by.call_args_list,
            [unittest.mock.call(_KEYBOARD_WINDOW, 4, -5), unittest.mock.call(_KEYBOARD_WINDOW, 6, 7)],
        )

    def test_pointer_motion_moves_before_committing_current_surface(self) -> None:
        runtime, service, window = self._runtime_with_pointer_service()
        calls: list[object] = []
        runtime._window_manager.get = Mock(return_value=window)
        runtime._window_manager.move_by = Mock(side_effect=lambda *args: calls.append(("move", args)))
        service.commit_surface.side_effect = lambda surface: calls.append(("commit", surface))

        runtime.context.dispatcher.dispatch_event(window_drag_started(_KEYBOARD_WINDOW))
        runtime.context.dispatcher.dispatch_event(pointer_motion_observed(4, 5))

        self.assertEqual(calls, [("move", (_KEYBOARD_WINDOW, 4, 5)), ("commit", 123)])

    def test_pointer_motion_cancels_drag_when_window_is_no_longer_live(self) -> None:
        runtime, service, _window = self._runtime_with_pointer_service()
        runtime._window_manager.get = Mock(return_value=None)

        runtime.context.dispatcher.dispatch_event(window_drag_started(_KEYBOARD_WINDOW))
        runtime.context.dispatcher.dispatch_event(pointer_motion_observed(4, 5))

        self.assertIsNone(runtime._active_pointer_drag_window_id)
        service.end_drag.assert_called_once_with()
        service.commit_surface.assert_not_called()

    def test_pointer_motion_cancels_drag_when_move_fails(self) -> None:
        runtime, service, window = self._runtime_with_pointer_service()
        failures = _record_failures(runtime)
        runtime._window_manager.get = Mock(return_value=window)
        runtime._window_manager.move_by = Mock(side_effect=RuntimeError("move failed"))

        runtime.context.dispatcher.dispatch_event(window_drag_started(_KEYBOARD_WINDOW))
        runtime.context.dispatcher.dispatch_event(pointer_motion_observed(4, 5))

        self.assertEqual([failure.message for failure in failures], ["move failed"])
        self.assertIsNone(runtime._active_pointer_drag_window_id)
        service.end_drag.assert_called_once_with()
        service.commit_surface.assert_not_called()

    def test_pointer_motion_cancels_drag_when_surface_lookup_fails(self) -> None:
        runtime, service, window = self._runtime_with_pointer_service()
        failures = _record_failures(runtime)
        runtime._window_manager.get = Mock(return_value=window)
        runtime._window_manager.move_by = Mock()
        window.winId.side_effect = RuntimeError("surface failed")

        runtime.context.dispatcher.dispatch_event(window_drag_started(_KEYBOARD_WINDOW))
        runtime.context.dispatcher.dispatch_event(pointer_motion_observed(4, 5))

        self.assertEqual([failure.message for failure in failures], ["surface failed"])
        self.assertIsNone(runtime._active_pointer_drag_window_id)
        service.end_drag.assert_called_once_with()
        service.commit_surface.assert_not_called()

    def test_pointer_motion_cancels_drag_when_commit_fails(self) -> None:
        runtime, service, window = self._runtime_with_pointer_service()
        failures = _record_failures(runtime)
        runtime._window_manager.get = Mock(return_value=window)
        runtime._window_manager.move_by = Mock()
        service.commit_surface.side_effect = RuntimeError("commit failed")

        runtime.context.dispatcher.dispatch_event(window_drag_started(_KEYBOARD_WINDOW))
        runtime.context.dispatcher.dispatch_event(pointer_motion_observed(4, 5))

        self.assertEqual([failure.message for failure in failures], ["commit failed"])
        self.assertIsNone(runtime._active_pointer_drag_window_id)
        service.end_drag.assert_called_once_with()

    def test_drag_end_stops_compositor_pointer_movement(self) -> None:
        runtime = _runtime_without_platform_services()
        dispatcher = runtime.context.dispatcher

        with patch.object(runtime._window_manager, "move_by") as move_by:
            dispatcher.dispatch_event(window_drag_started(_KEYBOARD_WINDOW))
            dispatcher.dispatch_event(window_drag_ended(_KEYBOARD_WINDOW))
            dispatcher.dispatch_event(pointer_motion_observed(4, 5))

        move_by.assert_not_called()

    def _runtime_with_pointer_service(self) -> tuple[ApplicationRuntime, Mock, Mock]:
        service = Mock()
        services = ServiceRegistry()
        services.register("keyboard", KeyboardService(_keyboard_backend()), autostart=False)
        services.register("relative-pointer", service, autostart=False)
        runtime = ApplicationRuntime(_app(), services=services, show_startup_windows=False)
        window = Mock()
        window.isVisible.return_value = True
        window.winId.return_value = 123
        return runtime, service, window


class ApplicationRuntimeProfileTests(unittest.TestCase):
    def test_default_profile_prompt_windows_remain_fully_opaque(self) -> None:
        profile = _runtime_without_platform_services().profile
        prompt_ids = (
            "quit-prompt",
            "permission-prompt",
            "permission-logout",
            "permission-terminal-opened",
            "permission-no-terminal",
        )

        self.assertEqual(profile.window(_KEYBOARD_WINDOW).opacity, 0.85)
        self.assertEqual({profile.window(window_id).opacity for window_id in prompt_ids}, {1.0})

    def test_default_permission_prompt_has_one_setup_action(self) -> None:
        profile = _runtime_without_platform_services().profile

        node_ids = [node.id for node in profile.window("permission-prompt").content.walk()]

        self.assertEqual(node_ids.count("permission-prompt:open_terminal"), 1)
        self.assertFalse(any("setup_here" in node_id for node_id in node_ids))

    def test_application_icon_loads_from_packaged_assets(self) -> None:
        app = _app()

        _set_application_icon(app)

        self.assertFalse(app.windowIcon().isNull())

    def test_app_activated_reaches_profile_callbacks(self) -> None:
        seen: list[DataMap] = []

        def on_activated(ctx: Any, event: DataMap) -> list[osk.Map]:
            del ctx
            seen.append(event)
            return []

        runtime = _runtime_without_platform_services(_bare_root({"app.activated": on_activated}))
        _start_profile(runtime)

        runtime.context.dispatcher.dispatch_event(app_activated())

        self.assertEqual(seen, [{}])

    def test_open_permission_setup_reports_launcher_result(self) -> None:
        for opened in (True, False):
            with self.subTest(opened=opened):
                runtime = _runtime_without_platform_services()
                events = _record_raw_events(runtime, LINUX_PERMISSION_SETUP_OPENED)

                with patch(
                    "axidev_osk.runtime.application.open_permission_setup_terminal",
                    return_value=opened,
                ) as launcher:
                    runtime.context.dispatcher.dispatch_action(RuntimeAction(LINUX_OPEN_PERMISSION_SETUP, {}))

                launcher.assert_called_once_with()
                self.assertEqual(events, [{"opened": opened}])


class ApplicationRuntimeQuitTests(unittest.TestCase):
    def test_confirmed_quit_asks_profile_without_shutting_down(self) -> None:
        runtime = _runtime_without_platform_services()
        _start_profile(runtime)
        requests = _record_raw_events(runtime, APP_QUIT_REQUESTED)

        with (
            patch.object(runtime._window_manager, "show"),
            patch.object(_app(), "exit") as exit_app,
        ):
            runtime._quit_controller.request_quit()

        self.assertEqual(requests, [{"reason": "request"}])
        exit_app.assert_not_called()

    def test_default_profile_shows_quit_prompt_on_quit_request(self) -> None:
        runtime = _runtime_without_platform_services()
        _start_profile(runtime)

        with (
            patch.object(runtime._window_manager, "show") as show,
            patch.object(_app(), "exit") as exit_app,
        ):
            runtime._quit_controller.request_quit()

        show.assert_called_once_with("quit-prompt")
        exit_app.assert_not_called()

    def test_default_profile_shows_quit_prompt_when_keyboard_close_is_requested(self) -> None:
        runtime = _runtime_without_platform_services()
        _start_profile(runtime)

        with (
            patch.object(runtime._window_manager, "show") as show,
            patch.object(_app(), "exit") as exit_app,
        ):
            runtime.context.dispatcher.dispatch_event(window_close_requested(_KEYBOARD_WINDOW))

        show.assert_called_once_with("quit-prompt")
        exit_app.assert_not_called()

    def test_quit_action_shuts_down_with_exit_code(self) -> None:
        runtime = _runtime_without_platform_services()
        callback = Mock()
        runtime._quit_controller.register_quit_callback(callback)

        with patch.object(_app(), "exit") as exit_app:
            runtime.context.dispatcher.dispatch_action(app_quit(3))

        callback.assert_called_once_with()
        exit_app.assert_called_once_with(3)

    def test_profile_without_quit_handlers_quits_on_request(self) -> None:
        runtime = _runtime_without_platform_services(_bare_root())
        _start_profile(runtime)

        with patch.object(_app(), "exit") as exit_app:
            runtime._quit_controller.request_quit()

        exit_app.assert_called_once_with(0)

    def test_profile_without_close_handler_quits_on_window_close_request(self) -> None:
        runtime = _runtime_without_platform_services(_bare_root())
        _start_profile(runtime)

        with patch.object(_app(), "exit") as exit_app:
            runtime.context.dispatcher.dispatch_event(window_close_requested("pad"))

        exit_app.assert_called_once_with(0)


class SecureInputPanelLifecycleTests(unittest.TestCase):
    def _runtime(self, root_config: osk.Map | None = None) -> tuple[ApplicationRuntime, Mock, KeyboardService]:
        backend = _keyboard_backend()
        keyboard = KeyboardService(backend)
        services = ServiceRegistry()
        services.register("keyboard", keyboard, autostart=False)
        runtime = ApplicationRuntime(
            _app(),
            root_config=root_config,
            services=services,
            show_startup_windows=False,
        )
        _start_profile(runtime)
        return runtime, backend, keyboard

    def test_repeated_prepare_release_cycles_rebuild_window_and_restart_keyboard(self) -> None:
        runtime, backend, keyboard = self._runtime()
        dispatcher = runtime.context.dispatcher
        lock_window = Mock()

        with (
            patch.object(runtime._window_manager, "show", return_value=lock_window) as show,
            patch.object(runtime._window_manager, "destroy") as destroy,
            patch.object(keyboard, "reset_state", wraps=keyboard.reset_state) as reset_state,
        ):
            dispatcher.dispatch_action(secure_input_panel_prepare())
            dispatcher.dispatch_action(secure_input_panel_prepare())
            dispatcher.dispatch_action(secure_input_panel_release())
            dispatcher.dispatch_action(secure_input_panel_prepare())

        self.assertEqual(backend.initialize.call_count, 2)
        backend.shutdown.assert_not_called()
        reset_state.assert_called_once_with()
        self.assertEqual(show.call_args_list, [unittest.mock.call(_KEYBOARD_WINDOW)] * 2)
        self.assertEqual(
            lock_window.set_close_enabled.call_args_list,
            [unittest.mock.call(False), unittest.mock.call(False)],
        )
        destroy.assert_called_once_with(_KEYBOARD_WINDOW)

    def test_prepare_fails_when_profile_has_no_panel_attachment(self) -> None:
        runtime, backend, _keyboard = self._runtime(_bare_root())
        failures = _record_failures(runtime)

        with patch.object(runtime._window_manager, "show") as show:
            runtime.context.dispatcher.dispatch_action(secure_input_panel_prepare())

        self.assertEqual(
            [failure.message for failure in failures],
            ["The active profile has no secure_input_panel attachment"],
        )
        show.assert_not_called()
        backend.initialize.assert_not_called()
        self.assertFalse(runtime._secure_input_panel_prepared)

    def test_failed_panel_creation_rolls_back_and_remains_retryable(self) -> None:
        runtime, backend, _keyboard = self._runtime()
        failures = _record_failures(runtime)

        with (
            patch.object(
                runtime._window_manager,
                "show",
                side_effect=(RuntimeError("window failed"), Mock()),
            ) as show,
            patch.object(runtime._window_manager, "destroy") as destroy,
        ):
            runtime.context.dispatcher.dispatch_action(secure_input_panel_prepare())
            self.assertEqual([failure.message for failure in failures], ["window failed"])
            self.assertFalse(runtime._secure_input_panel_prepared)

            runtime.context.dispatcher.dispatch_action(secure_input_panel_prepare())

        self.assertEqual(show.call_count, 2)
        destroy.assert_called_once_with(_KEYBOARD_WINDOW)
        self.assertEqual(backend.initialize.call_count, 2)
        backend.shutdown.assert_called_once_with()
        self.assertTrue(runtime._secure_input_panel_prepared)

    def test_failed_key_reset_still_destroys_released_panel(self) -> None:
        runtime, _backend, keyboard = self._runtime()
        runtime._secure_input_panel_prepared = True
        failures = _record_failures(runtime)

        with (
            patch.object(keyboard, "reset_state", side_effect=RuntimeError("reset failed")),
            patch.object(runtime._window_manager, "destroy") as destroy,
        ):
            runtime.context.dispatcher.dispatch_action(secure_input_panel_release())

        self.assertEqual([failure.message for failure in failures], ["reset failed"])
        destroy.assert_called_once_with(_KEYBOARD_WINDOW)
        self.assertFalse(runtime._secure_input_panel_prepared)

    def test_failed_panel_prepare_preserves_error_when_cleanup_also_fails(self) -> None:
        runtime, backend, _keyboard = self._runtime()
        failures = _record_failures(runtime)

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
        ):
            runtime.context.dispatcher.dispatch_action(secure_input_panel_prepare())

        self.assertEqual([failure.message for failure in failures], ["window failed"])
        backend.shutdown.assert_called_once_with()
        logger.exception.assert_called_once_with(
            "Failed to destroy a partially prepared secure input panel"
        )
        self.assertFalse(runtime._secure_input_panel_prepared)


if __name__ == "__main__":
    unittest.main()
