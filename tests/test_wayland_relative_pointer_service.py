from __future__ import annotations

import ctypes
import sys
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

from axidev_osk.runtime.events import PointerMotionObserved

if sys.platform.startswith("linux"):
    import axidev_osk.services.wayland_relative_pointer as relative_pointer
    from axidev_osk.platform.overlay import OverlayBackend
    from axidev_osk.services.wayland_relative_pointer import WaylandRelativePointerService


@unittest.skipUnless(sys.platform.startswith("linux"), "Wayland client integration is Linux-only")
class WaylandRelativePointerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WaylandRelativePointerService()
        self.context = Mock()

    def _activate_drag(self) -> None:
        self.service._context = self.context
        self.service.begin_drag()

    def _make_wayland_library(self) -> Mock:
        library = Mock()
        library.wl_proxy_get_version.return_value = 1
        library.wl_proxy_add_listener.return_value = 0
        library.wl_display_roundtrip.return_value = 0
        library.wl_display_flush.return_value = 0

        def marshal(proxy: ctypes.c_void_p, opcode: ctypes.c_uint32, *_args: object) -> int:
            return {
                (11, 1): 21,
                (21, 0): 31,
                (31, 1): 41,
            }.get((proxy.value, opcode.value), 1)

        library.wl_proxy_marshal_flags.side_effect = marshal
        return library

    def _native_environment(self, library: Mock) -> ExitStack:
        native = Mock()
        native.display.return_value = 11
        native.pointer.return_value = 12
        app = Mock()
        app.nativeInterface.return_value = native
        qgui_application = Mock()
        qgui_application.instance.return_value = app

        stack = ExitStack()
        stack.enter_context(patch.object(relative_pointer, "_wayland", library))
        stack.enter_context(
            patch.object(
                relative_pointer,
                "read_selected_overlay_backend",
                return_value=OverlayBackend.WAYLAND_LAYER_SHELL,
            )
        )
        stack.enter_context(patch.object(relative_pointer, "QGuiApplication", qgui_application))
        stack.enter_context(
            patch.object(
                relative_pointer._WlInterface,
                "in_dll",
                return_value=relative_pointer._WlInterface(),
            )
        )
        return stack

    def _cleanup_operations(self, library: Mock) -> list[tuple[str, int]]:
        operations: list[tuple[str, int]] = []
        for native_call in library.mock_calls:
            if native_call[0] == "wl_proxy_marshal_flags":
                if native_call.args[-1].value == relative_pointer._DESTROY:
                    operations.append(("protocol", native_call.args[0].value))
            elif native_call[0] == "wl_proxy_destroy":
                operations.append(("registry", native_call.args[0]))
        return operations

    def test_first_drag_motion_dispatches_accelerated_delta(self) -> None:
        self._activate_drag()

        self.service._on_motion(0, 0, 0, 1_000, 384, -640, 0, 0)

        self.context.dispatcher.dispatch_event.assert_called_once_with(
            PointerMotionObserved(dx=1.5, dy=-2.5)
        )

    def test_motion_outside_drag_is_ignored(self) -> None:
        self.service._context = self.context

        self.service._on_motion(0, 0, 0, 1_000, 384, -640, 0, 0)

        self.context.dispatcher.dispatch_event.assert_not_called()

    def test_close_motions_are_aggregated_until_timer_runs(self) -> None:
        callbacks: list[object] = []
        self._activate_drag()
        self.service._on_motion(0, 0, 0, 1_000, 256, 0, 0, 0)

        with patch(
            "axidev_osk.services.wayland_relative_pointer.QTimer.singleShot",
            side_effect=lambda _delay, callback: callbacks.append(callback),
        ) as single_shot:
            self.service._on_motion(0, 0, 0, 2_000, 256, 128, 0, 0)
            self.service._on_motion(0, 0, 0, 3_000, 256, 128, 0, 0)

        single_shot.assert_called_once()
        callbacks[0]()
        self.assertEqual(
            self.context.dispatcher.dispatch_event.call_args_list[-1].args[0],
            PointerMotionObserved(dx=2.0, dy=1.0),
        )

    def test_motion_timestamp_flushes_aggregated_delta(self) -> None:
        self._activate_drag()
        self.service._on_motion(0, 0, 0, 1_000, 256, 0, 0, 0)

        with patch("axidev_osk.services.wayland_relative_pointer.QTimer.singleShot"):
            self.service._on_motion(0, 0, 0, 2_000, 256, 0, 0, 0)
            self.service._on_motion(0, 0, 0, 5_000, 512, 0, 0, 0)

        self.assertEqual(
            self.context.dispatcher.dispatch_event.call_args_list[-1].args[0],
            PointerMotionObserved(dx=3.0, dy=0.0),
        )

    def test_drag_end_invalidates_scheduled_motion(self) -> None:
        callbacks: list[object] = []
        self._activate_drag()
        self.service._last_motion_time_us = 1_000
        with patch(
            "axidev_osk.services.wayland_relative_pointer.QTimer.singleShot",
            side_effect=lambda _delay, callback: callbacks.append(callback),
        ):
            self.service._on_motion(0, 0, 0, 2_000, 256, 128, 0, 0)

        self.service.end_drag()
        callbacks[0]()

        self.context.dispatcher.dispatch_event.assert_not_called()

    def test_new_drag_discards_motion_buffered_by_previous_drag(self) -> None:
        callbacks: list[object] = []
        self._activate_drag()
        self.service._last_motion_time_us = 1_000
        with patch(
            "axidev_osk.services.wayland_relative_pointer.QTimer.singleShot",
            side_effect=lambda _delay, callback: callbacks.append(callback),
        ):
            self.service._on_motion(0, 0, 0, 2_000, 256, 128, 0, 0)

        self.service.begin_drag()
        callbacks[0]()
        self.service._on_motion(0, 0, 0, 3_000, 512, 0, 0, 0)

        self.context.dispatcher.dispatch_event.assert_called_once_with(
            PointerMotionObserved(dx=2.0, dy=0.0)
        )

    def test_commit_uses_current_surface_without_retaining_it(self) -> None:
        library = self._make_wayland_library()
        self._activate_drag()
        self.service._display = 11

        with patch.object(relative_pointer, "_wayland", library):
            self.service.commit_surface(123)

        commit_call = library.wl_proxy_marshal_flags.call_args
        self.assertEqual(commit_call.args[0].value, 123)
        self.assertEqual(commit_call.args[1].value, 6)
        library.wl_display_flush.assert_called_once()
        self.assertFalse(hasattr(self.service, "_drag_surface"))

    def test_start_binds_protocol_and_stop_releases_owned_objects(self) -> None:
        library = self._make_wayland_library()

        def roundtrip(_display: object) -> int:
            self.service._on_global(0, 21, 7, b"zwp_relative_pointer_manager_v1", 1)
            return 0

        library.wl_display_roundtrip.side_effect = roundtrip
        with self._native_environment(library):
            self.service.start(self.context)
            self.assertIs(self.service._context, self.context)
            self.assertEqual(self.service._relative_pointer, 41)
            self.service.stop()

        self.assertEqual(
            self._cleanup_operations(library),
            [("protocol", 41), ("protocol", 31), ("registry", 21)],
        )

    def test_start_without_protocol_cleans_registry_and_stays_disabled(self) -> None:
        library = self._make_wayland_library()

        with self._native_environment(library):
            self.service.start(self.context)
            marshal_count = library.wl_proxy_marshal_flags.call_count
            self.service.begin_drag()
            self.service.commit_surface(123)

        self.assertIsNone(self.service._context)
        self.assertIsNone(self.service._registry)
        self.assertEqual(library.wl_proxy_marshal_flags.call_count, marshal_count)
        self.assertEqual(self._cleanup_operations(library), [("registry", 21)])

    def test_registry_listener_failure_cleans_registry(self) -> None:
        library = self._make_wayland_library()
        library.wl_proxy_add_listener.return_value = -1

        with self._native_environment(library), self.assertRaisesRegex(
            RuntimeError, "registry listener registration failed"
        ):
            self.service.start(self.context)

        self.assertIsNone(self.service._registry)
        self.assertEqual(self._cleanup_operations(library), [("registry", 21)])

    def test_registry_roundtrip_failure_cleans_registry(self) -> None:
        library = self._make_wayland_library()
        library.wl_display_roundtrip.return_value = -1

        with self._native_environment(library), self.assertRaisesRegex(
            RuntimeError, "registry roundtrip failed"
        ):
            self.service.start(self.context)

        self.assertIsNone(self.service._registry)
        self.assertEqual(self._cleanup_operations(library), [("registry", 21)])

    def test_failed_roundtrip_cleans_manager_acquired_by_callback(self) -> None:
        library = self._make_wayland_library()

        def roundtrip(_display: object) -> int:
            self.service._on_global(0, 21, 7, b"zwp_relative_pointer_manager_v1", 1)
            return -1

        library.wl_display_roundtrip.side_effect = roundtrip
        with self._native_environment(library), self.assertRaisesRegex(
            RuntimeError, "registry roundtrip failed"
        ):
            self.service.start(self.context)

        self.assertEqual(
            self._cleanup_operations(library),
            [("protocol", 31), ("registry", 21)],
        )

    def test_relative_pointer_creation_failure_cleans_manager_and_registry(self) -> None:
        library = self._make_wayland_library()

        def roundtrip(_display: object) -> int:
            self.service._on_global(0, 21, 7, b"zwp_relative_pointer_manager_v1", 1)
            return 0

        def marshal(proxy: ctypes.c_void_p, opcode: ctypes.c_uint32, *_args: object) -> int:
            return {(11, 1): 21, (21, 0): 31, (31, 1): 0}.get((proxy.value, opcode.value), 1)

        library.wl_display_roundtrip.side_effect = roundtrip
        library.wl_proxy_marshal_flags.side_effect = marshal
        with self._native_environment(library), self.assertRaisesRegex(
            RuntimeError, "relative pointer creation failed"
        ):
            self.service.start(self.context)

        self.assertIsNone(self.service._manager)
        self.assertIsNone(self.service._registry)
        self.assertEqual(
            self._cleanup_operations(library),
            [("protocol", 31), ("registry", 21)],
        )

    def test_relative_pointer_listener_failure_cleans_all_protocol_objects(self) -> None:
        library = self._make_wayland_library()

        def roundtrip(_display: object) -> int:
            self.service._on_global(0, 21, 7, b"zwp_relative_pointer_manager_v1", 1)
            return 0

        library.wl_display_roundtrip.side_effect = roundtrip
        library.wl_proxy_add_listener.side_effect = [0, -1]
        with self._native_environment(library), self.assertRaisesRegex(
            RuntimeError, "relative-pointer listener registration failed"
        ):
            self.service.start(self.context)

        self.assertIsNone(self.service._relative_pointer)
        self.assertIsNone(self.service._manager)
        self.assertIsNone(self.service._registry)
        self.assertEqual(
            self._cleanup_operations(library),
            [("protocol", 41), ("protocol", 31), ("registry", 21)],
        )


if __name__ == "__main__":
    unittest.main()
