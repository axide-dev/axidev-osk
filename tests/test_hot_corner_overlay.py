from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from PySide6.QtCore import QMargins, QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication

from axidev_osk.hot_corner.controller import (
    _configure_hot_corner_window,
    HotCornerConfig,
    HotCornerWindowToggleController,
    ScreenCorner,
)
from axidev_osk.runtime.dispatcher import Dispatcher
from axidev_osk.windows.overlay import layer_shell
from axidev_osk.windows.overlay.layer_shell import ANCHOR_LEFT, ANCHOR_TOP
from axidev_osk.windows.overlay.always_on_top import (
    AlwaysOnTopWindowConfig,
    AlwaysOnTopWindowController,
    OverlayBackend,
    prepare_always_on_top_window_environment,
)


class FakeWindow:
    def __init__(self) -> None:
        self.attributes: list[tuple[Qt.WidgetAttribute, bool]] = []
        self.flags: list[tuple[Qt.WindowType, bool]] = []
        self.focus_policies: list[Qt.FocusPolicy] = []
        self.moves: list[tuple[int, int]] = []
        self.opacity_changes: list[float] = []
        self._visible = False
        self._x = 0
        self._y = 0
        self._width = 100
        self._height = 60
        self._opacity = 1.0
        self._window_flags = Qt.WindowType.Widget
        self._attributes_enabled: set[Qt.WidgetAttribute] = set()
        self.lifecycle: list[str] = []

    def setFocusPolicy(self, policy: Qt.FocusPolicy) -> None:
        self.focus_policies.append(policy)

    def setAttribute(self, attribute: Qt.WidgetAttribute, enabled: bool = True) -> None:
        self.attributes.append((attribute, enabled))
        if enabled:
            self._attributes_enabled.add(attribute)
            return
        self._attributes_enabled.discard(attribute)

    def setWindowFlag(self, flag: Qt.WindowType, enabled: bool = True) -> None:
        self.lifecycle.append(f"flag:{flag.name}")
        self.flags.append((flag, enabled))
        if enabled:
            self._window_flags |= flag
            return
        self._window_flags &= ~flag

    def windowFlags(self) -> Qt.WindowType:
        return self._window_flags

    def move(self, *args: object) -> None:
        if len(args) == 1 and isinstance(args[0], QPoint):
            x = args[0].x()
            y = args[0].y()
        else:
            x = int(args[0])
            y = int(args[1])
        self._x = x
        self._y = y
        self.moves.append((x, y))

    def resize(self, width: int, height: int) -> None:
        self._width = width
        self._height = height

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height

    def geometry(self) -> QRect:
        return QRect(self._x, self._y, self._width, self._height)

    def minimumWidth(self) -> int:
        return 0

    def minimumHeight(self) -> int:
        return 0

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y

    def screen(self) -> None:
        return None

    def show(self) -> None:
        self._visible = True

    def hide(self) -> None:
        self._visible = False

    def isVisible(self) -> bool:
        return self._visible

    def setWindowOpacity(self, opacity: float) -> None:
        self._opacity = opacity
        self.opacity_changes.append(opacity)

    def windowOpacity(self) -> float:
        return self._opacity

    def testAttribute(self, attribute: Qt.WidgetAttribute) -> bool:
        return attribute in self._attributes_enabled

    def winId(self) -> int:
        self.lifecycle.append("win-id")
        return 1


class FakeOverlayController:
    def __init__(self, backend: OverlayBackend = OverlayBackend.X11_UTILITY) -> None:
        self.moves: list[tuple[QPoint, QRect]] = []
        self.anchored_moves: list[tuple[QPoint, int, QRect]] = []
        self.prepare_show_calls = 0
        self.handle_show_calls = 0
        self.backend = backend

    def move_to(self, position: QPoint, *, screen_geometry: QRect | None = None) -> None:
        geometry = QRect(screen_geometry) if screen_geometry is not None else QRect()
        self.moves.append((QPoint(position), geometry))

    def move_to_anchored(self, position: QPoint, *, anchors: int, screen_geometry: QRect | None = None) -> None:
        geometry = QRect(screen_geometry) if screen_geometry is not None else QRect()
        self.anchored_moves.append((QPoint(position), anchors, geometry))
        self.move_to(position, screen_geometry=screen_geometry)

    def prepare_show(self) -> bool:
        self.prepare_show_calls += 1
        return True

    def handle_show(self) -> bool:
        self.handle_show_calls += 1
        return True


class FakeScreen:
    def __init__(self, geometry: QRect, name: str = "Virtual-1") -> None:
        self._geometry = QRect(geometry)
        self._name = name

    def geometry(self) -> QRect:
        return QRect(self._geometry)

    def name(self) -> str:
        return self._name


class OverlayWindowControllerTests(unittest.TestCase):
    def test_configure_window_disables_system_background_erase(self) -> None:
        window = FakeWindow()
        with patch.object(
            AlwaysOnTopWindowController,
            "_detect_backend",
            return_value=OverlayBackend.WINDOWS_NATIVE,
        ):
            controller = AlwaysOnTopWindowController(window)

        controller.configure_window()

        self.assertIn((Qt.WidgetAttribute.WA_NoSystemBackground, True), window.attributes)

    def test_x11_manual_move_keeps_indicator_position(self) -> None:
        window = FakeWindow()
        with patch.object(
            AlwaysOnTopWindowController,
            "_detect_backend",
            return_value=OverlayBackend.X11_UTILITY,
        ):
            controller = AlwaysOnTopWindowController(
                window,
                config=AlwaysOnTopWindowConfig(manage_position=False),
            )

        controller.configure_window()
        controller.move_to(QPoint(42, 84))
        controller.handle_show()

        self.assertEqual(window.moves[-1], (42, 84))
        self.assertIn((Qt.WidgetAttribute.WA_X11DoNotAcceptFocus, True), window.attributes)

    def test_wayland_layer_shell_manual_move_persists_across_show(self) -> None:
        window = FakeWindow()
        calls: list[tuple[int, QMargins]] = []

        def record_apply_wayland_layer_shell(*args: object, **kwargs: object) -> bool:
            del args
            calls.append((int(kwargs["anchors"]), kwargs["margins"]))
            return True

        with patch.object(
            AlwaysOnTopWindowController,
            "_detect_backend",
            return_value=OverlayBackend.WAYLAND_LAYER_SHELL,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.apply_wayland_layer_shell",
            side_effect=record_apply_wayland_layer_shell,
        ):
            controller = AlwaysOnTopWindowController(
                window,
                config=AlwaysOnTopWindowConfig(manage_position=False),
            )
            controller.move_to(QPoint(110, 220), screen_geometry=QRect(100, 200, 800, 600))
            controller.handle_show()

        self.assertGreaterEqual(len(calls), 2)
        anchors, margins = calls[-1]
        self.assertEqual(anchors, ANCHOR_LEFT | ANCHOR_TOP)
        self.assertEqual(margins, QMargins(10, 20, 0, 0))

    def test_wayland_layer_shell_move_to_allows_negative_margins(self) -> None:
        window = FakeWindow()
        calls: list[tuple[int, QMargins]] = []

        def record_apply_wayland_layer_shell(*args: object, **kwargs: object) -> bool:
            del args
            calls.append((int(kwargs["anchors"]), kwargs["margins"]))
            return True

        with patch.object(
            AlwaysOnTopWindowController,
            "_detect_backend",
            return_value=OverlayBackend.WAYLAND_LAYER_SHELL,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.apply_wayland_layer_shell",
            side_effect=record_apply_wayland_layer_shell,
        ):
            controller = AlwaysOnTopWindowController(
                window,
                config=AlwaysOnTopWindowConfig(manage_position=False),
            )
            controller.move_to(QPoint(90, 180), screen_geometry=QRect(100, 200, 800, 600))

        self.assertGreaterEqual(len(calls), 1)
        anchors, margins = calls[-1]
        self.assertEqual(anchors, ANCHOR_LEFT | ANCHOR_TOP)
        self.assertEqual(margins, QMargins(-10, -20, 0, 0))

    def test_wayland_layer_shell_move_by_preserves_negative_margins(self) -> None:
        window = FakeWindow()
        calls: list[tuple[int, QMargins]] = []

        def record_apply_wayland_layer_shell(*args: object, **kwargs: object) -> bool:
            del args
            calls.append((int(kwargs["anchors"]), kwargs["margins"]))
            return True

        with patch.object(
            AlwaysOnTopWindowController,
            "_detect_backend",
            return_value=OverlayBackend.WAYLAND_LAYER_SHELL,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.apply_wayland_layer_shell",
            side_effect=record_apply_wayland_layer_shell,
        ):
            controller = AlwaysOnTopWindowController(
                window,
                config=AlwaysOnTopWindowConfig(manage_position=False),
            )
            controller.move_to(QPoint(100, 200), screen_geometry=QRect(100, 200, 800, 600))
            controller.move_by(-25, 30)

        self.assertGreaterEqual(len(calls), 2)
        anchors, margins = calls[-1]
        self.assertEqual(anchors, layer_shell.ANCHOR_LEFT | layer_shell.ANCHOR_BOTTOM)
        self.assertEqual(margins, QMargins(-25, 0, 0, -30))

    def test_wayland_layer_shell_uses_full_screen_geometry_for_initial_position(self) -> None:
        window = FakeWindow()
        window.resize(100, 60)

        calls: list[tuple[int, QMargins]] = []

        def record_apply_wayland_layer_shell(*args: object, **kwargs: object) -> bool:
            del args
            calls.append((int(kwargs["anchors"]), kwargs["margins"]))
            return True

        with patch.object(
            AlwaysOnTopWindowController,
            "_detect_backend",
            return_value=OverlayBackend.WAYLAND_LAYER_SHELL,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.AlwaysOnTopWindowController._current_screen_geometry",
            return_value=QRect(0, 0, 1920, 1080),
        ) as current_screen_geometry, patch(
            "axidev_osk.windows.overlay.always_on_top.apply_wayland_layer_shell",
            side_effect=record_apply_wayland_layer_shell,
        ):
            controller = AlwaysOnTopWindowController(window)
            controller.handle_show()

        self.assertTrue(any(call.kwargs.get("for_layer_shell") is True for call in current_screen_geometry.call_args_list))
        anchors, margins = calls[-1]
        self.assertEqual(anchors, layer_shell.ANCHOR_LEFT | layer_shell.ANCHOR_BOTTOM)
        self.assertEqual(margins, QMargins(1804, 0, 0, 1004))

    def test_wayland_layer_shell_show_refreshes_visible_surface_once(self) -> None:
        window = FakeWindow()
        window.show()

        with patch.object(
            AlwaysOnTopWindowController,
            "_detect_backend",
            return_value=OverlayBackend.WAYLAND_LAYER_SHELL,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.apply_wayland_layer_shell",
            return_value=True,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.QTimer.singleShot",
            side_effect=lambda _delay, callback: callback(),
        ) as single_shot:
            controller = AlwaysOnTopWindowController(window)
            controller.handle_show()
            controller.handle_show()

        single_shot.assert_called_once()
        self.assertTrue(window.isVisible())

    def test_wayland_layer_shell_move_by_initializes_position_before_delta(self) -> None:
        window = FakeWindow()
        window.resize(100, 60)

        calls: list[tuple[int, QMargins]] = []

        def record_apply_wayland_layer_shell(*args: object, **kwargs: object) -> bool:
            del args
            calls.append((int(kwargs["anchors"]), kwargs["margins"]))
            return True

        with patch.object(
            AlwaysOnTopWindowController,
            "_detect_backend",
            return_value=OverlayBackend.WAYLAND_LAYER_SHELL,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.AlwaysOnTopWindowController._current_screen_geometry",
            return_value=QRect(0, 0, 1920, 1080),
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.apply_wayland_layer_shell",
            side_effect=record_apply_wayland_layer_shell,
        ):
            controller = AlwaysOnTopWindowController(window)
            controller.move_by(10, 20)

        anchors, margins = calls[-1]
        self.assertEqual(anchors, layer_shell.ANCHOR_LEFT | layer_shell.ANCHOR_BOTTOM)
        self.assertEqual(margins, QMargins(1814, 0, 0, 984))

    def test_windows_native_overlay_keeps_native_chrome(self) -> None:
        window = FakeWindow()

        with patch.object(
            AlwaysOnTopWindowController,
            "_detect_backend",
            return_value=OverlayBackend.WINDOWS_NATIVE,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top._set_windows_taskbar_style",
        ) as set_taskbar_style:
            controller = AlwaysOnTopWindowController(window)
            controller.configure_window()

        self.assertFalse(controller.uses_custom_chrome)
        self.assertIn((Qt.WindowType.WindowStaysOnTopHint, True), window.flags)
        self.assertIn((Qt.WindowType.WindowDoesNotAcceptFocus, True), window.flags)
        self.assertIn((Qt.WidgetAttribute.WA_ShowWithoutActivating, True), window.attributes)
        self.assertNotIn((Qt.WindowType.FramelessWindowHint, True), window.flags)
        set_taskbar_style.assert_called_once_with(1)

    def test_windows_native_overlay_resets_chrome_inactive_after_show(self) -> None:
        window = FakeWindow()
        window.show()

        with patch.object(
            AlwaysOnTopWindowController,
            "_detect_backend",
            return_value=OverlayBackend.WINDOWS_NATIVE,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.QTimer.singleShot",
            side_effect=lambda _delay, callback: callback(),
        ), patch(
            "axidev_osk.windows.overlay.always_on_top._set_windows_native_chrome_inactive",
        ) as set_chrome_inactive:
            controller = AlwaysOnTopWindowController(
                window,
                config=AlwaysOnTopWindowConfig(manage_position=False),
            )
            controller.handle_show()

        set_chrome_inactive.assert_called_once_with(1)


class LayerShellPluginDiscoveryTests(unittest.TestCase):
    def test_find_qt_platform_plugin_root_detects_pyinstaller_bundle_plugins(self) -> None:
        with TemporaryDirectory() as temp_dir:
            bundle_root = Path(temp_dir)
            plugin_root = bundle_root / "_internal" / "PySide6" / "Qt" / "plugins"
            platform_dir = plugin_root / "platforms"
            platform_dir.mkdir(parents=True)
            (platform_dir / "libqxcb.so").write_bytes(b"")

            with patch.object(layer_shell.QLibraryInfo, "path", return_value=""), patch.dict(
                "os.environ",
                {},
                clear=True,
            ), patch.object(
                layer_shell,
                "_COMMON_QT_PLUGIN_ROOTS",
                (),
            ), patch.object(
                layer_shell.sys,
                "executable",
                str(bundle_root / "axidev-osk"),
            ):
                self.assertEqual(layer_shell.find_qt_platform_plugin_root(), plugin_root)


class OverlayBackendSelectionTests(unittest.TestCase):
    def test_kwin_input_method_connection_selects_input_panel(self) -> None:
        with patch(
            "axidev_osk.windows.overlay.always_on_top.sys.platform",
            "linux",
        ), patch.dict(
            "os.environ",
            {"WAYLAND_SOCKET": "12"},
            clear=True,
        ):
            backend = prepare_always_on_top_window_environment()
            selected_backend = os.environ["AXIDEV_OSK_OVERLAY_BACKEND"]
            qt_platform = os.environ["QT_QPA_PLATFORM"]
            bypass_hint = os.environ["QT_WAYLAND_USE_BYPASSWINDOWMANAGERHINT"]

        self.assertEqual(backend, OverlayBackend.WAYLAND_INPUT_PANEL)
        self.assertEqual(selected_backend, "wayland-input-panel")
        self.assertEqual(qt_platform, "wayland")
        self.assertEqual(bypass_hint, "1")

    def test_input_panel_controller_assigns_role_before_show(self) -> None:
        window = FakeWindow()
        window.screen = lambda: FakeScreen(QRect(0, 0, 1920, 1080))
        attachment = Mock()
        with patch.object(
            AlwaysOnTopWindowController,
            "_detect_backend",
            return_value=OverlayBackend.WAYLAND_INPUT_PANEL,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.attach_kwin_input_panel",
            side_effect=lambda *_args, **_kwargs: (
                window.lifecycle.append("attach") or attachment
            ),
        ) as attach_input_panel:
            controller = AlwaysOnTopWindowController(window)
            controller.configure_window()

        self.assertIn((Qt.WindowType.BypassWindowManagerHint, True), window.flags)
        attach_input_panel.assert_called_once_with(1, output_name="Virtual-1")
        self.assertLess(
            window.lifecycle.index("flag:FramelessWindowHint"),
            window.lifecycle.index("win-id"),
        )
        self.assertLess(window.lifecycle.index("win-id"), window.lifecycle.index("attach"))
        controller.release_resources()
        attachment.close.assert_called_once_with()

    def test_wayland_without_layer_shell_falls_back_to_x11_bridge_with_warning(self) -> None:
        with patch(
            "axidev_osk.windows.overlay.always_on_top.sys.platform",
            "linux",
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.is_wayland_session",
            return_value=True,
        ), patch.dict(
            "os.environ",
            {},
            clear=True,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.configure_wayland_layer_shell_environment",
            return_value=False,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top._configure_x11_bridge_environment",
            return_value=True,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top._warn_wayland_fallback",
        ) as warn_wayland_fallback:
            backend = prepare_always_on_top_window_environment()

        self.assertEqual(backend, OverlayBackend.X11_UTILITY_BRIDGE)
        warn_wayland_fallback.assert_called_once()

    def test_wayland_without_layer_shell_raises_if_x11_bridge_unavailable(self) -> None:
        with patch(
            "axidev_osk.windows.overlay.always_on_top.sys.platform",
            "linux",
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.is_wayland_session",
            return_value=True,
        ), patch.dict(
            "os.environ",
            {},
            clear=True,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.configure_wayland_layer_shell_environment",
            return_value=False,
        ):
            with patch(
                "axidev_osk.windows.overlay.always_on_top._configure_x11_bridge_environment",
                return_value=False,
            ):
                with self.assertRaisesRegex(RuntimeError, "X11/XWayland fallback backend could not be enabled"):
                    prepare_always_on_top_window_environment()

    def test_wayland_platform_with_xcb_fallback_uses_layer_shell(self) -> None:
        with patch(
            "axidev_osk.windows.overlay.always_on_top.sys.platform",
            "linux",
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.is_wayland_session",
            return_value=True,
        ), patch.dict(
            "os.environ",
            {"QT_QPA_PLATFORM": "wayland;xcb"},
            clear=True,
        ), patch(
            "axidev_osk.windows.overlay.always_on_top.configure_wayland_layer_shell_environment",
            return_value=True,
        ):
            backend = prepare_always_on_top_window_environment()
            selected_backend = os.environ["AXIDEV_OSK_OVERLAY_BACKEND"]

        self.assertEqual(backend, OverlayBackend.WAYLAND_LAYER_SHELL)
        self.assertEqual(selected_backend, "wayland-layer-shell")

    def test_wayland_controller_accepts_x11_bridge_backend(self) -> None:
        window = FakeWindow()

        with patch.object(
            AlwaysOnTopWindowController,
            "_detect_backend",
            return_value=OverlayBackend.X11_UTILITY_BRIDGE,
        ):
            controller = AlwaysOnTopWindowController(window)

        self.assertEqual(controller.backend, OverlayBackend.X11_UTILITY_BRIDGE)

    def test_wayland_controller_rejects_non_layer_shell_backend(self) -> None:
        window = FakeWindow()

        with patch.object(
            AlwaysOnTopWindowController,
            "_detect_backend",
            side_effect=RuntimeError("Wayland overlay backend was initialized without layer-shell support."),
        ):
            with self.assertRaisesRegex(RuntimeError, "without layer-shell support"):
                AlwaysOnTopWindowController(window)


class HotCornerControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.closeAllWindows()
        cls.app.processEvents()
        cls.app.quit()
        cls.app.processEvents()

    def setUp(self) -> None:
        self.dispatcher = Dispatcher()

    def test_show_indicator_uses_overlay_controller_for_manual_position(self) -> None:
        overlay = FakeOverlayController()
        with patch(
            "axidev_osk.hot_corner.controller.configure_hot_corner_overlay",
            return_value=overlay,
        ):
            controller = HotCornerWindowToggleController(self.dispatcher, config=HotCornerConfig())

        try:
            screen = FakeScreen(QRect(100, 200, 800, 600))
            move_count = len(overlay.moves)
            with patch.object(
                controller._indicator,
                "show",
                wraps=controller._indicator.show,
            ) as show_indicator, patch(
                "axidev_osk.hot_corner.controller.QGuiApplication.screenAt",
                return_value=screen,
            ):
                controller._show_indicator(ScreenCorner.TOP_RIGHT, QPoint(899, 200), 0.5)

            self.assertEqual(len(overlay.moves), move_count + 1)
            position, geometry = overlay.moves[-1]
            self.assertEqual(position, QPoint(834, 214))
            self.assertEqual(geometry, QRect(100, 200, 800, 600))
            self.assertEqual(overlay.prepare_show_calls, 0)
            self.assertEqual(overlay.handle_show_calls, 1)
            show_indicator.assert_called_once()
        finally:
            controller.stop()
            controller._indicator.close()

    def test_sensor_position_uses_corner_size(self) -> None:
        overlay = FakeOverlayController()
        with patch(
            "axidev_osk.hot_corner.controller.configure_hot_corner_overlay",
            return_value=overlay,
        ):
            controller = HotCornerWindowToggleController(
                self.dispatcher,
                config=HotCornerConfig(corner_size_px=24),
            )

        try:
            geometry = QRect(100, 200, 800, 600)
            self.assertEqual(
                controller._sensor_position(geometry, ScreenCorner.TOP_RIGHT),
                QPoint(876, 200),
            )
            self.assertEqual(
                controller._sensor_position(geometry, ScreenCorner.BOTTOM_LEFT),
                QPoint(100, 776),
            )
        finally:
            controller.stop()
            controller._indicator.close()

    def test_x11_hot_corners_use_cursor_polling_without_sensor_windows(self) -> None:
        overlay = FakeOverlayController(backend=OverlayBackend.X11_UTILITY)
        with patch(
            "axidev_osk.hot_corner.controller.configure_hot_corner_overlay",
            return_value=overlay,
        ):
            controller = HotCornerWindowToggleController(
                self.dispatcher,
                config=HotCornerConfig(corner_size_px=24),
            )

        try:
            self.assertFalse(controller._use_sensor_windows)
            self.assertEqual(controller._sensor_handles, [])
        finally:
            controller.stop()
            controller._indicator.close()

    def test_wayland_hot_corners_create_sensor_windows(self) -> None:
        overlay = FakeOverlayController(backend=OverlayBackend.WAYLAND_LAYER_SHELL)
        with patch(
            "axidev_osk.hot_corner.controller.configure_hot_corner_overlay",
            return_value=overlay,
        ):
            controller = HotCornerWindowToggleController(self.dispatcher, config=HotCornerConfig())

        try:
            self.assertEqual(len(controller._sensor_handles), len(self.app.screens()) * len(ScreenCorner))
            self.assertTrue(controller._use_sensor_windows)
        finally:
            controller.stop()
            controller._indicator.close()

    def test_sensor_windows_use_overlay_controller_for_positions(self) -> None:
        overlay = FakeOverlayController(backend=OverlayBackend.WAYLAND_LAYER_SHELL)
        with patch(
            "axidev_osk.hot_corner.controller.configure_hot_corner_overlay",
            return_value=overlay,
        ):
            controller = HotCornerWindowToggleController(self.dispatcher, config=HotCornerConfig())

        try:
            self.assertEqual(overlay.anchored_moves, [])
            self.assertEqual(len(overlay.moves), len(self.app.screens()) * len(ScreenCorner))
            self.assertTrue(controller._sensor_handles)
            for handle in controller._sensor_handles:
                self.assertIs(handle.overlay, overlay)
        finally:
            controller.stop()
            controller._indicator.close()

    def test_x11_bridge_hot_corners_create_sensor_windows(self) -> None:
        overlay = FakeOverlayController(backend=OverlayBackend.X11_UTILITY_BRIDGE)
        with patch(
            "axidev_osk.hot_corner.controller.configure_hot_corner_overlay",
            return_value=overlay,
        ):
            controller = HotCornerWindowToggleController(self.dispatcher, config=HotCornerConfig())

        try:
            self.assertEqual(len(controller._sensor_handles), len(self.app.screens()) * len(ScreenCorner))
        finally:
            controller.stop()
            controller._indicator.close()

    def test_sensor_window_polling_uses_active_sensor(self) -> None:
        overlay = FakeOverlayController(backend=OverlayBackend.X11_UTILITY_BRIDGE)
        with patch(
            "axidev_osk.hot_corner.controller.configure_hot_corner_overlay",
            return_value=overlay,
        ):
            controller = HotCornerWindowToggleController(self.dispatcher, config=HotCornerConfig())

        try:
            with patch.object(controller, "_poll_active_sensor") as poll_active_sensor, patch.object(
                controller,
                "_poll_cursor",
            ) as poll_cursor:
                controller._poll()

            poll_active_sensor.assert_called_once()
            poll_cursor.assert_not_called()
        finally:
            controller.stop()
            controller._indicator.close()

    def test_configure_hot_corner_window_requests_shadowless_flags(self) -> None:
        indicator_window = FakeWindow()
        sensor_window = FakeWindow()

        _configure_hot_corner_window(indicator_window, accepts_input=False)
        _configure_hot_corner_window(sensor_window, accepts_input=True)

        self.assertIn((Qt.WindowType.FramelessWindowHint, True), indicator_window.flags)
        self.assertIn((Qt.WindowType.NoDropShadowWindowHint, True), indicator_window.flags)
        self.assertIn((Qt.WindowType.WindowTransparentForInput, True), indicator_window.flags)

        self.assertIn((Qt.WindowType.FramelessWindowHint, True), sensor_window.flags)
        self.assertIn((Qt.WindowType.NoDropShadowWindowHint, True), sensor_window.flags)
        self.assertNotIn((Qt.WindowType.WindowTransparentForInput, True), sensor_window.flags)


if __name__ == "__main__":
    unittest.main()
