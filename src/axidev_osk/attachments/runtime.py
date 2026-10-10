"""Install a profile's attachments and route the actions they own."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol

from ..config.models import DwellClickConfig, HotCornerConfig, PointerLocatorConfig
from ..config.profile import ProfileConfig
from ..messages import DataMap, MessageResult, RuntimeAction
from ..runtime.decoding import bool_value, non_empty_string_value, require_keys, validated_action
from ..runtime.dispatcher import Dispatcher
from ..runtime.profile_runtime import ProfileRuntime
from . import DwellOptions, HotCornersOptions, PointerLocatorOptions, SecureInputPanelOptions

DWELL_SET_ENABLED = "dwell.set_enabled"


@dataclass(frozen=True, slots=True)
class DwellSetEnabledArguments:
    dwell: str
    enabled: bool


def dwell_set_enabled(dwell: str, enabled: bool) -> RuntimeAction:
    return validated_action(DWELL_SET_ENABLED, {"dwell": dwell, "enabled": enabled}, decode_dwell_set_enabled)


def decode_dwell_set_enabled(arguments: DataMap) -> DwellSetEnabledArguments:
    require_keys(arguments, ("dwell", "enabled"))
    return DwellSetEnabledArguments(
        dwell=non_empty_string_value(arguments, "dwell"),
        enabled=bool_value(arguments, "enabled"),
    )


@dataclass(frozen=True, slots=True)
class WindowAttachments:
    """What a window must install when it is built."""

    dwell: DwellClickConfig | None = None
    pointer_locators: tuple[PointerLocatorConfig, ...] = ()


class DwellTarget(Protocol):
    def set_dwell_enabled(self, enabled: bool) -> None: ...


class HotCornerTarget(Protocol):
    def configure(self, settings: HotCornerConfig, corners: frozenset[str]) -> None: ...


class AttachmentRuntime:
    """Hold the active profile's attachments and own ``dwell.set_enabled``."""

    def __init__(
        self,
        dispatcher: Dispatcher,
        profile_runtime: ProfileRuntime,
        *,
        window_lookup: Callable[[str], DwellTarget | None],
        hot_corners: HotCornerTarget | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._profile_runtime = profile_runtime
        self._window_lookup = window_lookup
        self._hot_corners = hot_corners
        self._dwell: dict[str, DwellOptions] = {}
        self._dwell_by_window: dict[str, str] = {}
        self._locators: dict[str, list[PointerLocatorConfig]] = {}
        self._secure_input_panel_window: str | None = None
        profile_runtime.declare_root("dwell", {})
        dispatcher.register_action(DWELL_SET_ENABLED, decode_dwell_set_enabled, self._set_dwell_enabled)

    @property
    def secure_input_panel_window(self) -> str | None:
        return self._secure_input_panel_window

    def start(self, profile: ProfileConfig) -> None:
        """Validate references and prepare attachments for ``profile``.

        Every check runs before anything changes, so a rejected profile leaves
        the current attachments as they were.
        """

        window_ids = {window.id for window in profile.windows}
        dwell: dict[str, DwellOptions] = {}
        dwell_by_window: dict[str, str] = {}
        locators: dict[str, list[PointerLocatorConfig]] = {}
        hot_corners: list[HotCornersOptions] = []
        panels: list[SecureInputPanelOptions] = []
        for attachment in profile.attachments:
            options = attachment.options
            target = getattr(options, "window", None)
            if target is not None and target not in window_ids:
                raise ValueError(f"Attachment {attachment.id!r} targets unknown window {target!r}")
            if isinstance(options, DwellOptions):
                if options.window in dwell_by_window:
                    raise ValueError(f"Window {options.window!r} has more than one dwell attachment")
                dwell[attachment.id] = options
                dwell_by_window[options.window] = attachment.id
            elif isinstance(options, PointerLocatorOptions):
                locators.setdefault(options.window, []).append(options.settings)
            elif isinstance(options, HotCornersOptions):
                hot_corners.append(options)
            elif isinstance(options, SecureInputPanelOptions):
                panels.append(options)
        if len(hot_corners) > 1:
            raise ValueError("A profile can have at most one hot_corners attachment")
        if len(panels) > 1:
            raise ValueError("A profile can have at most one secure_input_panel attachment")
        self._dwell = dwell
        self._dwell_by_window = dwell_by_window
        self._locators = locators
        self._secure_input_panel_window = panels[0].window if panels else None
        if hot_corners and self._hot_corners is not None:
            self._hot_corners.configure(hot_corners[0].settings, hot_corners[0].corners)
        observed: MessageResult = []
        for dwell_id, options in self._dwell.items():
            observed.extend(self._profile_runtime.set_observed(("dwell", dwell_id, "enabled"), options.settings.enabled))
        self._dispatcher.dispatch(*observed)

    def for_window(self, window_id: str) -> WindowAttachments:
        """Return the attachments a window installs, with dwell's current enabled state."""

        dwell: DwellClickConfig | None = None
        dwell_id = self._dwell_by_window.get(window_id)
        if dwell_id is not None:
            enabled = bool(self._profile_runtime.state.get(("dwell", dwell_id, "enabled")))
            dwell = replace(self._dwell[dwell_id].settings, enabled=enabled)
        return WindowAttachments(dwell=dwell, pointer_locators=tuple(self._locators.get(window_id, ())))

    def _set_dwell_enabled(self, arguments: DwellSetEnabledArguments) -> MessageResult:
        options = self._dwell.get(arguments.dwell)
        if options is None:
            raise ValueError(f"No dwell attachment named {arguments.dwell!r}")
        window = self._window_lookup(options.window)
        if window is not None:
            window.set_dwell_enabled(arguments.enabled)
        return self._profile_runtime.set_observed(("dwell", arguments.dwell, "enabled"), arguments.enabled)
