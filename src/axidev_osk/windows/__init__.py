"""Generic window and surface builders."""

from .builder import build_window
from .surface import register_surfaces

__all__ = ["build_window", "register_surfaces"]
