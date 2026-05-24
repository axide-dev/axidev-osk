"""Re-exports for keyboard grid metrics.

The ``KeyboardMetrics`` DTO was promoted to ``axidev_osk.config.models``
because it is pure data and configurable per grid. This module is kept
as a stable import alias for existing callers and provides
``DEFAULT_KEYBOARD_METRICS`` as a convenience for the rare site that
needs a fallback (tests, ad-hoc widget construction).
"""

from __future__ import annotations

from ...config.models import KeyboardMetrics

DEFAULT_KEYBOARD_METRICS = KeyboardMetrics()

__all__ = ["DEFAULT_KEYBOARD_METRICS", "KeyboardMetrics"]
