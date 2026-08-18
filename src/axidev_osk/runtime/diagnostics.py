"""Opt-in runtime diagnostics shared across subsystem boundaries."""

from __future__ import annotations

import os


KEYBOARD_DEBUG_ENV = "AXIDEV_OSK_KEYBOARD_DEBUG"


def keyboard_debug_enabled() -> bool:
    """Return whether modifier state tracing is enabled."""

    return os.environ.get(KEYBOARD_DEBUG_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
