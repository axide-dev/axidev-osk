from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from axidev_osk.messages import MessageResult
from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.runtime.events import PROMPT_RESOLVED, PromptResolvedArguments
from axidev_osk.runtime.testing import make_test_context


class FakeKeyboardBackend:
    ready = True
    status_text = ""
    needs_permission_setup = False

    def add_key_state_listener(self, listener: object) -> object:
        del listener
        return lambda: None


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
        prompt_widget = context.components.build(prompt, context, host=window)
        prompt_widget.setParent(window)
        window.show()

        button = next(
            child
            for child in prompt_widget.findChildren(QPushButton)
            if child.property("role") == "accepted"
        )
        button.click()

        self.assertEqual(resolved, [PromptResolvedArguments(prompt_id=prompt.id, result="accepted")])
        self.assertTrue(window.isVisible())


if __name__ == "__main__":
    unittest.main()
