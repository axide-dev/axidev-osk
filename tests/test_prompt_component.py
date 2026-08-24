from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from axidev_osk.messages import MessageResult
from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.runtime.events import PROMPT_RESOLVED, PromptResolvedArguments
from axidev_osk.runtime.config_paths import surface_source_path
from axidev_osk.runtime.testing import make_test_context


class FakeKeyboardBackend:
    ready = True
    status_text = ""
    needs_permission_setup = False

    def add_key_state_listener(self, listener: object) -> object:
        del listener
        return lambda: None

    def key_name_for_output(self, output):
        return output.output_key

    def state_tags_for_key(self, output_key):
        del output_key
        return frozenset()

    def is_key_down(self, key_name):
        del key_name
        return False


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class PromptComponentTests(unittest.TestCase):
    def test_prompt_button_only_emits_resolution_event(self) -> None:
        _app()
        config = build_default_app_config()
        context = make_test_context(FakeKeyboardBackend(), config=config)
        prompt = config.quit_prompt
        resolved: list[PromptResolvedArguments] = []

        def record(event: PromptResolvedArguments) -> MessageResult:
            resolved.append(event)
            return []

        context.dispatcher.add_event_handler(PROMPT_RESOLVED, record)
        window = QWidget()
        self.addCleanup(window.close)
        prompt_path = surface_source_path(
            config,
            prompt.window_id,
            prompt.surface_id,
        ).child("component", prompt.id)
        prompt_widget = context.components.build(
            prompt,
            context,
            source_path=prompt_path,
            host=window,
        )
        prompt_widget.setParent(window)
        window.show()

        button = next(
            child
            for child in prompt_widget.findChildren(QPushButton)
            if child.property("componentId") == prompt.buttons[0].id
        )
        button.click()

        self.assertEqual(resolved, [PromptResolvedArguments(prompt_id=prompt.id, result="accepted")])
        self.assertTrue(window.isVisible())


if __name__ == "__main__":
    unittest.main()
