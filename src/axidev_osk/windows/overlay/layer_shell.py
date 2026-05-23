"""Compatibility alias for shared Wayland layer-shell helpers."""

from __future__ import annotations

import sys

from ...platform import layer_shell as _layer_shell

sys.modules[__name__] = _layer_shell
