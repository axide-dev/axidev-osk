from __future__ import annotations

import unittest
from unittest.mock import patch

from axidev_osk.runtime.application import ApplicationRuntime
from axidev_osk.runtime.registries import ServiceRegistry
from axidev_osk.runtime.testing import make_test_context
from axidev_osk.services import register_services
from axidev_osk.services.displays import DisplayService
from axidev_osk.services.keyboard import KeyboardService
from support import RecordingBackend, qt_app


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

    def test_a_service_name_can_be_registered_once(self) -> None:
        services = ServiceRegistry()
        first = RecordingService("first", [])
        services.register("keyboard", first)

        with self.assertRaisesRegex(ValueError, "Service 'keyboard' is already registered"):
            services.register("keyboard", RecordingService("second", []))
        self.assertIs(services.find("keyboard"), first)

    def test_register_services_honors_the_include_filter(self) -> None:
        qt_app()
        services = ServiceRegistry()
        keyboard = KeyboardService(RecordingBackend())

        register_services(services, include={"keyboard", "displays"}, keyboard=keyboard)

        self.assertIs(services.find("keyboard"), keyboard)
        self.assertIsInstance(services.find("displays"), DisplayService)
        for name in ("single_instance", "wayland_relative_pointer", "hot_corner"):
            with self.subTest(name=name):
                self.assertIsNone(services.find(name))

    def test_test_context_binds_keyboard_without_starting_it(self) -> None:
        backend = RecordingBackend()

        make_test_context(backend)

        self.assertEqual(backend.initialized, 0)
        self.assertEqual(len(backend.observers), 1)

    def test_runtime_starts_and_stops_registered_services_in_order(self) -> None:
        calls: list[str] = []
        services = ServiceRegistry()
        services.register("keyboard", KeyboardService(RecordingBackend()))
        services.register("first", RecordingService("first", calls))
        services.register("deferred", RecordingService("deferred", calls), autostart=False)
        services.register("second", RecordingService("second", calls))
        runtime = ApplicationRuntime(
            qt_app(),
            services=services,
            confirm_quit=False,
            show_startup_windows=False,
        )

        def exec_and_quit() -> int:
            runtime._quit_controller.request_quit("signal")
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
