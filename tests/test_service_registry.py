from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from axidev_osk.runtime.application import ApplicationRuntime
from axidev_osk.runtime.registries import ServiceRegistry
from axidev_osk.runtime.testing import make_test_context
from axidev_osk.services import register_services
from axidev_osk.services.displays import DisplayService
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

    def __init__(self) -> None:
        self.initialized = 0
        self.listeners: list[object] = []

    def initialize(self) -> bool:
        self.initialized += 1
        return True

    def shutdown(self) -> None:
        return None

    def add_observation_listener(self, listener):
        self.listeners.append(listener)
        return lambda: None

    def canonical_key(self, key: str) -> str:
        return key

    def key_up(self, handle) -> None:
        del handle


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
    def test_deferred_service_is_excluded_only_from_autostart(self) -> None:
        services = ServiceRegistry()
        deferred = RecordingService("deferred", [])
        automatic = RecordingService("automatic", [])
        services.register("deferred", deferred, autostart=False)
        services.register("automatic", automatic)

        self.assertEqual(tuple(services.services()), (deferred, automatic))
        self.assertEqual(tuple(services.autostart_services()), (automatic,))

    def test_find_returns_none_for_missing_services_and_get_checks_type(self) -> None:
        services = ServiceRegistry()
        service = RecordingService("first", [])
        services.register("first", service)

        self.assertIs(services.find("first"), service)
        self.assertIsNone(services.find("missing"))
        self.assertIs(services.get("first", RecordingService), service)
        with self.assertRaisesRegex(ValueError, "No service registered for name 'missing'"):
            services.get("missing", RecordingService)
        with self.assertRaisesRegex(TypeError, "Service 'first' is not a KeyboardService"):
            services.get("first", KeyboardService)

    def test_register_services_honors_the_include_filter(self) -> None:
        _app()
        services = ServiceRegistry()
        keyboard = KeyboardService(FakeKeyboardBackend())  # type: ignore[arg-type]

        register_services(services, include={"keyboard", "displays"}, keyboard=keyboard)

        self.assertIs(services.find("keyboard"), keyboard)
        self.assertIsInstance(services.find("displays"), DisplayService)
        for name in ("single_instance", "wayland_relative_pointer", "hot_corner"):
            with self.subTest(name=name):
                self.assertIsNone(services.find(name))

    def test_test_context_starts_only_the_requested_services(self) -> None:
        backend = FakeKeyboardBackend()

        context = make_test_context(backend, services={"keyboard"})

        self.assertEqual(backend.initialized, 1)
        self.assertEqual(len(backend.listeners), 1)
        context.keyboard.shutdown()

    def test_test_context_without_services_binds_keyboard_without_starting_it(self) -> None:
        backend = FakeKeyboardBackend()

        make_test_context(backend)

        self.assertEqual(backend.initialized, 0)
        self.assertEqual(len(backend.listeners), 1)

    def test_runtime_starts_and_stops_registered_services_in_order(self) -> None:
        calls: list[str] = []
        services = ServiceRegistry()
        services.register("keyboard", KeyboardService(FakeKeyboardBackend()))  # type: ignore[arg-type]
        services.register("first", RecordingService("first", calls))
        services.register("deferred", RecordingService("deferred", calls), autostart=False)
        services.register("second", RecordingService("second", calls))
        runtime = ApplicationRuntime(
            _app(),
            services=services,
            confirm_quit=False,
            show_startup_windows=False,
        )

        def exec_and_quit() -> int:
            runtime._quit_controller.request_quit()
            return 0

        with (
            patch.object(runtime._app, "exec", side_effect=exec_and_quit),
            patch.object(runtime._app, "exit"),
        ):
            self.assertEqual(runtime.start(), 0)

        self.assertEqual(
            calls,
            ["start:first", "start:second", "stop:first", "stop:deferred", "stop:second"],
        )


if __name__ == "__main__":
    unittest.main()
