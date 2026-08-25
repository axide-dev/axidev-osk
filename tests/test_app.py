from __future__ import annotations

import unittest
from unittest.mock import Mock

from PySide6.QtCore import QObject

from axidev_osk.app import _input_panel_services
from axidev_osk.platform.overlay import OverlayBackend


class InputPanelRuntimeTests(unittest.TestCase):
    def test_input_panel_starts_only_keyboard_service(self) -> None:
        app = QObject()

        services = _input_panel_services(
            app,
            OverlayBackend.WAYLAND_INPUT_PANEL,
            lock_lifecycle=True,
        )

        self.assertIsNotNone(services)
        self.assertEqual(len(tuple(services.services())), 2)
        self.assertEqual(len(tuple(services.autostart_services())), 1)

    def test_plasma_login_input_panel_starts_keyboard_without_lock_monitor(self) -> None:
        services = _input_panel_services(
            QObject(),
            OverlayBackend.WAYLAND_INPUT_PANEL,
            lock_lifecycle=False,
        )

        self.assertIsNotNone(services)
        self.assertEqual(len(tuple(services.services())), 1)
        self.assertEqual(tuple(services.autostart_services()), tuple(services.services()))

    def test_ordinary_overlay_uses_default_services(self) -> None:
        services = _input_panel_services(
            Mock(),
            OverlayBackend.WAYLAND_LAYER_SHELL,
            lock_lifecycle=False,
        )

        self.assertIsNone(services)
