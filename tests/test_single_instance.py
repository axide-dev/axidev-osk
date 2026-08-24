from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from axidev_osk.messages import MessageResult
from axidev_osk.runtime.actions import WINDOW_SHOW, WindowArguments, decode_window, window_show
from axidev_osk.runtime.registries import ServiceRegistry
from axidev_osk.runtime.testing import make_test_context
from axidev_osk.services import register_services
from axidev_osk.services.single_instance import ExistingInstanceActivated, WindowsSingleInstanceService


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FakeKeyboardBackend:
    ready = True
    status_text = "ready"
    needs_permission_setup = False
    permission_setup_text = ""

    def add_key_state_listener(self, listener):
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


class WindowsSingleInstanceServiceTests(unittest.TestCase):
    def test_service_registers_before_runtime_backends(self) -> None:
        registry = ServiceRegistry()

        register_services(registry)

        services = list(registry.services())
        self.assertIsInstance(services[0], WindowsSingleInstanceService)

    def test_service_is_inactive_off_windows(self) -> None:
        service = WindowsSingleInstanceService(parent=_app())
        context = make_test_context(FakeKeyboardBackend())

        with patch("axidev_osk.services.single_instance.sys.platform", "linux"):
            service.start(context)

        self.assertIsNone(service._server)

    @unittest.skipUnless(sys.platform == "win32", "Windows local-server integration test")
    def test_second_launch_activates_primary_instance(self) -> None:
        _app()
        context = make_test_context(FakeKeyboardBackend())
        actions: list[object] = []

        def record(arguments: WindowArguments) -> MessageResult:
            actions.append(window_show(arguments.window_id))
            return []

        context.dispatcher.register_action(WINDOW_SHOW, decode_window, record)
        primary = WindowsSingleInstanceService()
        secondary = WindowsSingleInstanceService()
        server_name = f"axidev-osk-test-{uuid4().hex}"

        with TemporaryDirectory() as temp_dir, patch(
            "axidev_osk.services.single_instance._server_name",
            return_value=server_name,
        ), patch(
            "axidev_osk.services.single_instance._lock_path",
            return_value=Path(temp_dir) / "single-instance.lock",
        ):
            primary.start(context)
            try:
                with self.assertRaises(ExistingInstanceActivated):
                    secondary.start(context)
                QTest.qWait(100)
            finally:
                secondary.stop()
                primary.stop()

        self.assertEqual(actions, [window_show(context.config.keyboard_window_id)])


if __name__ == "__main__":
    unittest.main()
