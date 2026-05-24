from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from axidev_osk.components import register_components
from axidev_osk.components.grid.keyboard import KeyboardWidget
from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.runtime.registries import ComponentRegistry, SurfaceRegistry
from axidev_osk.runtime.testing import make_test_context
from axidev_osk.windows.builder import build_window
from axidev_osk.windows.chrome import OverlayResizeHandle, OverlayTitleBar
from axidev_osk.windows.surface import register_surfaces
from axidev_osk.windows.overlay.always_on_top import OverlayPlacement


class FakeKeyboardBackend:
    def __init__(self, *, ready: bool) -> None:
        self.ready = ready
        self.status_text = "Keyboard output is unavailable."
        self.needs_permission_setup = False

    def initialize(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def add_key_state_listener(self, listener):
        return lambda: None

    def is_key_down(self, key_name: str) -> bool:
        return False

    def key_name_for_spec(self, spec):
        return spec.io_key or (spec.label if len(spec.label) == 1 else None)

    def key_down(self, spec, latched_keys):
        return None

    def key_up(self, press_handle) -> None:
        return None

    def sync_latched_key(self, spec, latched: bool, press_handle=None):
        return press_handle


class FakeOverlayController:
    def __init__(self, *, uses_custom_chrome: bool = True) -> None:
        self.uses_custom_chrome = uses_custom_chrome
        self.reapply_count = 0

    def prepare_show(self) -> bool:
        return True

    def move_by(self, dx: int, dy: int) -> None:
        return None

    def resize_by(self, dx: int, dy: int) -> None:
        return None

    def handle_show(self) -> bool:
        return True

    def apply_configured_position(self) -> None:
        return None

    def reapply_always_on_top(self) -> None:
        self.reapply_count += 1


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _build_keyboard_window(backend: FakeKeyboardBackend):
    config = build_default_app_config()
    components = ComponentRegistry()
    surfaces = SurfaceRegistry()
    register_components(components)
    register_surfaces(surfaces)
    context = make_test_context(
        backend,
        config=config,
        components=components,
        surfaces=surfaces,
    )
    return build_window(config.windows[0], context)


class RuntimeWindowLayoutTests(unittest.TestCase):
    """Tests covering the default keyboard window built via ``build_window``."""
    def test_custom_chrome_puts_resize_handle_in_title_bar(self) -> None:
        _app()
        overlay = FakeOverlayController()

        with (
            patch(
                "axidev_osk.windows.builder.configure_always_on_top_window",
                return_value=overlay,
            ),
        ):
            window = _build_keyboard_window(FakeKeyboardBackend(ready=True))

        self.addCleanup(window.close)

        central_layout = window.centralWidget().layout()
        self.assertEqual(central_layout.count(), 3)

        title_bar = central_layout.itemAt(0).widget()
        self.assertIsInstance(title_bar, OverlayTitleBar)

        resize_handle = title_bar.findChild(OverlayResizeHandle, "layerShellResizeHandle")
        self.assertIsNotNone(resize_handle)

        close_button = title_bar.findChild(QPushButton, "layerShellCloseButton")
        self.assertIsNotNone(close_button)
        title_bar_layout = title_bar.layout()
        self.assertLess(title_bar_layout.indexOf(resize_handle), title_bar_layout.indexOf(close_button))
        status_label = window.findChild(QLabel, "statusLabel")
        self.assertIsNotNone(status_label)
        self.assertFalse(status_label.isVisible())

    def test_status_footer_is_only_visible_when_backend_is_unavailable(self) -> None:
        _app()
        overlay = FakeOverlayController()

        with (
            patch(
                "axidev_osk.windows.builder.configure_always_on_top_window",
                return_value=overlay,
            ),
        ):
            window = _build_keyboard_window(FakeKeyboardBackend(ready=False))

        self.addCleanup(window.close)

        central_layout = window.centralWidget().layout()
        self.assertEqual(central_layout.count(), 3)
        self.assertIsNotNone(window.findChild(QPushButton, "layerShellCloseButton"))
        self.assertIsNotNone(window.findChild(QLabel, "statusLabel"))

    def test_root_surface_uses_styled_background(self) -> None:
        _app()
        overlay = FakeOverlayController()

        with (
            patch(
                "axidev_osk.windows.builder.configure_always_on_top_window",
                return_value=overlay,
            ),
        ):
            window = _build_keyboard_window(FakeKeyboardBackend(ready=True))

        self.addCleanup(window.close)

        central = window.centralWidget()
        self.assertTrue(central.testAttribute(Qt.WidgetAttribute.WA_StyledBackground))

    def test_startup_size_uses_minimum_size(self) -> None:
        _app()
        overlay = FakeOverlayController()

        with (
            patch(
                "axidev_osk.windows.builder.configure_always_on_top_window",
                return_value=overlay,
            ),
        ):
            window = _build_keyboard_window(FakeKeyboardBackend(ready=True))

        self.addCleanup(window.close)

        self.assertEqual(window.size(), window.minimumSize())
        self.assertEqual(window.minimumSize(), window.minimumSizeHint().expandedTo(window.minimumSize()))
        self.assertLessEqual(window.minimumWidth(), window.width())
        self.assertLessEqual(window.minimumHeight(), window.height())

    def test_keyboard_window_uses_center_overlay_placement(self) -> None:
        _app()
        overlay = FakeOverlayController()

        with (
            patch(
                "axidev_osk.windows.builder.configure_always_on_top_window",
                return_value=overlay,
            ) as configure_overlay,
        ):
            window = _build_keyboard_window(FakeKeyboardBackend(ready=True))

        self.addCleanup(window.close)

        config = configure_overlay.call_args.kwargs["config"]
        self.assertEqual(config.placement, OverlayPlacement.CENTER)

    def test_runtime_window_and_components_expose_dynamic_identity_properties(self) -> None:
        _app()
        overlay = FakeOverlayController()

        with (
            patch(
                "axidev_osk.windows.builder.configure_always_on_top_window",
                return_value=overlay,
            ),
        ):
            window = _build_keyboard_window(FakeKeyboardBackend(ready=True))

        self.addCleanup(window.close)

        self.assertEqual(window.property("componentType"), "window")
        self.assertEqual(window.property("componentId"), "window:keyboard")
        self.assertEqual(window.centralWidget().property("componentType"), "surface")
        self.assertEqual(window.centralWidget().property("componentId"), "surface:keyboard")

        keyboard = window.findChild(KeyboardWidget)
        self.assertIsNotNone(keyboard)
        self.assertEqual(keyboard.property("componentType"), "grid")
        self.assertEqual(keyboard.property("componentId"), "component:keyboard-grid")
        self.assertEqual(keyboard.property("layout"), "layout:us-iso")
        self.assertEqual(keyboard.property("layoutName"), "us-iso")

        key = next(
            button
            for button in window.findChildren(QPushButton)
            if button.property("ioKey") == "A"
        )
        self.assertEqual(key.property("componentType"), "key")
        self.assertIsInstance(key.property("componentId"), str)
        self.assertIsNone(key.property("keyId"))
        self.assertEqual(key.property("ioKey"), "A")
        self.assertEqual(key.property("interactionState"), "idle")
        self.assertFalse(key.property("latched"))
        self.assertFalse(key.property("pressed"))
        self.assertEqual(key.property("profile"), "default")
        self.assertEqual(key.property("layout"), "layout:us-iso")

    def test_runtime_window_reapplies_always_on_top_through_overlay_controller(self) -> None:
        _app()
        overlay = FakeOverlayController()

        with patch(
            "axidev_osk.windows.builder.configure_always_on_top_window",
            return_value=overlay,
        ):
            window = _build_keyboard_window(FakeKeyboardBackend(ready=True))

        self.addCleanup(window.close)

        self.assertTrue(window.always_on_top)
        window.reapply_always_on_top()

        self.assertEqual(overlay.reapply_count, 1)


if __name__ == "__main__":
    unittest.main()
