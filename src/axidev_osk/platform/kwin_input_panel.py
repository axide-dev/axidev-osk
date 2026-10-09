"""KWin input-panel surface integration through the Wayland client ABI."""

from __future__ import annotations

import ctypes
import ctypes.util
from collections.abc import Iterable
from dataclasses import dataclass, field


class KWinInputPanelError(RuntimeError):
    """Raised when KWin cannot assign an input-panel role to a window."""


class _WlInterface(ctypes.Structure):
    pass


class _WlMessage(ctypes.Structure):
    _fields_ = [
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


_RegistryGlobal = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.c_char_p,
    ctypes.c_uint32,
)
_RegistryGlobalRemove = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint32,
)


class _WlRegistryListener(ctypes.Structure):
    _fields_ = [("global_", _RegistryGlobal), ("global_remove", _RegistryGlobalRemove)]


_OutputGeometry = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_int32,
    ctypes.c_int32,
    ctypes.c_int32,
    ctypes.c_int32,
    ctypes.c_int32,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_int32,
)
_OutputMode = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.c_int32,
    ctypes.c_int32,
    ctypes.c_int32,
)
_OutputDone = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)
_OutputScale = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32)
_OutputName = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)
_OutputDescription = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)


class _WlOutputListener(ctypes.Structure):
    _fields_ = [
        ("geometry", _OutputGeometry),
        ("mode", _OutputMode),
        ("done", _OutputDone),
        ("scale", _OutputScale),
        ("name", _OutputName),
        ("description", _OutputDescription),
    ]


@dataclass
class _Output:
    global_name: int
    proxy: int
    display_name: str | None = None
    callbacks: list[object] = field(default_factory=list)
    listener: _WlOutputListener | None = None


class _Protocol:
    def __init__(self, library: ctypes.CDLL) -> None:
        self.library = library
        self.registry = _WlInterface.in_dll(library, "wl_registry_interface")
        self.surface = _WlInterface.in_dll(library, "wl_surface_interface")
        self.output = _WlInterface.in_dll(library, "wl_output_interface")

        input_panel_surface_types = (ctypes.POINTER(_WlInterface) * 2)(
            ctypes.pointer(self.output),
            ctypes.POINTER(_WlInterface)(),
        )
        self.input_panel_surface_methods = (_WlMessage * 2)(
            _WlMessage(b"set_toplevel", b"ou", input_panel_surface_types),
            _WlMessage(b"set_overlay_panel", b"", None),
        )
        self.input_panel_surface = _WlInterface(
            b"zwp_input_panel_surface_v1",
            1,
            len(self.input_panel_surface_methods),
            self.input_panel_surface_methods,
            0,
            None,
        )

        input_panel_types = (ctypes.POINTER(_WlInterface) * 2)(
            ctypes.pointer(self.input_panel_surface),
            ctypes.pointer(self.surface),
        )
        self.input_panel_methods = (_WlMessage * 1)(
            _WlMessage(b"get_input_panel_surface", b"no", input_panel_types),
        )
        self.input_panel = _WlInterface(
            b"zwp_input_panel_v1",
            1,
            len(self.input_panel_methods),
            self.input_panel_methods,
            0,
            None,
        )


class KWinInputPanelAttachment:
    """Own the client-side proxy for one input-panel surface role."""

    def __init__(self, client: "_InputPanelClient", panel_surface: int) -> None:
        self._client = client
        self._panel_surface = panel_surface

    def close(self) -> None:
        """Release the client-side role proxy exactly once."""

        if self._panel_surface:
            self._client.destroy_proxy(self._panel_surface)
            self._panel_surface = 0


class _InputPanelClient:
    def __init__(self, library: ctypes.CDLL, display: int) -> None:
        self.library = library
        self.display = display
        self.protocol = _Protocol(library)
        self.marshal = library.wl_proxy_marshal_flags
        self.marshal.restype = ctypes.c_void_p
        library.wl_proxy_add_listener.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_void_p,
        ]
        library.wl_proxy_add_listener.restype = ctypes.c_int
        library.wl_display_roundtrip.argtypes = [ctypes.c_void_p]
        library.wl_display_roundtrip.restype = ctypes.c_int
        library.wl_display_flush.argtypes = [ctypes.c_void_p]
        library.wl_display_flush.restype = ctypes.c_int
        library.wl_proxy_destroy.argtypes = [ctypes.c_void_p]
        library.wl_proxy_destroy.restype = None

        self.registry = self.marshal(
            ctypes.c_void_p(display),
            ctypes.c_uint32(1),
            ctypes.pointer(self.protocol.registry),
            ctypes.c_uint32(1),
            ctypes.c_uint32(0),
            None,
        )
        if not self.registry:
            raise KWinInputPanelError("cannot read the Wayland registry")

        self.input_panel = 0
        self._input_panel_global: tuple[int, int] | None = None
        self._advertised_outputs: dict[int, int] = {}
        self.outputs: dict[int, _Output] = {}
        self._initialized = False
        self._registry_callbacks = (
            _RegistryGlobal(self._registry_global),
            _RegistryGlobalRemove(self._registry_global_remove),
        )
        self._registry_listener = _WlRegistryListener(*self._registry_callbacks)
        listener_pointer = ctypes.cast(
            ctypes.pointer(self._registry_listener),
            ctypes.POINTER(ctypes.c_void_p),
        )
        if library.wl_proxy_add_listener(self.registry, listener_pointer, None) != 0:
            self.destroy_proxy(self.registry)
            self.registry = 0
            raise KWinInputPanelError("cannot listen to the Wayland registry")
        try:
            self._roundtrip()
            if self._input_panel_global is None:
                raise KWinInputPanelError("KWin did not expose zwp_input_panel_v1")
            if not self._advertised_outputs:
                raise KWinInputPanelError("KWin did not expose a Wayland output")
            for name, version in self._advertised_outputs.items():
                self._bind_output(name, version)
            self._roundtrip()
            if not any(output.display_name for output in self.outputs.values()):
                raise KWinInputPanelError(
                    "KWin outputs do not expose names through wl_output version 4"
                )
            if self._input_panel_global is None:
                raise KWinInputPanelError("KWin removed zwp_input_panel_v1 during setup")
            self.input_panel = _bind_global(
                self.marshal,
                self.registry,
                self.protocol.input_panel,
                self._input_panel_global,
            )
            self._initialized = True
        except Exception:
            self._cleanup_initialization()
            raise

    def attach(self, surface: int, output_name: str) -> KWinInputPanelAttachment:
        """Assign an input-panel role on the Qt-selected output."""

        self._roundtrip()
        try:
            output = _select_output(self.outputs.values(), output_name)
        except KWinInputPanelError:
            self._roundtrip()
            output = _select_output(self.outputs.values(), output_name)
        panel_surface = self.marshal(
            ctypes.c_void_p(self.input_panel),
            ctypes.c_uint32(0),
            ctypes.pointer(self.protocol.input_panel_surface),
            ctypes.c_uint32(1),
            ctypes.c_uint32(0),
            None,
            ctypes.c_void_p(surface),
        )
        if not panel_surface:
            raise KWinInputPanelError("KWin refused the input-panel surface")
        self.marshal(
            ctypes.c_void_p(panel_surface),
            ctypes.c_uint32(0),
            None,
            ctypes.c_uint32(1),
            ctypes.c_uint32(0),
            ctypes.c_void_p(output.proxy),
            ctypes.c_uint32(0),
        )
        if self.library.wl_display_flush(self.display) < 0:
            self.destroy_proxy(panel_surface)
            raise KWinInputPanelError("KWin closed the input-method connection")
        return KWinInputPanelAttachment(self, panel_surface)

    def destroy_proxy(self, proxy: int) -> None:
        """Destroy one local Wayland proxy without touching Qt's display or surface."""

        if proxy:
            self.library.wl_proxy_destroy(ctypes.c_void_p(proxy))

    def _roundtrip(self) -> None:
        if self.library.wl_display_roundtrip(self.display) < 0:
            raise KWinInputPanelError("KWin closed the input-method connection")

    def _registry_global(
        self,
        data: ctypes.c_void_p,
        registry_proxy: ctypes.c_void_p,
        name: int,
        interface: bytes,
        version: int,
    ) -> None:
        del data, registry_proxy
        try:
            if interface == b"zwp_input_panel_v1" and self._input_panel_global is None:
                self._input_panel_global = (name, version)
            elif interface == b"wl_output":
                self._advertised_outputs[name] = version
                if self._initialized:
                    self._bind_output(name, version)
        except KWinInputPanelError:
            pass

    def _registry_global_remove(
        self,
        data: ctypes.c_void_p,
        registry_proxy: ctypes.c_void_p,
        name: int,
    ) -> None:
        del data, registry_proxy
        if self._input_panel_global is not None and self._input_panel_global[0] == name:
            self._input_panel_global = None
        self._advertised_outputs.pop(name, None)
        output = self.outputs.pop(name, None)
        if output is not None:
            self.destroy_proxy(output.proxy)

    def _bind_output(self, name: int, version: int) -> None:
        proxy = _bind_global(
            self.marshal,
            self.registry,
            self.protocol.output,
            (name, version),
            maximum_version=4,
        )
        output = _Output(name, proxy)

        @_OutputGeometry
        def geometry(*args: object) -> None:
            del args

        @_OutputMode
        def mode(*args: object) -> None:
            del args

        @_OutputDone
        def done(*args: object) -> None:
            del args

        @_OutputScale
        def scale(*args: object) -> None:
            del args

        @_OutputName
        def output_name(data: ctypes.c_void_p, output_proxy: ctypes.c_void_p, value: bytes) -> None:
            del data, output_proxy
            output.display_name = value.decode("utf-8", errors="replace")

        @_OutputDescription
        def description(*args: object) -> None:
            del args

        output.callbacks.extend((geometry, mode, done, scale, output_name, description))
        output.listener = _WlOutputListener(*output.callbacks)
        listener_pointer = ctypes.cast(
            ctypes.pointer(output.listener),
            ctypes.POINTER(ctypes.c_void_p),
        )
        if self.library.wl_proxy_add_listener(proxy, listener_pointer, None) != 0:
            self.destroy_proxy(proxy)
            raise KWinInputPanelError("cannot listen to a Wayland output")
        self.outputs[name] = output

    def _cleanup_initialization(self) -> None:
        for output in self.outputs.values():
            self.destroy_proxy(output.proxy)
        self.outputs.clear()
        if self.input_panel:
            self.destroy_proxy(self.input_panel)
            self.input_panel = 0
        if self.registry:
            self.destroy_proxy(self.registry)
            self.registry = 0


_clients: dict[int, _InputPanelClient] = {}


def attach_kwin_input_panel(
    window_id: int,
    *,
    output_name: str,
) -> KWinInputPanelAttachment:
    """Assign KWin's keyboard role to an unmapped Qt surface on its selected output."""

    if not window_id:
        raise KWinInputPanelError("Qt did not create a Wayland surface")
    if not output_name:
        raise KWinInputPanelError("Qt did not select a Wayland output")
    library_name = ctypes.util.find_library("wayland-client")
    if not library_name:
        raise KWinInputPanelError("libwayland-client is unavailable")

    library = ctypes.CDLL(library_name)
    library.wl_proxy_get_display.argtypes = [ctypes.c_void_p]
    library.wl_proxy_get_display.restype = ctypes.c_void_p
    surface = ctypes.c_void_p(window_id)
    display = library.wl_proxy_get_display(surface)
    if not display:
        raise KWinInputPanelError("Qt window ID is not a Wayland surface")

    display_id = int(display)
    client = _client_for_display(library, display_id)
    return client.attach(window_id, output_name)


def _client_for_display(library: ctypes.CDLL, display: int) -> _InputPanelClient:
    client = _clients.get(display)
    if client is None:
        client = _InputPanelClient(library, display)
        _clients[display] = client
    return client


def _select_output(outputs: Iterable[_Output], output_name: str) -> _Output:
    candidates = tuple(outputs)
    for output in candidates:
        if output.display_name == output_name:
            return output
    available = ", ".join(
        sorted(output.display_name for output in candidates if output.display_name)
    )
    detail = available or "none named"
    raise KWinInputPanelError(
        f"KWin did not expose Qt output {output_name!r}; available outputs: {detail}"
    )


def _bind_global(
    marshal: object,
    registry: int,
    interface: _WlInterface,
    advertised: tuple[int, int],
    *,
    maximum_version: int | None = None,
) -> int:
    name, advertised_version = advertised
    version = min(interface.version, advertised_version)
    if maximum_version is not None:
        version = min(version, maximum_version)
    proxy = marshal(
        ctypes.c_void_p(registry),
        ctypes.c_uint32(0),
        ctypes.pointer(interface),
        ctypes.c_uint32(version),
        ctypes.c_uint32(0),
        ctypes.c_uint32(name),
        interface.name,
        ctypes.c_uint32(version),
        None,
    )
    if not proxy:
        raise KWinInputPanelError(f"cannot bind {interface.name.decode()}")
    return proxy
