from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from axidev_osk.app import _set_application_icon
from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.config.models import WindowConfig
from axidev_osk.runtime.application import ApplicationRuntime
from axidev_osk.runtime.events import PromptResolved


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


if __name__ == "__main__":
    unittest.main()
