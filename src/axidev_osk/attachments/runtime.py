"""Install a profile's attachments and apply their options as state changes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..config.models import DwellClickConfig, HotCornerConfig, PointerLocatorConfig
from ..config.profile import AttachmentConfig, ProfileConfig
from ..runtime.dispatcher import Unsubscribe
from ..runtime.profile_runtime import BindingTracker
from . import HotCornersOptions


@dataclass(frozen=True, slots=True)
class WindowAttachments:
    """What a window must install when it is built."""

    dwell: DwellClickConfig | None = None
    pointer_locators: tuple[PointerLocatorConfig, ...] = ()


class AttachmentWindow(Protocol):
    def set_dwell(self, config: DwellClickConfig) -> None: ...

    def set_pointer_locator(self, settings: PointerLocatorConfig) -> None: ...


class HotCornerTarget(Protocol):
    def configure(self, settings: HotCornerConfig, corners: frozenset[str]) -> None: ...


class AttachmentRuntime:
    """Hold the active profile's attachments and keep their options following state."""

    def __init__(
        self,
        bindings: BindingTracker,
        *,
        window_lookup: Callable[[str], AttachmentWindow | None],
        hot_corners: HotCornerTarget | None = None,
    ) -> None:
        self._bindings = bindings
        self._window_lookup = window_lookup
        self._hot_corners = hot_corners
        self._dwell: dict[str, DwellClickConfig] = {}
        self._locators: dict[str, dict[str, PointerLocatorConfig]] = {}
        self._secure_input_panel_window: str | None = None
        self._unbinds: list[Unsubscribe] = []

    @property
    def secure_input_panel_window(self) -> str | None:
        return self._secure_input_panel_window

    def start(self, profile: ProfileConfig) -> None:
        """Bind every attachment's options for ``profile``; the config decoder already checked their references."""

        by_kind: dict[str, list[AttachmentConfig]] = {}
        for attachment in profile.attachments:
            by_kind.setdefault(attachment.kind, []).append(attachment)
        self.stop()
        panels = by_kind.get("secure_input_panel", [])
        self._secure_input_panel_window = panels[0].target if panels else None
        for attachment in by_kind.get("dwell", []):
            self._bind(attachment, self._dwell_applier(attachment.target or ""))
        for attachment in by_kind.get("pointer_locator", []):
            self._bind(attachment, self._locator_applier(attachment.target or ""))
        if self._hot_corners is not None:
            for attachment in by_kind.get("hot_corners", []):
                self._bind(attachment, self._hot_corners_applier(self._hot_corners))

    def stop(self) -> None:
        for unbind in self._unbinds:
            unbind()
        self._unbinds.clear()
        self._dwell.clear()
        self._locators.clear()

    def for_window(self, window_id: str) -> WindowAttachments:
        """Return the attachments a window installs, with their current options."""

        return WindowAttachments(
            dwell=self._dwell.get(window_id),
            pointer_locators=tuple(self._locators.get(window_id, {}).values()),
        )

    def _bind(self, attachment: AttachmentConfig, apply: Callable[[object], None]) -> None:
        self._unbinds.append(
            self._bindings.bind(
                attachment.values.decode,
                f"attachment:{attachment.id}",
                lambda options, _previous: apply(options),
                fallback=attachment.values.initial,
            )
        )

    def _dwell_applier(self, window_id: str) -> Callable[[object], None]:
        def apply(options: object) -> None:
            assert isinstance(options, DwellClickConfig)
            self._dwell[window_id] = options
            window = self._window_lookup(window_id)
            if window is not None:
                window.set_dwell(options)

        return apply

    def _locator_applier(self, window_id: str) -> Callable[[object], None]:
        def apply(options: object) -> None:
            assert isinstance(options, PointerLocatorConfig)
            self._locators.setdefault(window_id, {})[options.id] = options
            window = self._window_lookup(window_id)
            if window is not None:
                window.set_pointer_locator(options)

        return apply

    @staticmethod
    def _hot_corners_applier(target: HotCornerTarget) -> Callable[[object], None]:
        def apply(options: object) -> None:
            assert isinstance(options, HotCornersOptions)
            target.configure(options.settings, options.corners)

        return apply
