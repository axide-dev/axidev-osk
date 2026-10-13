"""Install a profile's attachments and apply their options as state changes."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ..config.models import DwellClickConfig, PointerLocatorConfig
from ..config.profile import ProfileConfig
from ..runtime.dispatcher import Unsubscribe
from ..runtime.profile_runtime import BindingTracker
from . import AttachmentKind, AttachmentUnavailable, AttachmentWindow, HotCornerTarget

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WindowAttachments:
    """What a window must install when it is built."""

    dwell: DwellClickConfig | None = None
    pointer_locators: tuple[PointerLocatorConfig, ...] = ()


class AttachmentRuntime:
    """Hold the active profile's attachments and keep their options following state."""

    def __init__(
        self,
        bindings: BindingTracker,
        kinds: Mapping[str, AttachmentKind],
        *,
        window_lookup: Callable[[str], AttachmentWindow | None],
        hot_corners: HotCornerTarget | None = None,
    ) -> None:
        self._bindings = bindings
        self._kinds = kinds
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
        """Attach and bind every attachment of ``profile``; the config decoder already checked their references.

        Raises when another profile's attachments are still running: the
        caller stops them first.
        """

        if self._unbinds:
            raise RuntimeError("Attachments are still running; stop them before starting a profile's")
        for attachment in profile.attachments:
            try:
                apply = self._kinds[attachment.kind].attach(self, attachment.target)
            except AttachmentUnavailable as exc:
                _logger.warning("Attachment %r does nothing: %s", attachment.id, exc)
                continue
            self._unbinds.append(
                self._bindings.bind(
                    attachment.values.decode,
                    f"attachment:{attachment.id}",
                    lambda options, _previous, apply=apply: apply(options),
                    fallback=attachment.values.initial,
                )
            )

    def stop(self) -> None:
        for unbind in self._unbinds:
            unbind()
        self._unbinds.clear()
        self._dwell.clear()
        self._locators.clear()
        self._secure_input_panel_window = None
        if self._hot_corners is not None:
            self._hot_corners.clear()

    def for_window(self, window_id: str) -> WindowAttachments:
        """Return the attachments a window installs, with their current options."""

        return WindowAttachments(
            dwell=self._dwell.get(window_id),
            pointer_locators=tuple(self._locators.get(window_id, {}).values()),
        )

    def window(self, window_id: str) -> AttachmentWindow | None:
        return self._window_lookup(window_id)

    def keep_dwell(self, window_id: str, config: DwellClickConfig) -> None:
        self._dwell[window_id] = config

    def keep_pointer_locator(self, window_id: str, settings: PointerLocatorConfig) -> None:
        self._locators.setdefault(window_id, {})[settings.id] = settings

    def hot_corners(self) -> HotCornerTarget | None:
        return self._hot_corners

    def set_secure_input_panel(self, window_id: str) -> None:
        self._secure_input_panel_window = window_id
