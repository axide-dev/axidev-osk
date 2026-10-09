"""Adapter around axidev_io keyboard output and key observation."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from ...runtime.diagnostics import keyboard_debug_enabled

_logger = logging.getLogger(__name__)

_MODIFIER_KEY_NAMES = frozenset(
    {
        "shift",
        "shiftleft",
        "shiftright",
        "ctrl",
        "ctrlleft",
        "ctrlright",
        "alt",
        "altleft",
        "altright",
        "super",
        "superleft",
        "superright",
    }
)

Unsubscribe = Callable[[], None]


@dataclass(frozen=True)
class KeyObservation:
    """One observed key transition, as reported by the input listener.

    Attributes:
        key: Canonical key name, such as ``A``, ``ShiftLeft``, or ``.``.
        text: Text the key produced in the active layout, if any.
        modifiers: Active modifier and lock names, such as ``Shift`` or ``CapsLock``.
        pressed: Whether the key went down.
    """

    key: str
    text: str | None
    modifiers: tuple[str, ...]
    pressed: bool


ObservationListener = Callable[[KeyObservation], None]


@dataclass(frozen=True)
class KeyPressHandle:
    """A held key, kept until it is released.

    Attributes:
        key_name: Canonical backend key name.
        mods: Optional backend modifier chord sent with the key.
        repeats: Whether the backend auto-repeats the press.
    """

    key_name: str
    mods: str | None = None
    repeats: bool = True


class AxidevIoKeyboardBackend:
    """Keyboard backend facade used by the runtime keyboard service."""

    def __init__(self) -> None:
        self._keyboard: Any | None = None
        self._ready = False
        self._status_text = "Keyboard output is unavailable."
        self._needs_permission_setup = False
        self._observation_listeners: list[ObservationListener] = []
        self._listener_unsubscribe: Unsubscribe | None = None
        self._listeners_lock = RLock()

    @property
    def ready(self) -> bool:
        """Whether keyboard output is initialized and available."""

        return self._ready

    @property
    def status_text(self) -> str:
        """Human-readable backend status for UI display."""

        return self._status_text

    @property
    def needs_permission_setup(self) -> bool:
        """Whether Linux input permissions must be configured before use."""

        return self._needs_permission_setup

    @property
    def permission_setup_text(self) -> str:
        """Human-readable instructions for resolving permission issues."""

        return self._build_permission_setup_text()

    def initialize(self) -> bool:
        """Initialize axidev_io keyboard output and key observation."""

        if self._ready:
            return True

        self._needs_permission_setup = False

        try:
            from axidev_io import keyboard
        except Exception as exc:
            self._status_text = (
                f"axidev_io is not available: {exc}. "
                f"{self._build_install_hint()}"
            )
            return False

        try:
            keyboard.initialize(
                key_delay_us=2000,
                log_level="debug" if keyboard_debug_enabled() else "info",
            )
        except Exception as exc:
            if self._is_linux_permission_error(exc):
                self._needs_permission_setup = True
                self._status_text = (
                    "axidev_io initialization failed: permission_denied. "
                    "Linux input permissions still need to be configured for this user, "
                    "or the current session needs a logout/login refresh after setup."
                )
            else:
                self._status_text = f"axidev_io initialization failed: {exc}"
            return False

        backend_name = keyboard.status().backend_name
        self._keyboard = keyboard
        self._ready = True
        self._status_text = f"Keyboard output ready via axidev_io ({backend_name})."
        self._start_listener()
        return True

    def shutdown(self) -> None:
        """Stop observation and shut down the backend."""

        if self._keyboard is None:
            return

        try:
            self._stop_listener()
            self._keyboard.shutdown()
        except Exception as exc:
            _logger.exception("axidev_io shutdown failed: %s", exc)
        finally:
            self._keyboard = None
            self._ready = False

    def add_observation_listener(self, listener: ObservationListener) -> Unsubscribe:
        """Register a listener for every observed key transition.

        Listeners are called on the backend's listener thread.
        """

        with self._listeners_lock:
            self._observation_listeners.append(listener)

        def unsubscribe() -> None:
            with self._listeners_lock:
                if listener in self._observation_listeners:
                    self._observation_listeners.remove(listener)

        return unsubscribe

    def canonical_key(self, key_name: str) -> str:
        """Return the backend's canonical spelling of a key name."""

        if self._keyboard is None:
            return key_name
        try:
            formatted = self._keyboard.keys.format(self._keyboard.keys.parse(key_name))
            return formatted or key_name
        except Exception:
            return key_name

    def press(self, key: str, mods: tuple[str, ...], repeat: bool) -> KeyPressHandle | None:
        """Send a key down with explicit modifiers and return its release handle."""

        if not self._ready or self._keyboard is None:
            return None
        press = KeyPressHandle(
            key_name=self.canonical_key(key),
            mods="+".join(mods) if mods else None,
            repeats=repeat,
        )
        try:
            self._debug_press("down", press)
            if press.mods is None:
                self._keyboard.sender.key_down(press.key_name, repeat=press.repeats)
            else:
                self._keyboard.sender.key_down(press.key_name, mods=press.mods, repeat=press.repeats)
            return press
        except Exception as exc:
            _logger.exception("axidev_io key down failed for %r: %s", key, exc)
            return None

    def key_up(self, press: object | None) -> None:
        """Release a key press previously returned by ``press``."""

        if not self._ready or self._keyboard is None or not isinstance(press, KeyPressHandle):
            return
        try:
            self._debug_press("up", press)
            if press.mods is None:
                self._keyboard.sender.key_up(press.key_name)
            else:
                self._keyboard.sender.key_up(press.key_name, mods=press.mods)
        except Exception as exc:
            _logger.exception("axidev_io key_up failed for %r: %s", press.key_name, exc)

    def tap(self, key: str, mods: tuple[str, ...]) -> None:
        """Send one key press and release with explicit modifiers."""

        if not self._ready or self._keyboard is None:
            return
        try:
            if mods:
                self._keyboard.sender.tap(self.canonical_key(key), mods=list(mods))
            else:
                self._keyboard.sender.tap(self.canonical_key(key))
        except Exception as exc:
            _logger.exception("axidev_io tap failed for %r: %s", key, exc)

    def type_text(self, text: str) -> None:
        """Type text through the backend's layout-aware text output."""

        if not self._ready or self._keyboard is None:
            return
        try:
            self._keyboard.sender.type_text(text)
        except Exception as exc:
            _logger.exception("axidev_io type_text failed: %s", exc)

    def _debug_press(self, action: str, press: KeyPressHandle) -> None:
        if not keyboard_debug_enabled() or press.key_name.casefold() not in _MODIFIER_KEY_NAMES:
            return
        _logger.info(
            "keyboard modifier %s: %s mods=%r repeat=%s",
            action,
            press.key_name,
            press.mods,
            press.repeats,
        )

    def _build_install_hint(self) -> str:
        repo_root = self._repo_root()
        submodule_path = repo_root / "vendor" / "axidev-io-python"
        if submodule_path.is_dir():
            return "Install the submodule package with `python -m pip install -e ./vendor/axidev-io-python`."
        return "Initialize the submodule, then install it with `python -m pip install -e ./vendor/axidev-io-python`."

    @staticmethod
    def _repo_root() -> Path:
        """Return the source checkout root containing the vendored backend."""

        return Path(__file__).resolve().parents[4]

    def _build_permission_setup_text(self) -> str:
        return (
            "Linux blocked keyboard output because this session does not currently have access to /dev/uinput.\n\n"
            "The most reliable fix is to open a terminal and run:\n"
            "axidev-osk linux setup-permissions\n\n"
            "Run that command from a real terminal so sudo can prompt there.\n"
            "If the setup step reports that access was applied but a logout is still required, "
            "log out and back in before testing again.\n"
            "If you already ran the setup in this session, either log out and back in, then relaunch the app, "
            "or retry once from a terminal with:\n"
            "sg uinput -c axidev-osk"
        )

    def _is_linux_permission_error(self, exc: Exception) -> bool:
        if not sys.platform.startswith("linux"):
            return False
        return "permission_denied" in str(exc).lower()

    def _start_listener(self) -> None:
        if self._keyboard is None or self._listener_unsubscribe is not None:
            return
        try:
            self._listener_unsubscribe = self._keyboard.listener.start(self._handle_key_event)
        except Exception as exc:
            _logger.exception("axidev_io listener startup failed: %s", exc)

    def _stop_listener(self) -> None:
        if self._listener_unsubscribe is None:
            return
        try:
            self._listener_unsubscribe()
        except Exception as exc:
            _logger.exception("axidev_io listener shutdown failed: %s", exc)
        finally:
            self._listener_unsubscribe = None

    def _handle_key_event(self, event: object) -> None:
        key_name = getattr(event, "key_name", None)
        if not isinstance(key_name, str) or not key_name:
            return
        text = getattr(event, "text", None)
        modifiers = getattr(event, "modifiers", ())
        observation = KeyObservation(
            key=key_name,
            text=text if isinstance(text, str) and text else None,
            modifiers=tuple(str(name) for name in modifiers) if isinstance(modifiers, tuple) else (),
            pressed=bool(getattr(event, "pressed", False)),
        )
        with self._listeners_lock:
            listeners = tuple(self._observation_listeners)
        for listener in listeners:
            try:
                listener(observation)
            except Exception as exc:
                _logger.exception("axidev_io observation listener failed: %s", exc)
