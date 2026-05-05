"""Bundled default app configuration."""

from __future__ import annotations

from ..application.overlay_window import AlwaysOnTopWindowConfig, OverlayPlacement
from ..layouts.us_iso import build_us_iso_layout_config
from ..runtime.identity import stable_id, validate_unique_ids
from .models import AppConfig, ChromeConfig, OverlayConfig, SurfaceConfig, WindowConfig


def build_default_app_config() -> AppConfig:
    """Build the default Axidev OSK runtime config.

    Args:
        None.

    Returns:
        Declarative app config containing the startup keyboard window.

    Side effects:
        Raises ``ValueError`` if deterministic IDs collide.
    """

    app_id = "app:axidev-osk"
    keyboard_window_id = stable_id(app_id, "window", "keyboard", stable_override="window:keyboard")
    keyboard_surface_id = stable_id(keyboard_window_id, "surface", "keyboard", stable_override="surface:keyboard")
    keyboard_window = WindowConfig(
        id=keyboard_window_id,
        title="axidev OSK",
        surface=SurfaceConfig(
            id=keyboard_surface_id,
            kind="keyboard",
            layout=build_us_iso_layout_config(parent_id=keyboard_surface_id),
            margins=(10, 10, 10, 10),
            spacing=8,
        ),
        overlay=OverlayConfig(
            always_on_top=True,
            config=AlwaysOnTopWindowConfig(
                placement=OverlayPlacement.CENTER,
                screen_margin=16,
            ),
        ),
        chrome=ChromeConfig(enabled=True),
    )

    validate_unique_ids((keyboard_window.id,), scope="default app windows")
    return AppConfig(
        windows=(keyboard_window,),
        startup_window_ids=(keyboard_window.id,),
        keyboard_window_id=keyboard_window.id,
    )
