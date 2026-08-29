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
from axidev_osk.runtime.events import PromptResolved, ScreenLockStateChanged
from axidev_osk.runtime.registries import ServiceRegistry
from axidev_osk.services.keyboard import KeyboardService
from axidev_osk.services.kwin_lock import KWinLockService


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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
    def test_repeated_lock_cycles_rebuild_window_and_restart_keyboard(self) -> None:
        backend = Mock()
        backend.initialize.return_value = True
        backend.add_key_state_listener.return_value = lambda: None
        keyboard = KeyboardService(backend)
        kwin_lock = KWinLockService()
        kwin_lock.activate = Mock()
        services = ServiceRegistry()
        services.register("keyboard", keyboard, autostart=False)
        services.register("kwin_lock", kwin_lock, autostart=False)
        runtime = ApplicationRuntime(_app(), services=services, show_startup_windows=False)
        lock_window = Mock()

        with (
            patch.object(runtime._window_manager, "show", return_value=lock_window) as show,
            patch.object(runtime._window_manager, "destroy") as destroy,
        ):
            runtime.context.dispatcher.dispatch_event(ScreenLockStateChanged(locked=True))
            runtime.context.dispatcher.dispatch_event(ScreenLockStateChanged(locked=True))
            runtime.context.dispatcher.dispatch_event(ScreenLockStateChanged(locked=False))
            runtime.context.dispatcher.dispatch_event(ScreenLockStateChanged(locked=True))

        self.assertEqual(backend.initialize.call_count, 2)
        backend.shutdown.assert_called_once_with()
        self.assertEqual(show.call_count, 2)
        self.assertEqual(
            lock_window.set_close_enabled.call_args_list,
            [unittest.mock.call(False), unittest.mock.call(False)],
        )
        destroy.assert_called_once_with(runtime._config.keyboard_window_id)
        self.assertEqual(kwin_lock.activate.call_count, 3)

    def test_failed_lock_window_creation_rolls_back_and_remains_retryable(self) -> None:
        backend = Mock()
        backend.initialize.return_value = True
        backend.add_key_state_listener.return_value = lambda: None
        keyboard = KeyboardService(backend)
        kwin_lock = KWinLockService()
        kwin_lock.activate = Mock()
        services = ServiceRegistry()
        services.register("keyboard", keyboard, autostart=False)
        services.register("kwin_lock", kwin_lock, autostart=False)
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
                runtime.context.dispatcher.dispatch_event(ScreenLockStateChanged(locked=True))
            self.assertIsNone(runtime._screen_locked)

            runtime.context.dispatcher.dispatch_event(ScreenLockStateChanged(locked=True))

        self.assertEqual(show.call_count, 2)
        destroy.assert_called_once_with(runtime._config.keyboard_window_id)
        self.assertEqual(backend.initialize.call_count, 2)
        backend.shutdown.assert_called_once_with()
        kwin_lock.activate.assert_called_once_with()
        self.assertTrue(runtime._screen_locked)

    def test_failed_lock_startup_preserves_error_when_cleanup_also_fails(self) -> None:
        backend = Mock()
        backend.initialize.return_value = True
        backend.add_key_state_listener.return_value = lambda: None
        keyboard = KeyboardService(backend)
        kwin_lock = KWinLockService()
        services = ServiceRegistry()
        services.register("keyboard", keyboard, autostart=False)
        services.register("kwin_lock", kwin_lock, autostart=False)
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
            runtime.context.dispatcher.dispatch_event(ScreenLockStateChanged(locked=True))

        backend.shutdown.assert_called_once_with()
        logger.exception.assert_called_once_with(
            "Failed to destroy a partially started lock window"
        )
        self.assertIsNone(runtime._screen_locked)


if __name__ == "__main__":
    unittest.main()
