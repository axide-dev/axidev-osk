"""Bundled default app configuration."""

from __future__ import annotations

from ...runtime.identity import stable_id, validate_unique_ids
from ...windows.overlay import AlwaysOnTopWindowConfig, OverlayPlacement
from ..models import AppConfig, ChromeConfig, KeyboardGridConfig, KeyboardStatusConfig, OverlayConfig, SurfaceConfig, WindowConfig
from .us_iso import build_us_iso_layout_config


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
    keyboard_grid_id = stable_id(keyboard_surface_id, "component", "keyboard-grid", stable_override="component:keyboard-grid")
    keyboard_status_id = stable_id(keyboard_surface_id, "component", "keyboard-status", stable_override="component:keyboard-status")
    keyboard_window = WindowConfig(
        id=keyboard_window_id,
        title="axidev OSK",
        surface=SurfaceConfig(
            id=keyboard_surface_id,
            components=(
                KeyboardGridConfig(
                    id=keyboard_grid_id,
                    layout=build_us_iso_layout_config(parent_id=keyboard_surface_id),
                ),
                KeyboardStatusConfig(id=keyboard_status_id),
            ),
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
