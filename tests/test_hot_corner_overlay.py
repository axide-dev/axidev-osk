from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtCore import QMargins, QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QWidget

from axidev_osk.application.hot_corner import HotCornerConfig, HotCornerWindowToggleController, ScreenCorner
from axidev_osk.application import layer_shell
from axidev_osk.application.layer_shell import ANCHOR_LEFT, ANCHOR_TOP
from axidev_osk.application.overlay_window import (
    AlwaysOnTopWindowConfig,
    AlwaysOnTopWindowController,
    OverlayBackend,
)


class FakeWindow:
    def __init__(self) -> None:
        self.attributes: list[tuple[Qt.WidgetAttribute, bool]] = []
        self.flags: list[tuple[Qt.WindowType, bool]] = []
        self.focus_policies: list[Qt.FocusPolicy] = []
        self.moves: list[tuple[int, int]] = []
        self._visible = False
        self._x = 0
        self._y = 0
        self._width = 100
        self._height = 60

    def setFocusPolicy(self, policy: Qt.FocusPolicy) -> None:
        self.focus_policies.append(policy)

    def setAttribute(self, attribute: Qt.WidgetAttribute, enabled: bool = True) -> None:
        self.attributes.append((attribute, enabled))

    def setWindowFlag(self, flag: Qt.WindowType, enabled: bool = True) -> None:
        self.flags.append((flag, enabled))

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

    def isVisible(self) -> bool:
        return self._visible

    def winId(self) -> int:
        return 1


class FakeOverlayController:
    def __init__(self, backend: OverlayBackend = OverlayBackend.X11_UTILITY) -> None:
        self.moves: list[tuple[QPoint, QRect]] = []
        self.handle_show_calls = 0
        self.backend = backend

    def move_to(self, position: QPoint, *, screen_geometry: QRect | None = None) -> None:
        geometry = QRect(screen_geometry) if screen_geometry is not None else QRect()
        self.moves.append((QPoint(position), geometry))

    def handle_show(self) -> bool:
        self.handle_show_calls += 1
        return True


class FakeScreen:
    def __init__(self, geometry: QRect) -> None:
        self._geometry = QRect(geometry)

    def geometry(self) -> QRect:
        return QRect(self._geometry)


class OverlayWindowControllerTests(unittest.TestCase):
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
            "axidev_osk.application.overlay_window.apply_wayland_layer_shell",
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


class HotCornerControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_show_indicator_uses_overlay_controller_for_manual_position(self) -> None:
        overlay = FakeOverlayController()
        with patch(
            "axidev_osk.application.hot_corner.configure_always_on_top_window",
            return_value=overlay,
        ):
            controller = HotCornerWindowToggleController(self.app, config=HotCornerConfig())

        try:
            screen = FakeScreen(QRect(100, 200, 800, 600))
            with patch.object(
                controller._indicator,
                "show",
                wraps=controller._indicator.show,
            ) as show_indicator, patch(
                "axidev_osk.application.hot_corner.QGuiApplication.screenAt",
                return_value=screen,
            ):
                controller._show_indicator(ScreenCorner.TOP_RIGHT, QPoint(899, 200), 0.5)

            self.assertEqual(len(overlay.moves), 1)
            position, geometry = overlay.moves[0]
            self.assertEqual(position, QPoint(834, 214))
            self.assertEqual(geometry, QRect(100, 200, 800, 600))
            self.assertEqual(overlay.handle_show_calls, 1)
            show_indicator.assert_called_once()
        finally:
            controller.stop()
            controller._indicator.close()

    def test_visible_top_level_windows_excludes_indicator(self) -> None:
        overlay = FakeOverlayController()
        with patch(
            "axidev_osk.application.hot_corner.configure_always_on_top_window",
            return_value=overlay,
        ):
            controller = HotCornerWindowToggleController(self.app, config=HotCornerConfig())

        window = QWidget()
        window.show()
        controller._indicator.show()
        self.app.processEvents()

        try:
            visible_windows = controller._visible_top_level_windows()
            self.assertIn(window, visible_windows)
            self.assertNotIn(controller._indicator, visible_windows)
        finally:
            window.close()
            controller.stop()
            controller._indicator.close()
            self.app.processEvents()

    def test_sensor_position_uses_corner_size(self) -> None:
        overlay = FakeOverlayController()
        with patch(
            "axidev_osk.application.hot_corner.configure_always_on_top_window",
            return_value=overlay,
        ):
            controller = HotCornerWindowToggleController(
                self.app,
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


if __name__ == "__main__":
    unittest.main()
