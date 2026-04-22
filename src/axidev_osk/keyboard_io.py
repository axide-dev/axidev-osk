from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

from .models import KeySpec


class AxidevIoKeyboardBackend:
    def __init__(self) -> None:
        self._keyboard: Any | None = None
        self._ready = False
        self._status_text = "Keyboard output is unavailable."

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
            keyboard.initialize(key_delay_us=2000)
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
            self._keyboard.shutdown()
        except Exception as exc:
            print(f"axidev_io shutdown failed: {exc}", file=sys.stderr)
        finally:
            self._keyboard = None
            self._ready = False

    def press_key(self, spec: KeySpec, latched_keys: Mapping[str, bool]) -> None:
        if spec.latchable or not self._ready or self._keyboard is None:
            return

        try:
            text_output = self._resolve_text_output(spec, latched_keys)
            if text_output is not None:
                self._keyboard.sender.type_text(text_output)
                return

            key_name = spec.io_key
            if key_name is None:
                return

            mods = self._resolve_sender_modifiers(spec, latched_keys)
            if mods is None:
                self._keyboard.sender.tap(key_name)
                return

            self._keyboard.sender.tap(key_name, mods=mods)
        except Exception as exc:
            print(f"axidev_io key dispatch failed for {spec.label!r}: {exc}", file=sys.stderr)

    def _resolve_text_output(self, spec: KeySpec, latched_keys: Mapping[str, bool]) -> str | None:
        shift = bool(latched_keys.get("shift", False))
        caps = bool(latched_keys.get("caps", False))

        if spec.io_key == "Space":
            return " "

        if len(spec.label) == 1 and spec.label.isalpha():
            use_uppercase = shift ^ caps
            return spec.label.upper() if use_uppercase else spec.label.lower()

        if spec.secondary_label is not None:
            return spec.secondary_label if shift else spec.label

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

        modifiers: list[str] = []
        if latched_keys.get("shift", False):
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
