from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from .models import KeySpec

KeyStateListener = Callable[[str, bool], None]
Unsubscribe = Callable[[], None]


@dataclass(frozen=True)
class KeyPressHandle:
    key_name: str
    mods: str | None = None


@dataclass(frozen=True)
class PermissionSetupOutcome:
    already_granted: bool
    helper_applied: bool
    requires_logout: bool
    helper_path: str | None = None
    error_text: str | None = None


class AxidevIoKeyboardBackend:
    def __init__(self) -> None:
        self._keyboard: Any | None = None
        self._ready = False
        self._status_text = "Keyboard output is unavailable."
        self._needs_permission_setup = False
        self._held_latched_keys: dict[str, KeyPressHandle] = {}
        self._pressed_key_names: set[str] = set()
        self._key_state_listeners: list[KeyStateListener] = []
        self._listener_unsubscribe: Unsubscribe | None = None
        self._key_state_lock = RLock()

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def status_text(self) -> str:
        return self._status_text

    @property
    def needs_permission_setup(self) -> bool:
        return self._needs_permission_setup

    @property
    def permission_setup_text(self) -> str:
        return self._build_permission_setup_text()

    @property
    def permission_setup_script_path(self) -> Path | None:
        return self._permission_script_path()

    @property
    def permission_setup_command(self) -> str:
        script_path = self._permission_script_path()
        if script_path is not None:
            return self._permission_setup_command(script_path)
        return "bash ./vendor/axidev-io-python/vendor/axidev-io/scripts/setup_uinput_permissions.sh"

    def setup_permissions(self) -> PermissionSetupOutcome:
        try:
            from axidev_io import keyboard
        except Exception as exc:
            error_text = (
                f"axidev_io is not available: {exc}. "
                f"{self._build_install_hint()}"
            )
            self._status_text = error_text
            return PermissionSetupOutcome(
                already_granted=False,
                helper_applied=False,
                requires_logout=False,
                error_text=error_text,
            )

        try:
            if sys.platform.startswith("linux"):
                has_required_permissions = getattr(keyboard, "has_required_permissions", None)
                if callable(has_required_permissions) and has_required_permissions():
                    outcome = PermissionSetupOutcome(
                        already_granted=True,
                        helper_applied=False,
                        requires_logout=False,
                        helper_path=None,
                    )
                elif self._permission_script_path() is not None:
                    helper_path = self._run_permission_setup_script()
                    outcome = PermissionSetupOutcome(
                        already_granted=False,
                        helper_applied=True,
                        requires_logout=True,
                        helper_path=helper_path,
                    )
                else:
                    setup_permissions = getattr(keyboard, "setup_permissions", None)
                    if not callable(setup_permissions):
                        raise RuntimeError("axidev_io.keyboard.setup_permissions is unavailable.")

                    result = setup_permissions()
                    helper_path = getattr(result, "helper_path", None)
                    outcome = PermissionSetupOutcome(
                        already_granted=bool(getattr(result, "already_granted", False)),
                        helper_applied=bool(getattr(result, "helper_applied", False)),
                        requires_logout=bool(getattr(result, "requires_logout", False)),
                        helper_path=str(helper_path) if helper_path else None,
                    )
            else:
                setup_permissions = getattr(keyboard, "setup_permissions", None)
                if not callable(setup_permissions):
                    raise RuntimeError("axidev_io.keyboard.setup_permissions is unavailable.")

                result = setup_permissions()
                helper_path = getattr(result, "helper_path", None)
                outcome = PermissionSetupOutcome(
                    already_granted=bool(getattr(result, "already_granted", False)),
                    helper_applied=bool(getattr(result, "helper_applied", False)),
                    requires_logout=bool(getattr(result, "requires_logout", False)),
                    helper_path=str(helper_path) if helper_path else None,
                )
        except Exception as exc:
            error_text = f"Linux permission setup failed: {exc}"
            self._keyboard = None
            self._ready = False
            self._needs_permission_setup = True
            self._status_text = error_text
            return PermissionSetupOutcome(
                already_granted=False,
                helper_applied=False,
                requires_logout=False,
                error_text=error_text,
            )

        if outcome.requires_logout:
            self._keyboard = None
            self._ready = False
            self._needs_permission_setup = True
            self._status_text = (
                "Linux permission setup was applied. "
                "Log out and back in, then relaunch axidev-osk."
            )
            return outcome

        if self.initialize():
            return outcome

        return PermissionSetupOutcome(
            already_granted=outcome.already_granted,
            helper_applied=outcome.helper_applied,
            requires_logout=False,
            helper_path=outcome.helper_path,
            error_text=self._status_text,
        )

    def initialize(self) -> bool:
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
            keyboard.initialize(key_delay_us=2000, log_level="debug")
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
        if self._keyboard is None:
            return

        try:
            self._release_all_latched_keys()
            self._stop_key_state_listener()
            self._keyboard.shutdown()
        except Exception as exc:
            print(f"axidev_io shutdown failed: {exc}", file=sys.stderr)
        finally:
            self._keyboard = None
            self._ready = False
            self._held_latched_keys.clear()
            self._clear_pressed_key_names()

    def add_key_state_listener(self, listener: KeyStateListener) -> Unsubscribe:
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
        canonical_name = self._canonical_key_name(key_name)
        if canonical_name is None:
            return False

        with self._key_state_lock:
            return canonical_name in self._pressed_key_names

    def key_name_for_spec(self, spec: KeySpec) -> str | None:
        key_name = self._resolve_key_name(spec)
        if key_name is None:
            return None
        return self._canonical_key_name(key_name)

    def sync_latched_key(self, spec: KeySpec, latched: bool, active_press: object | None = None) -> object | None:
        if (
            not self._ready
            or self._keyboard is None
            or not spec.holds_when_latched
            or spec.key_id is None
        ):
            return active_press

        resolved_active_press = active_press if isinstance(active_press, KeyPressHandle) else None
        try:
            held_press = self._held_latched_keys.get(spec.key_id)
            if latched:
                if held_press is not None:
                    if resolved_active_press is held_press:
                        return None
                    return active_press

                if resolved_active_press is not None:
                    self._held_latched_keys[spec.key_id] = resolved_active_press
                    return None

                press = self._resolve_latched_press(spec)
                if press is None:
                    return active_press

                if press.mods is None:
                    self._keyboard.sender.key_down(press.key_name)
                else:
                    self._keyboard.sender.key_down(press.key_name, mods=press.mods)
                self._held_latched_keys[spec.key_id] = press
                return active_press

            if held_press is None:
                return active_press

            if held_press.mods is None:
                self._keyboard.sender.key_up(held_press.key_name)
            else:
                self._keyboard.sender.key_up(held_press.key_name, mods=held_press.mods)
            del self._held_latched_keys[spec.key_id]
            if resolved_active_press is held_press:
                return None
            return active_press
        except Exception as exc:
            print(f"axidev_io latch sync failed for {spec.label!r}: {exc}", file=sys.stderr)
            return active_press

    def key_down(self, spec: KeySpec, latched_keys: Mapping[str, bool]) -> KeyPressHandle | None:
        if not self._ready or self._keyboard is None:
            return None
        if spec.latchable and not spec.holds_when_latched:
            return None
        if spec.holds_when_latched and spec.key_id is not None and spec.key_id in self._held_latched_keys:
            return None

        try:
            press = self._resolve_key_press(spec, latched_keys)
            if press is None:
                return None

            if press.mods is None:
                self._keyboard.sender.key_down(press.key_name)
            else:
                self._keyboard.sender.key_down(press.key_name, mods=press.mods)
            return press
        except Exception as exc:
            print(f"axidev_io key_down failed for {spec.label!r}: {exc}", file=sys.stderr)
            return None

    def key_up(self, press: object | None) -> None:
        if not self._ready or self._keyboard is None or not isinstance(press, KeyPressHandle):
            return

        try:
            if press.mods is None:
                self._keyboard.sender.key_up(press.key_name)
            else:
                self._keyboard.sender.key_up(press.key_name, mods=press.mods)
        except Exception as exc:
            print(f"axidev_io key_up failed for {press.key_name!r}: {exc}", file=sys.stderr)

    def _resolve_key_press(self, spec: KeySpec, latched_keys: Mapping[str, bool]) -> KeyPressHandle | None:
        key_name = self._resolve_key_name(spec)
        if key_name is None:
            return None

        mods = self._resolve_sender_modifiers(spec, latched_keys)
        return KeyPressHandle(key_name=key_name, mods=mods)

    def _resolve_latched_press(self, spec: KeySpec) -> KeyPressHandle | None:
        key_name = spec.latched_io_key or spec.io_key
        if key_name is None:
            return None
        return KeyPressHandle(key_name=key_name)

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
        shift_is_held = "shift" in self._held_latched_keys
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

    def _build_permission_setup_text(self) -> str:
        return (
            "Linux blocked keyboard output because this session does not currently have access to /dev/uinput.\n\n"
            "The most reliable fix is to open a terminal and run:\n"
            f"{self.permission_setup_command}\n\n"
            "Run that command from a real terminal so sudo can prompt there.\n"
            "If the setup step reports that access was applied but a logout is still required, "
            "log out and back in before testing again.\n"
            "If you already ran the setup in this session, either log out and back in, then relaunch the app, "
            "or retry once from a terminal with:\n"
            "sg input -c axidev-osk"
        )

    def _application_root(self) -> Path:
        return Path(sys.executable).resolve().parent

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _permission_setup_command(self, script_path: Path) -> str:
        if script_path.parent == self._application_root():
            return f"bash ./{script_path.name}"
        return f"bash {script_path}"

    def _permission_script_path(self) -> Path | None:
        repo_root = self._repo_root()
        for script_path in (
            self._application_root() / "setup_uinput_permissions.sh",
            repo_root / "setup_uinput_permissions.sh",
            repo_root / "vendor" / "axidev-io-python" / "vendor" / "axidev-io" / "scripts" / "setup_uinput_permissions.sh",
        ):
            if script_path.is_file():
                return script_path
        return None

    def _run_permission_setup_script(self) -> str:
        if not sys.platform.startswith("linux"):
            raise RuntimeError("Automatic permission setup is only supported on Linux.")

        script_path = self._permission_script_path()
        if script_path is None:
            raise FileNotFoundError(
                "Linux permission helper not found in the app folder or bundled vendor files."
            )

        try:
            subprocess.run(["bash", str(script_path)], check=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Linux permission helper exited with status {exc.returncode}"
            ) from exc
        except OSError as exc:
            raise RuntimeError(str(exc)) from exc

        return str(script_path)

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
            print(f"axidev_io listener startup failed: {exc}", file=sys.stderr)

    def _stop_key_state_listener(self) -> None:
        if self._listener_unsubscribe is None:
            return

        try:
            self._listener_unsubscribe()
        except Exception as exc:
            print(f"axidev_io listener shutdown failed: {exc}", file=sys.stderr)
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
                print(f"axidev_io key state listener failed for {key_name!r}: {exc}", file=sys.stderr)

    def _release_all_latched_keys(self) -> None:
        if self._keyboard is None:
            return

        for key_id, press in tuple(self._held_latched_keys.items()):
            try:
                if press.mods is None:
                    self._keyboard.sender.key_up(press.key_name)
                else:
                    self._keyboard.sender.key_up(press.key_name, mods=press.mods)
            except Exception as exc:
                print(f"axidev_io key_up failed for latched key {key_id!r}: {exc}", file=sys.stderr)
        self._held_latched_keys.clear()
