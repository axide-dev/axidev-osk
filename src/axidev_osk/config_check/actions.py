"""Whether an action a callback returns could run in its profile, decided without running it."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from ..messages import DataMap, RuntimeAction
from ..runtime.app_messages import (
    ProfileSwitchArguments,
    WindowArguments,
    WindowClickArguments,
    WindowDeltaArguments,
    WindowPointArguments,
    WindowSizeArguments,
)
from ..runtime.engine_messages import KeyboardDownArguments, KeyboardKeyArguments, KeyboardTapArguments
from ..services.keyboard.names import KeyNameError, KeyNames

DecoderLookup = Callable[[str], Callable[[DataMap], object] | None]


class ActionRules:
    """Check returned actions against their registered decoders and the profile they run in.

    An action fails when its name is not registered or its arguments do not
    decode, when a keyboard action names a key or modifier by anything but its
    official spelling, when a window action names a window the profile does not
    define, or when ``profile.switch`` names a profile the root config does not
    have. ``state.set`` paths and values are checked where the state is.
    """

    def __init__(
        self,
        *,
        decoder_for: DecoderLookup,
        names: KeyNames,
        windows: Iterable[str],
        profiles: Iterable[str],
    ) -> None:
        self._decoder_for = decoder_for
        self._names = names
        self._windows = frozenset(windows)
        self._profiles = frozenset(profiles)

    def problems(self, action: RuntimeAction) -> list[str]:
        """Why ``action`` would fail, or nothing when it would run."""

        decoder = self._decoder_for(action.action)
        if decoder is None:
            return [f"Action {action.action!r} is not registered"]
        try:
            decoded = decoder(action.arguments)
        except Exception as exc:
            return [f"Action {action.action!r} has invalid arguments: {type(exc).__name__}: {exc}"]
        try:
            if isinstance(decoded, (KeyboardDownArguments, KeyboardTapArguments)):
                self._names.check(decoded.key, decoded.mods)
            elif isinstance(decoded, KeyboardKeyArguments):
                self._names.check_key(decoded.key)
        except KeyNameError as exc:
            return [f"Action {action.action!r}: {exc}"]
        if isinstance(decoded, (
            WindowArguments, WindowDeltaArguments, WindowPointArguments, WindowSizeArguments, WindowClickArguments
        )) and decoded.window_id not in self._windows:
            return [f"Action {action.action!r} names window {decoded.window_id!r}, which the profile does not define"]
        if isinstance(decoded, ProfileSwitchArguments) and decoded.profile not in self._profiles:
            return [f"Action {action.action!r} names profile {decoded.profile!r}, which the config does not have"]
        return []
