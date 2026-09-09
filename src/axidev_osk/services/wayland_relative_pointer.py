"""Wayland relative-pointer bridge for layer-shell window dragging."""

from __future__ import annotations

import ctypes
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication

from ..platform.overlay import OverlayBackend, read_selected_overlay_backend
from ..runtime.events import PointerMotionObserved

if TYPE_CHECKING:
    from ..runtime.context import Context

_logger = logging.getLogger(__name__)
_MANAGER_NAME = b"zwp_relative_pointer_manager_v1"
_DESTROY = 1
_DISPATCH_INTERVAL_US = 4_000


class _WlInterface(ctypes.Structure):
    pass


class _WlMessage(ctypes.Structure):
    pass


_WlMessage._fields_ = [
    ("name", ctypes.c_char_p),
    ("signature", ctypes.c_char_p),
    ("types", ctypes.POINTER(ctypes.POINTER(_WlInterface))),
]
_WlInterface._fields_ = [
    ("name", ctypes.c_char_p),
    ("version", ctypes.c_int),
    ("method_count", ctypes.c_int),
    ("methods", ctypes.POINTER(_WlMessage)),
    ("event_count", ctypes.c_int),
    ("events", ctypes.POINTER(_WlMessage)),
]

_relative_requests = (_WlMessage * 1)(_WlMessage(b"destroy", b"", None))
_relative_events = (_WlMessage * 1)(_WlMessage(b"relative_motion", b"uuffff", None))
_relative_interface = _WlInterface(
    b"zwp_relative_pointer_v1",
    1,
    len(_relative_requests),
    _relative_requests,
    len(_relative_events),
    _relative_events,
)

_wayland = ctypes.CDLL("libwayland-client.so.0")
_wl_pointer_interface = _WlInterface.in_dll(_wayland, "wl_pointer_interface")
_manager_request_types = (ctypes.POINTER(_WlInterface) * 2)(
    ctypes.pointer(_relative_interface),
    ctypes.pointer(_wl_pointer_interface),
)
_manager_requests = (_WlMessage * 2)(
    _WlMessage(b"destroy", b"", None),
    _WlMessage(b"get_relative_pointer", b"no", _manager_request_types),
)
_manager_interface = _WlInterface(_MANAGER_NAME, 1, len(_manager_requests), _manager_requests, 0, None)

_wayland.wl_proxy_get_version.argtypes = [ctypes.c_void_p]
_wayland.wl_proxy_get_version.restype = ctypes.c_uint32
_wayland.wl_proxy_add_listener.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
_wayland.wl_proxy_add_listener.restype = ctypes.c_int
_wayland.wl_proxy_destroy.argtypes = [ctypes.c_void_p]
_wayland.wl_display_roundtrip.argtypes = [ctypes.c_void_p]
_wayland.wl_display_roundtrip.restype = ctypes.c_int
_wayland.wl_display_flush.argtypes = [ctypes.c_void_p]
_wayland.wl_display_flush.restype = ctypes.c_int
_wayland.wl_proxy_marshal_flags.restype = ctypes.c_void_p

_GlobalCallback = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32
)
_GlobalRemoveCallback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32)
_MotionCallback = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.c_uint32,
    ctypes.c_int32,
    ctypes.c_int32,
    ctypes.c_int32,
    ctypes.c_int32,
)


class WaylandRelativePointerService(QObject):
    """Publish compositor-accelerated relative pointer motion."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._context: Context | None = None
        self._display: int | None = None
        self._registry: int | None = None
        self._manager: int | None = None
        self._relative_pointer: int | None = None
        self._drag_active = False
        self._pending_dx = 0.0
        self._pending_dy = 0.0
        self._last_motion_time_us: int | None = None
        self._dispatch_scheduled = False
        self._dispatch_token = 0
        self._global_callback = _GlobalCallback(self._on_global)
        self._global_remove_callback = _GlobalRemoveCallback(lambda *_args: None)
        self._motion_callback = _MotionCallback(self._on_motion)
        self._registry_listener = (ctypes.c_void_p * 2)(
            ctypes.cast(self._global_callback, ctypes.c_void_p),
            ctypes.cast(self._global_remove_callback, ctypes.c_void_p),
        )
        self._motion_listener = (ctypes.c_void_p * 1)(ctypes.cast(self._motion_callback, ctypes.c_void_p))

    def start(self, context: "Context") -> None:
        """Bind the standard relative-pointer protocol when layer-shell uses it."""

        if self._context is not None or read_selected_overlay_backend() != OverlayBackend.WAYLAND_LAYER_SHELL:
            return
        app = QGuiApplication.instance()
        native = app.nativeInterface() if app is not None else None
        display = native.display() if native is not None and hasattr(native, "display") else 0
        pointer = native.pointer() if native is not None and hasattr(native, "pointer") else 0
        if not display or not pointer:
            _logger.warning("Wayland native pointer is unavailable; layer-shell dragging is disabled")
            return

        display_version = _wayland.wl_proxy_get_version(display)
        registry_interface = _WlInterface.in_dll(_wayland, "wl_registry_interface")
        registry = _wayland.wl_proxy_marshal_flags(
            ctypes.c_void_p(display),
            ctypes.c_uint32(1),
            ctypes.byref(registry_interface),
            ctypes.c_uint32(display_version),
            ctypes.c_uint32(0),
            ctypes.c_void_p(),
        )
        if not registry:
            raise RuntimeError("Wayland registry creation failed")
        self._registry = registry
        if _wayland.wl_proxy_add_listener(registry, self._registry_listener, None) != 0:
            self.stop()
            raise RuntimeError("Wayland registry listener registration failed")
        if _wayland.wl_display_roundtrip(display) < 0:
            self.stop()
            raise RuntimeError("Wayland registry roundtrip failed")
        if self._manager is None:
            _logger.warning("Wayland relative-pointer protocol is unavailable; layer-shell dragging is disabled")
            self.stop()
            return

        relative_pointer = _wayland.wl_proxy_marshal_flags(
            ctypes.c_void_p(self._manager),
            ctypes.c_uint32(1),
            ctypes.byref(_relative_interface),
            ctypes.c_uint32(1),
            ctypes.c_uint32(0),
            ctypes.c_void_p(),
            ctypes.c_void_p(pointer),
        )
        if not relative_pointer:
            self.stop()
            raise RuntimeError("Wayland relative pointer creation failed")
        self._relative_pointer = relative_pointer
        if _wayland.wl_proxy_add_listener(relative_pointer, self._motion_listener, None) != 0:
            self.stop()
            raise RuntimeError("Wayland relative-pointer listener registration failed")
        self._context = context
        self._display = display
        _logger.info("Wayland relative-pointer bridge started")

    def stop(self) -> None:
        """Destroy protocol objects owned by the service."""

        self._context = None
        self._display = None
        self._drag_active = False
        self._reset_pending_motion()
        if self._relative_pointer is not None:
            self._destroy_protocol_object(self._relative_pointer)
            self._relative_pointer = None
        if self._manager is not None:
            self._destroy_protocol_object(self._manager)
            self._manager = None
        if self._registry is not None:
            _wayland.wl_proxy_destroy(self._registry)
            self._registry = None

    def _reset_pending_motion(self) -> None:
        self._pending_dx = 0.0
        self._pending_dy = 0.0
        self._last_motion_time_us = None
        self._dispatch_scheduled = False
        self._dispatch_token += 1

    def _on_global(
        self, _data: int, registry: int, name: int, interface: bytes, version: int
    ) -> None:
        if interface != _MANAGER_NAME or self._manager is not None:
            return
        protocol_version = min(version, 1)
        self._manager = _wayland.wl_proxy_marshal_flags(
            ctypes.c_void_p(registry),
            ctypes.c_uint32(0),
            ctypes.byref(_manager_interface),
            ctypes.c_uint32(protocol_version),
            ctypes.c_uint32(0),
            ctypes.c_uint32(name),
            _MANAGER_NAME,
            ctypes.c_uint32(protocol_version),
            ctypes.c_void_p(),
        )

    def _on_motion(
        self,
        _data: int,
        _relative_pointer: int,
        time_hi: int,
        time_lo: int,
        dx: int,
        dy: int,
        _dx_unaccelerated: int,
        _dy_unaccelerated: int,
    ) -> None:
        if self._context is None or not self._drag_active:
            return
        self._pending_dx += dx / 256.0
        self._pending_dy += dy / 256.0
        motion_time_us = (time_hi << 32) | time_lo
        if (
            self._last_motion_time_us is None
            or motion_time_us - self._last_motion_time_us >= _DISPATCH_INTERVAL_US
        ):
            self._last_motion_time_us = motion_time_us
            self._dispatch_token += 1
            self._dispatch_scheduled = False
            self._flush_motion()
            return
        if self._dispatch_scheduled:
            return
        self._dispatch_scheduled = True
        self._dispatch_token += 1
        token = self._dispatch_token
        QTimer.singleShot(4, lambda: self._flush_scheduled_motion(token))

    def _flush_scheduled_motion(self, token: int) -> None:
        if token != self._dispatch_token:
            return
        self._flush_motion()

    def _flush_motion(self) -> None:
        self._dispatch_scheduled = False
        dx = self._pending_dx
        dy = self._pending_dy
        self._pending_dx = 0.0
        self._pending_dy = 0.0
        if self._context is None or not self._drag_active or (dx == 0.0 and dy == 0.0):
            return
        self._context.dispatcher.dispatch_event(PointerMotionObserved(dx=dx, dy=dy))

    def begin_drag(self) -> None:
        """Start a fresh relative-pointer drag."""

        self._reset_pending_motion()
        self._drag_active = self._context is not None

    def end_drag(self) -> None:
        """Stop the current drag and discard its buffered movement."""

        self._drag_active = False
        self._reset_pending_motion()

    def commit_surface(self, surface: int) -> None:
        """Commit the current Qt-owned surface without retaining its pointer."""

        if self._context is None or not self._drag_active:
            return
        version = _wayland.wl_proxy_get_version(surface)
        _wayland.wl_proxy_marshal_flags(
            ctypes.c_void_p(surface),
            ctypes.c_uint32(6),
            ctypes.c_void_p(),
            ctypes.c_uint32(version),
            ctypes.c_uint32(0),
        )
        if self._display is not None:
            _wayland.wl_display_flush(self._display)

    @staticmethod
    def _destroy_protocol_object(proxy: int) -> None:
        version = _wayland.wl_proxy_get_version(proxy)
        _wayland.wl_proxy_marshal_flags(
            ctypes.c_void_p(proxy),
            ctypes.c_uint32(0),
            ctypes.c_void_p(),
            ctypes.c_uint32(version),
            ctypes.c_uint32(_DESTROY),
        )
