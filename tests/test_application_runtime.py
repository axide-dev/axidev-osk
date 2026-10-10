from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent

from axidev_osk.app import _set_application_icon
from axidev_osk.messages import DataMap, MessageResult, RuntimeAction
from axidev_osk.python_defaults import osk
from axidev_osk.runtime.app_messages import (
    APP_QUIT_REQUESTED,
    LINUX_OPEN_PERMISSION_SETUP,
    LINUX_PERMISSION_SETUP_OPENED,
    app_activated,
    app_quit,
    pointer_motion_observed,
    secure_input_panel_prepare,
    secure_input_panel_release,
    window_close,
    window_close_requested,
    window_drag_ended,
    window_drag_started,
    window_hide,
    window_show,
)
from axidev_osk.runtime.application import ApplicationRuntime
from axidev_osk.runtime.dispatcher import ACTION_FAILED, ActionFailedArguments
from axidev_osk.runtime.engine_messages import keyboard_reset
from axidev_osk.runtime.registries import ServiceRegistry
from axidev_osk.services.keyboard import KeyboardService
from support import RecordingBackend, qt_app

_KEYBOARD_WINDOW = "keyboard"


def _runtime_without_platform_services(
    root_config: osk.Map | None = None,
    **options: Any,
) -> ApplicationRuntime:
    services = ServiceRegistry()
    services.register("keyboard", KeyboardService(RecordingBackend()), autostart=False)
    return ApplicationRuntime(
        qt_app(),
        root_config=root_config,
        services=services,
        show_startup_windows=False,
        **options,
    )


def _start(test: unittest.TestCase, runtime: ApplicationRuntime) -> None:
    """Run ``ApplicationRuntime.start`` without the Qt event loop or OS signal handlers.

    The app's stylesheet, palette, and font are restored when the test ends.
    """

    app = qt_app()
    previous = (app.styleSheet(), app.palette(), app.font())
    test.addCleanup(lambda: (app.setStyleSheet(previous[0]), app.setPalette(previous[1]), app.setFont(previous[2])))
    with (
        patch.object(app, "exec", return_value=0),
        patch.object(runtime._quit_controller, "install_signal_handlers"),
    ):
        runtime.start()


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
            dispatcher.dispatch(window_drag_started(_KEYBOARD_WINDOW))
            dispatcher.dispatch(pointer_motion_observed(4.25, -5.5))
            dispatcher.dispatch(pointer_motion_observed(5.75, 7.5))
            dispatcher.dispatch(window_drag_ended(_KEYBOARD_WINDOW))
            dispatcher.dispatch(pointer_motion_observed(10, 10))

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

        runtime.context.dispatcher.dispatch(window_drag_started(_KEYBOARD_WINDOW))
        runtime.context.dispatcher.dispatch(pointer_motion_observed(4, 5))

        self.assertEqual(calls, [("move", (_KEYBOARD_WINDOW, 4, 5)), ("commit", 123)])

    def test_pointer_motion_cancels_drag_when_window_is_no_longer_live(self) -> None:
        runtime, service, _window = self._runtime_with_pointer_service()
        runtime._window_manager.get = Mock(return_value=None)

        runtime.context.dispatcher.dispatch(window_drag_started(_KEYBOARD_WINDOW))
        runtime.context.dispatcher.dispatch(pointer_motion_observed(4, 5))

        self.assertIsNone(runtime._pointer_drag.window_id)
        service.end_drag.assert_called_once_with()
        service.commit_surface.assert_not_called()

    def test_pointer_motion_cancels_drag_when_move_fails(self) -> None:
        runtime, service, window = self._runtime_with_pointer_service()
        failures = _record_failures(runtime)
        runtime._window_manager.get = Mock(return_value=window)
        runtime._window_manager.move_by = Mock(side_effect=RuntimeError("move failed"))

        runtime.context.dispatcher.dispatch(window_drag_started(_KEYBOARD_WINDOW))
        runtime.context.dispatcher.dispatch(pointer_motion_observed(4, 5))

        self.assertEqual([failure.message for failure in failures], ["move failed"])
        self.assertIsNone(runtime._pointer_drag.window_id)
        service.end_drag.assert_called_once_with()
        service.commit_surface.assert_not_called()

    def test_pointer_motion_cancels_drag_when_surface_lookup_fails(self) -> None:
        runtime, service, window = self._runtime_with_pointer_service()
        failures = _record_failures(runtime)
        runtime._window_manager.get = Mock(return_value=window)
        runtime._window_manager.move_by = Mock()
        window.winId.side_effect = RuntimeError("surface failed")

        runtime.context.dispatcher.dispatch(window_drag_started(_KEYBOARD_WINDOW))
        runtime.context.dispatcher.dispatch(pointer_motion_observed(4, 5))

        self.assertEqual([failure.message for failure in failures], ["surface failed"])
        self.assertIsNone(runtime._pointer_drag.window_id)
        service.end_drag.assert_called_once_with()
        service.commit_surface.assert_not_called()

    def test_pointer_motion_cancels_drag_when_commit_fails(self) -> None:
        runtime, service, window = self._runtime_with_pointer_service()
        failures = _record_failures(runtime)
        runtime._window_manager.get = Mock(return_value=window)
        runtime._window_manager.move_by = Mock()
        service.commit_surface.side_effect = RuntimeError("commit failed")

        runtime.context.dispatcher.dispatch(window_drag_started(_KEYBOARD_WINDOW))
        runtime.context.dispatcher.dispatch(pointer_motion_observed(4, 5))

        self.assertEqual([failure.message for failure in failures], ["commit failed"])
        self.assertIsNone(runtime._pointer_drag.window_id)
        service.end_drag.assert_called_once_with()

    def test_drag_end_stops_compositor_pointer_movement(self) -> None:
        runtime = _runtime_without_platform_services()
        dispatcher = runtime.context.dispatcher

        with patch.object(runtime._window_manager, "move_by") as move_by:
            dispatcher.dispatch(window_drag_started(_KEYBOARD_WINDOW))
            dispatcher.dispatch(window_drag_ended(_KEYBOARD_WINDOW))
            dispatcher.dispatch(pointer_motion_observed(4, 5))

        move_by.assert_not_called()

    def _runtime_with_pointer_service(self) -> tuple[ApplicationRuntime, Mock, Mock]:
        service = Mock()
        services = ServiceRegistry()
        services.register("keyboard", KeyboardService(RecordingBackend()), autostart=False)
        services.register("relative-pointer", service, autostart=False)
        runtime = ApplicationRuntime(qt_app(), services=services, show_startup_windows=False)
        window = Mock()
        window.isVisible.return_value = True
        window.winId.return_value = 123
        return runtime, service, window


class ApplicationRuntimeProfileTests(unittest.TestCase):
    def test_application_icon_loads_from_packaged_assets(self) -> None:
        app = qt_app()

        _set_application_icon(app)

        self.assertFalse(app.windowIcon().isNull())

    def test_app_activated_reaches_profile_callbacks(self) -> None:
        seen: list[DataMap] = []

        def on_activated(ctx: Any, event: DataMap) -> list[osk.Map]:
            del ctx
            seen.append(event)
            return []

        runtime = _runtime_without_platform_services(_bare_root({"app.activated": on_activated}))
        _start(self, runtime)

        runtime.context.dispatcher.dispatch(app_activated())

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
                    runtime.context.dispatcher.dispatch(RuntimeAction(LINUX_OPEN_PERMISSION_SETUP, {}))

                launcher.assert_called_once_with()
                self.assertEqual(events, [{"opened": opened}])


class ApplicationRuntimeQuitTests(unittest.TestCase):
    def test_confirmed_quit_asks_profile_without_shutting_down(self) -> None:
        runtime = _runtime_without_platform_services()
        _start(self, runtime)
        requests = _record_raw_events(runtime, APP_QUIT_REQUESTED)

        with (
            patch.object(runtime._window_manager, "show"),
            patch.object(qt_app(), "exit") as exit_app,
        ):
            runtime._quit_controller.request_quit("signal")

        self.assertEqual(requests, [{"reason": "signal"}])
        exit_app.assert_not_called()

    def test_default_profile_shows_quit_prompt_on_quit_request(self) -> None:
        runtime = _runtime_without_platform_services()
        _start(self, runtime)

        with (
            patch.object(runtime._window_manager, "show") as show,
            patch.object(qt_app(), "exit") as exit_app,
        ):
            runtime._quit_controller.request_quit("signal")

        show.assert_called_once_with("quit-prompt")
        exit_app.assert_not_called()

    def test_default_profile_shows_quit_prompt_when_keyboard_close_is_requested(self) -> None:
        runtime = _runtime_without_platform_services()
        _start(self, runtime)

        with (
            patch.object(runtime._window_manager, "show") as show,
            patch.object(runtime._window_manager, "close") as close,
            patch.object(qt_app(), "exit") as exit_app,
        ):
            runtime.context.dispatcher.dispatch(window_close_requested(_KEYBOARD_WINDOW))

        show.assert_called_once_with("quit-prompt")
        close.assert_not_called()
        exit_app.assert_not_called()

    def test_quit_action_shuts_down_with_exit_code(self) -> None:
        runtime = _runtime_without_platform_services()
        callback = Mock()
        runtime._quit_controller.register_quit_callback(callback)

        with patch.object(qt_app(), "exit") as exit_app:
            runtime.context.dispatcher.dispatch(app_quit(3))

        callback.assert_called_once_with()
        exit_app.assert_called_once_with(3)

    def test_profile_without_quit_handlers_quits_on_request(self) -> None:
        runtime = _runtime_without_platform_services(_bare_root())
        _start(self, runtime)

        with patch.object(qt_app(), "exit") as exit_app:
            runtime._quit_controller.request_quit("signal")

        exit_app.assert_called_once_with(0)

    def test_profile_without_close_handler_quits_on_window_close_request(self) -> None:
        runtime = _runtime_without_platform_services(_bare_root())
        _start(self, runtime)

        with patch.object(qt_app(), "exit") as exit_app:
            runtime.context.dispatcher.dispatch(window_close_requested("pad"))

        exit_app.assert_called_once_with(0)

    def test_closing_the_last_window_asks_the_profile_with_its_reason(self) -> None:
        runtime = _runtime_without_platform_services(
            _bare_root({"app.quit_requested": lambda ctx, event: []})
        )
        _start(self, runtime)
        requests = _record_raw_events(runtime, APP_QUIT_REQUESTED)

        with patch.object(qt_app(), "exit") as exit_app:
            runtime.context.dispatcher.dispatch(window_close_requested("pad"))

        self.assertEqual(requests, [{"reason": "window_closed"}])
        exit_app.assert_not_called()

    def test_shutdown_stops_the_profile_before_teardown_events(self) -> None:
        resets: list[DataMap] = []
        runtime = _runtime_without_platform_services(
            _bare_root({"keyboard.reset": lambda ctx, event: resets.append(event) or []})
        )
        _start(self, runtime)
        runtime.context.dispatcher.dispatch(keyboard_reset())
        self.assertEqual(len(resets), 1)

        with patch.object(qt_app(), "exit") as exit_app:
            runtime._quit_controller.shutdown()

        self.assertEqual(len(resets), 1)
        exit_app.assert_called_once_with(0)

    def test_quitting_waits_for_queued_work_and_nothing_runs_after_shutdown(self) -> None:
        reopened: list[DataMap] = []

        def reopen(ctx: Any, event: DataMap) -> list[osk.Map]:
            del ctx
            reopened.append(event)
            return [osk.window.show("pad")]

        runtime = _runtime_without_platform_services(_bare_root({"window.close_requested": reopen}))
        _start(self, runtime)
        self.addCleanup(runtime._window_manager.close_all)
        dispatcher = runtime.context.dispatcher
        dispatcher.dispatch(window_show("pad"))

        with patch.object(qt_app(), "exit") as exit_app:
            dispatcher.dispatch(window_close_requested("pad"))
            dispatcher.dispatch(window_show("pad"))

        exit_app.assert_called_once_with(0)
        self.assertEqual(len(reopened), 1)
        self.assertEqual(runtime._window_manager.all_windows(), [])
        self.assertFalse(dispatcher.has_pending())

    def test_profile_without_close_handler_closes_only_that_window_while_another_is_visible(self) -> None:
        root = osk.config(
            active_profile="p",
            profiles={
                "p": osk.profile(
                    windows=[
                        osk.window(id="pad", title="pad", content=osk.box(id="pad:root")),
                        osk.window(id="tool", title="tool", content=osk.box(id="tool:root")),
                    ]
                )
            },
        )
        runtime = _runtime_without_platform_services(root)
        _start(self, runtime)
        dispatcher = runtime.context.dispatcher
        dispatcher.dispatch(window_show("pad"))
        dispatcher.dispatch(window_show("tool"))
        self.addCleanup(runtime._window_manager.close_all)
        tool = runtime._window_manager.get("tool")

        with patch.object(qt_app(), "exit") as exit_app:
            dispatcher.dispatch(window_close_requested("tool"))

        exit_app.assert_not_called()
        self.assertIsNone(runtime._window_manager.get("tool"))
        self.assertFalse(tool.isVisible())
        self.assertTrue(runtime._window_manager.get("pad").isVisible())

    def test_window_close_action_closes_the_window_and_show_rebuilds_one(self) -> None:
        runtime = _runtime_without_platform_services(_bare_root())
        _start(self, runtime)
        dispatcher = runtime.context.dispatcher
        dispatcher.dispatch(window_show("pad"))
        first = runtime._window_manager.get("pad")

        dispatcher.dispatch(window_close("pad"))
        self.assertFalse(first.isVisible())
        self.assertIsNone(runtime._window_manager.get("pad"))

        dispatcher.dispatch(window_show("pad"))
        self.addCleanup(runtime._window_manager.close_all)
        second = runtime._window_manager.get("pad")
        self.assertIsNot(second, first)
        self.assertTrue(second.isVisible())

    def test_every_window_action_reports_an_unknown_window(self) -> None:
        runtime = _runtime_without_platform_services(_bare_root())
        _start(self, runtime)
        failures = _record_failures(runtime)
        actions = [
            osk.window.show("typo"),
            osk.window.hide("typo"),
            osk.window.close("typo"),
            osk.window.set_opacity("typo", 0.5),
            osk.window.block_input("typo", []),
            osk.window.unblock_input("typo"),
        ]

        for action in actions:
            runtime.context.dispatcher.dispatch(RuntimeAction(action["action"], action["arguments"]))

        self.assertEqual(
            [(failure.action, failure.message) for failure in failures],
            [(action["action"], "No window named 'typo' in the active profile") for action in actions],
        )

    def test_window_actions_on_a_defined_window_that_is_not_built_do_nothing(self) -> None:
        runtime = _runtime_without_platform_services(_bare_root())
        _start(self, runtime)
        failures = _record_failures(runtime)

        for action in (osk.window.hide("pad"), osk.window.close("pad"), osk.window.set_opacity("pad", 0.5)):
            runtime.context.dispatcher.dispatch(RuntimeAction(action["action"], action["arguments"]))

        self.assertEqual(failures, [])
        self.assertEqual(runtime._window_manager.all_windows(), [])


class SecureInputPanelLifecycleTests(unittest.TestCase):
    def _runtime(self, root_config: osk.Map | None = None) -> tuple[ApplicationRuntime, RecordingBackend, KeyboardService]:
        backend = RecordingBackend()
        keyboard = KeyboardService(backend)
        services = ServiceRegistry()
        services.register("keyboard", keyboard, autostart=False)
        runtime = ApplicationRuntime(
            qt_app(),
            root_config=root_config,
            services=services,
            show_startup_windows=False,
        )
        _start(self, runtime)
        self.addCleanup(runtime._window_manager.close_all)
        return runtime, backend, keyboard

    def _panel_visible(self, runtime: ApplicationRuntime) -> bool:
        window = runtime._window_manager.get(_KEYBOARD_WINDOW)
        return window is not None and window.isVisible()

    def test_repeated_prepare_release_cycles_rebuild_window_and_restart_keyboard(self) -> None:
        runtime, backend, keyboard = self._runtime()
        dispatcher = runtime.context.dispatcher

        with patch.object(keyboard, "reset_state", wraps=keyboard.reset_state) as reset_state:
            dispatcher.dispatch(secure_input_panel_prepare())
            first = runtime._window_manager.get(_KEYBOARD_WINDOW)
            dispatcher.dispatch(secure_input_panel_prepare())
            self.assertIs(runtime._window_manager.get(_KEYBOARD_WINDOW), first)
            dispatcher.dispatch(secure_input_panel_release())
            self.assertIsNone(runtime._window_manager.get(_KEYBOARD_WINDOW))
            dispatcher.dispatch(secure_input_panel_prepare())

        self.assertTrue(self._panel_visible(runtime))
        self.assertIsNot(runtime._window_manager.get(_KEYBOARD_WINDOW), first)
        self.assertEqual(backend.initialized, 2)
        self.assertEqual(backend.shutdowns, 0)
        reset_state.assert_called_once_with()

    def test_prepare_shows_a_panel_the_profile_hid(self) -> None:
        runtime, _backend, _keyboard = self._runtime()
        dispatcher = runtime.context.dispatcher
        dispatcher.dispatch(secure_input_panel_prepare())

        dispatcher.dispatch(window_hide(_KEYBOARD_WINDOW))
        dispatcher.dispatch(secure_input_panel_prepare())

        self.assertTrue(self._panel_visible(runtime))

    def test_prepare_starts_the_keyboard_even_if_the_profile_already_shows_the_window(self) -> None:
        runtime, backend, _keyboard = self._runtime()
        dispatcher = runtime.context.dispatcher
        dispatcher.dispatch(window_show(_KEYBOARD_WINDOW))

        dispatcher.dispatch(secure_input_panel_prepare())

        self.assertEqual(backend.initialized, 1)
        self.assertTrue(self._panel_visible(runtime))

    def test_release_resets_held_keys_even_if_the_profile_closed_the_window(self) -> None:
        runtime, _backend, keyboard = self._runtime()
        dispatcher = runtime.context.dispatcher
        dispatcher.dispatch(secure_input_panel_prepare())
        dispatcher.dispatch(window_close(_KEYBOARD_WINDOW))

        with patch.object(keyboard, "reset_state") as reset_state:
            dispatcher.dispatch(secure_input_panel_release())

        reset_state.assert_called_once_with()

    def test_prepare_fails_when_keyboard_output_cannot_start(self) -> None:
        runtime, backend, _keyboard = self._runtime()
        backend.ready = False
        backend.status_text = "permission denied"
        failures = _record_failures(runtime)

        runtime.context.dispatcher.dispatch(secure_input_panel_prepare())

        self.assertEqual(
            [failure.message for failure in failures],
            ["Keyboard output is unavailable: permission denied"],
        )
        self.assertIsNone(runtime._window_manager.get(_KEYBOARD_WINDOW))
        self.assertEqual(backend.shutdowns, 1)

    def test_shutdown_completes_after_a_panel_prepare_and_release_cycle(self) -> None:
        runtime, _backend, _keyboard = self._runtime()
        runtime._quit_controller.register_quit_callback(runtime._window_manager.close_all)
        dispatcher = runtime.context.dispatcher

        dispatcher.dispatch(secure_input_panel_prepare())
        dispatcher.dispatch(secure_input_panel_release())
        qt_app().sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        dispatcher.dispatch(secure_input_panel_prepare())

        with patch.object(qt_app(), "exit") as exit_app:
            runtime._quit_controller.shutdown()

        exit_app.assert_called_once_with(0)
        self.assertEqual(runtime._window_manager.all_windows(), [])

    def test_prepare_fails_when_profile_has_no_panel_attachment(self) -> None:
        runtime, backend, _keyboard = self._runtime(_bare_root())
        failures = _record_failures(runtime)

        runtime.context.dispatcher.dispatch(secure_input_panel_prepare())

        self.assertEqual(
            [failure.message for failure in failures],
            ["The active profile has no secure_input_panel attachment"],
        )
        self.assertEqual(backend.initialized, 0)
        self.assertEqual(runtime._window_manager.all_windows(), [])

    def test_failed_panel_creation_rolls_back_and_remains_retryable(self) -> None:
        runtime, backend, _keyboard = self._runtime()
        failures = _record_failures(runtime)
        real_show = runtime._window_manager.show
        attempts: list[str] = []

        def show_failing_once(window_id: str) -> object:
            attempts.append(window_id)
            if len(attempts) == 1:
                raise RuntimeError("window failed")
            return real_show(window_id)

        with patch.object(runtime._window_manager, "show", side_effect=show_failing_once):
            runtime.context.dispatcher.dispatch(secure_input_panel_prepare())
            self.assertEqual([failure.message for failure in failures], ["window failed"])
            self.assertFalse(self._panel_visible(runtime))

            runtime.context.dispatcher.dispatch(secure_input_panel_prepare())

        self.assertTrue(self._panel_visible(runtime))
        self.assertEqual(backend.initialized, 2)
        self.assertEqual(backend.shutdowns, 1)

    def test_failed_key_reset_still_closes_released_panel(self) -> None:
        runtime, _backend, keyboard = self._runtime()
        runtime.context.dispatcher.dispatch(secure_input_panel_prepare())
        failures = _record_failures(runtime)

        with patch.object(keyboard, "reset_state", side_effect=RuntimeError("reset failed")):
            runtime.context.dispatcher.dispatch(secure_input_panel_release())

        self.assertEqual([failure.message for failure in failures], ["reset failed"])
        self.assertIsNone(runtime._window_manager.get(_KEYBOARD_WINDOW))

    def test_failed_panel_prepare_preserves_error_when_cleanup_also_fails(self) -> None:
        runtime, backend, _keyboard = self._runtime()
        failures = _record_failures(runtime)

        with (
            patch.object(runtime._window_manager, "show", side_effect=RuntimeError("window failed")),
            patch.object(runtime._window_manager, "close", side_effect=RuntimeError("cleanup failed")),
            patch("axidev_osk.runtime.application._logger") as logger,
        ):
            runtime.context.dispatcher.dispatch(secure_input_panel_prepare())

        self.assertEqual([failure.message for failure in failures], ["window failed"])
        self.assertEqual(backend.shutdowns, 1)
        logger.exception.assert_called_once_with("Failed to close a partially prepared secure input panel")


if __name__ == "__main__":
    unittest.main()
