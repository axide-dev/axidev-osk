from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.runtime.application import ApplicationRuntime
from axidev_osk.runtime.registries import ComponentRegistry, ServiceRegistry, SurfaceRegistry
from axidev_osk.services.keyboard import KeyboardService


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

    def initialize(self) -> bool:
        return True

    def shutdown(self) -> None:
        return None

    def add_key_state_listener(self, listener):
        del listener
        return lambda: None

    def is_key_down(self, key_name: str) -> bool:
        del key_name
        return False

    def key_name_for_spec(self, spec) -> str | None:
        return getattr(spec, "io_key", None)


class RecordingService:
    def __init__(self, name: str, calls: list[str]) -> None:
        self._name = name
        self._calls = calls

    def start(self, context) -> None:
        del context
        self._calls.append(f"start:{self._name}")

    def stop(self) -> None:
        self._calls.append(f"stop:{self._name}")


class ServiceRegistryTests(unittest.TestCase):
    def test_runtime_starts_and_stops_registered_services_in_order(self) -> None:
        calls: list[str] = []
        services = ServiceRegistry()
        services.register("keyboard", KeyboardService(FakeKeyboardBackend()))
        services.register("first", RecordingService("first", calls))
        services.register("second", RecordingService("second", calls))
        config = replace(build_default_app_config(), startup_window_ids=())
        runtime = ApplicationRuntime(_app(), config=config, services=services)

        def exec_and_quit() -> int:
            runtime._quit_controller._prompt = lambda parent: True
            runtime._quit_controller.request_quit()
            return 0

        with patch.object(runtime._app, "exec", side_effect=exec_and_quit):
            self.assertEqual(runtime.start(), 0)

        self.assertEqual(calls, ["start:first", "start:second", "stop:first", "stop:second"])


class RegistryErrorTests(unittest.TestCase):
    def test_component_registry_reports_missing_kind(self) -> None:
        registry = ComponentRegistry()

        with self.assertRaisesRegex(ValueError, "No component registered for kind 'missing-component'"):
            registry.build(SimpleNamespace(kind="missing-component"), None)  # type: ignore[arg-type]

    def test_surface_registry_reports_missing_kind(self) -> None:
        registry = SurfaceRegistry()

        with self.assertRaisesRegex(ValueError, "No surface registered for kind 'missing-surface'"):
            registry.build(SimpleNamespace(kind="missing-surface"), None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
