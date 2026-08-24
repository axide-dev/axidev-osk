"""Adapter around axidev_io keyboard output and key-state observation."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from ...models import KeySpec
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

KeyStateListener = Callable[[str, bool], None]
Unsubscribe = Callable[[], None]


@dataclass(frozen=True)
class KeyPressHandle:
    """Backend key press handle tracked until release.

    Attributes:
        key_name: Canonical backend key name.
        mods: Optional backend modifier chord sent with the key.
        repeats: Whether the backend should auto-repeat the press.
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
        self._pressed_key_names: set[str] = set()
        self._key_state_listeners: list[KeyStateListener] = []
        self._listener_unsubscribe: Unsubscribe | None = None
        self._key_state_lock = RLock()

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
        """Initialize axidev_io keyboard output and state observation."""

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
        self._start_key_state_listener()
        return True

    def shutdown(self) -> None:
        """Release held keys and shut down the backend."""

        if self._keyboard is None:
            return

        try:
            self._stop_key_state_listener()
            self._keyboard.shutdown()
        except Exception as exc:
            _logger.exception("axidev_io shutdown failed: %s", exc)
        finally:
            self._keyboard = None
            self._ready = False
            self._clear_pressed_key_names()

    def add_key_state_listener(self, listener: KeyStateListener) -> Unsubscribe:
        """Register a backend key-state listener and return an unsubscribe callback."""

        with self._key_state_lock:
            self._key_state_listeners.append(listener)
        active = True

        def unsubscribe() -> None:
            nonlocal active
            if not active:
                return
            active = False
            with self._key_state_lock:
                try:
                    self._key_state_listeners.remove(listener)
                except ValueError:
                    return

        return unsubscribe

    def is_key_down(self, key_name: str) -> bool:
        """Return whether a canonical backend key is currently pressed."""

        canonical_name = self._canonical_key_name(key_name)
        if canonical_name is None:
            return False

        with self._key_state_lock:
            return canonical_name in self._pressed_key_names

    def key_name_for_spec(self, spec: KeySpec) -> str | None:
        """Resolve a key spec to a canonical backend key name."""

        key_name = self._resolve_key_name(spec)
        if key_name is None:
            return None
        return self._canonical_key_name(key_name)

    def key_down(self, spec: KeySpec, latched_keys: Mapping[str, bool]) -> KeyPressHandle | None:
        """Emit a key press for ``spec`` and return a handle for release."""

        if not self._ready or self._keyboard is None:
            return None
        if spec.latchable and not spec.holds_when_latched:
            return None
        try:
            press = self._resolve_key_press(spec, latched_keys)
            if press is None:
                return None

            if spec.holds_when_latched:
                self._debug_modifier("request-down", key_id=spec.key_id, press=self._describe_press(press))
            self._send_key_down(press)
            self._set_key_down(press.key_name, True)
            if spec.holds_when_latched:
                self._debug_modifier("press-active", key_id=spec.key_id, press=self._describe_press(press))
            return press
        except Exception as exc:
            _logger.exception("axidev_io key_down failed for %r: %s", spec.label, exc)
            return None

    def key_up(self, press: object | None) -> None:
        """Release a key press previously returned by ``key_down``."""

        if not self._ready or self._keyboard is None or not isinstance(press, KeyPressHandle):
            return

        try:
            if _is_modifier_key_name(press.key_name):
                self._debug_modifier("request-up", key_id=None, press=self._describe_press(press))
            if press.mods is None:
                self._keyboard.sender.key_up(press.key_name)
            else:
                self._keyboard.sender.key_up(press.key_name, mods=press.mods)
            self._set_key_down(press.key_name, False)
            if _is_modifier_key_name(press.key_name):
                self._debug_modifier("press-released", key_id=None, press=self._describe_press(press))
        except Exception as exc:
            _logger.exception("axidev_io key_up failed for %r: %s", press.key_name, exc)

    def _resolve_key_press(self, spec: KeySpec, latched_keys: Mapping[str, bool]) -> KeyPressHandle | None:
        key_name = self._resolve_key_name(spec)
        if key_name is None:
            return None

        mods = self._resolve_sender_modifiers(spec, latched_keys)
        return KeyPressHandle(key_name=key_name, mods=mods, repeats=spec.repeats)

    def _send_key_down(self, press: KeyPressHandle) -> None:
        if self._keyboard is None:
            return
        if press.mods is None:
            self._keyboard.sender.key_down(press.key_name, repeat=press.repeats)
        else:
            self._keyboard.sender.key_down(
                press.key_name,
                mods=press.mods,
                repeat=press.repeats,
            )

    def _debug_modifier(self, action: str, **context: object) -> None:
        if not keyboard_debug_enabled():
            return
        details = ", ".join(f"{key}={value!r}" for key, value in context.items())
        _logger.info("keyboard modifier %s: %s", action, details)

    @staticmethod
    def _describe_press(press: KeyPressHandle | None) -> str | None:
        if press is None:
            return None
        return f"{press.key_name} mods={press.mods!r} repeat={press.repeats}"

    def _resolve_key_name(self, spec: KeySpec) -> str | None:
        if spec.io_key is not None:
            return spec.io_key
        if len(spec.label) == 1:
            return spec.label
        return None

    def _canonical_key_name(self, key_name: str) -> str | None:
        if self._keyboard is None:
            return key_name

        try:
            parsed_key = self._keyboard.keys.parse(key_name)
            formatted_key = self._keyboard.keys.format(parsed_key)
            return formatted_key or key_name
        except Exception:
            return key_name

    def _resolve_sender_modifiers(
        self,
        spec: KeySpec,
        latched_keys: Mapping[str, bool],
    ) -> str | None:
        if not spec.honors_latched_modifiers:
            return None

        shift = bool(latched_keys.get("shift", False))
        caps = bool(latched_keys.get("caps", False))
        shift_is_held = self.is_key_down("ShiftLeft") or self.is_key_down("ShiftRight")
        modifiers: list[str] = []

        if len(spec.label) == 1 and spec.label.isalpha():
            if (shift and not shift_is_held) ^ caps:
                modifiers.append("Shift")
        elif shift and not shift_is_held:
            modifiers.append("Shift")

        if not modifiers:
            return None

        return "+".join(modifiers)

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

    def _start_key_state_listener(self) -> None:
        if self._keyboard is None or self._listener_unsubscribe is not None:
            return

        try:
            self._listener_unsubscribe = self._keyboard.listener.start(self._handle_key_event)
        except Exception as exc:
            _logger.exception("axidev_io listener startup failed: %s", exc)

    def _stop_key_state_listener(self) -> None:
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
        self._set_key_down(key_name, bool(getattr(event, "pressed", False)))

    def _set_key_down(self, key_name: str, pressed: bool) -> None:
        canonical_name = self._canonical_key_name(key_name)
        if canonical_name is None:
            return

        with self._key_state_lock:
            was_pressed = canonical_name in self._pressed_key_names
            if pressed == was_pressed:
                return
            if pressed:
                self._pressed_key_names.add(canonical_name)
            else:
                self._pressed_key_names.discard(canonical_name)

        self._notify_key_state_listeners(canonical_name, pressed)

    def _clear_pressed_key_names(self) -> None:
        with self._key_state_lock:
            pressed_key_names = tuple(self._pressed_key_names)
            self._pressed_key_names.clear()

        for key_name in pressed_key_names:
            self._notify_key_state_listeners(key_name, False)

    def _notify_key_state_listeners(self, key_name: str, pressed: bool) -> None:
        with self._key_state_lock:
            listeners = tuple(self._key_state_listeners)

        for listener in listeners:
            try:
                listener(key_name, pressed)
            except Exception as exc:
                _logger.exception("axidev_io key state listener failed for %r: %s", key_name, exc)


def _is_modifier_key_name(key_name: str) -> bool:
    return key_name.replace("_", "").replace("-", "").lower() in _MODIFIER_KEY_NAMES
