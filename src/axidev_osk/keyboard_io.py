from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .models import KeySpec


@dataclass(frozen=True)
class KeyPressHandle:
    key_name: str
    mods: str | None = None


class AxidevIoKeyboardBackend:
    def __init__(self) -> None:
        self._keyboard: Any | None = None
        self._ready = False
        self._status_text = "Keyboard output is unavailable."
        self._held_latched_keys: dict[str, KeyPressHandle] = {}

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def status_text(self) -> str:
        return self._status_text

    def initialize(self) -> bool:
        if self._ready:
            return True

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
            self._status_text = f"axidev_io initialization failed: {exc}"
            return False

        backend_name = keyboard.status().backend_name
        self._keyboard = keyboard
        self._ready = True
        self._status_text = f"Keyboard output ready via axidev_io ({backend_name})."
        return True

    def shutdown(self) -> None:
        if self._keyboard is None:
            return

        try:
            self._release_all_latched_keys()
            self._keyboard.shutdown()
        except Exception as exc:
            print(f"axidev_io shutdown failed: {exc}", file=sys.stderr)
        finally:
            self._keyboard = None
            self._ready = False
            self._held_latched_keys.clear()

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
        repo_root = Path(__file__).resolve().parents[2]
        submodule_path = repo_root / "vendor" / "axidev-io-python"
        if submodule_path.is_dir():
            return "Install the submodule package with `python -m pip install -e ./vendor/axidev-io-python`."
        return "Initialize the submodule, then install it with `python -m pip install -e ./vendor/axidev-io-python`."

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
