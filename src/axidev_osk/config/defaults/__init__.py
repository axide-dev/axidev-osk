"""Bundled default app configuration."""

from __future__ import annotations

from ...components.prompt import prompt_button_config
from ...runtime.identity import stable_id, validate_unique_ids
from ...windows.overlay import AlwaysOnTopWindowConfig, OverlayPlacement
from ..models import (
    AppConfig,
    ButtonConfig,
    ChromeConfig,
    HotCornerConfig,
    KeyboardGridConfig,
    KeyboardStatusConfig,
    OverlayConfig,
    PromptConfig,
    SurfaceConfig,
    WindowConfig,
)
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
                    layout=build_us_iso_layout_config(
                        parent_id=keyboard_surface_id,
                        target_window_id=keyboard_window_id,
                    ),
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
        quit_prompt=_build_default_quit_prompt(app_id),
        linux_permission_prompt=_build_default_linux_permission_prompt(app_id),
        hot_corner=HotCornerConfig(
            bindings={
                "top_left": [keyboard_window.id],
                "top_right": [keyboard_window.id],
                "bottom_left": [keyboard_window.id],
                "bottom_right": [keyboard_window.id],
            }
        ),
    )


def _build_default_quit_prompt(app_id: str) -> PromptConfig:
    """Build the bundled quit confirmation prompt config.

    Args:
        app_id: Stable application ID used as the prompt ID namespace.

    Returns:
        Prompt config matching the existing quit confirmation copy and buttons.

    Side effects:
        None.
    """

    window_id = stable_id(app_id, "window", "quit-prompt", stable_override="window:quit-prompt")
    surface_id = stable_id(window_id, "surface", "prompt", stable_override="surface:quit-prompt")
    prompt_id = stable_id(surface_id, "prompt", "quit", stable_override="prompt:quit")
    return PromptConfig(
        id=prompt_id,
        window_id=window_id,
        surface_id=surface_id,
        title="Close axidev-osk?",
        message="Do you want to close axidev-osk? This will stop OSK input.",
        buttons=(
            prompt_button_config(prompt_id, role="accepted", label="Yes"),
            prompt_button_config(prompt_id, role="rejected", label="No"),
        ),
        prompt_glyph="!",
        danger=True,
        hint=(
            "Tip: if you only want to hide OSK, move your cursor into "
            "the screen corner; the hot-corner sensor will hide it without "
            "shutting the app down."
        ),
    )


def _build_default_linux_permission_prompt(app_id: str) -> PromptConfig:
    """Build the bundled Linux permission setup prompt config.

    Args:
        app_id: Stable application ID used as the prompt ID namespace.

    Returns:
        Prompt config matching the existing Linux permission prompt copy and buttons.

    Side effects:
        None.
    """

    window_id = stable_id(
        app_id,
        "window",
        "linux-permission-prompt",
        stable_override="window:linux-permission-prompt",
    )
    surface_id = stable_id(
        window_id,
        "surface",
        "prompt",
        stable_override="surface:linux-permission-prompt",
    )
    prompt_id = stable_id(surface_id, "prompt", "linux-permission", stable_override="prompt:linux-permission")
    return PromptConfig(
        id=prompt_id,
        window_id=window_id,
        surface_id=surface_id,
        title="Linux Input Permission",
        message="Keyboard output is blocked by Linux permissions.",
        buttons=(
            ButtonConfig(
                id=stable_id(
                    prompt_id,
                    "button",
                    "open_terminal",
                    stable_override="prompt:linux-permission:button:open_terminal",
                ),
                role="open_terminal",
                label="Open In Terminal",
            ),
            ButtonConfig(
                id=stable_id(
                    prompt_id,
                    "button",
                    "setup_here",
                    stable_override="prompt:linux-permission:button:setup_here",
                ),
                role="setup_here",
                label="Run Setup Here",
            ),
            ButtonConfig(
                id=stable_id(
                    prompt_id,
                    "button",
                    "already_configured",
                    stable_override="prompt:linux-permission:button:already_configured",
                ),
                role="already_configured",
                label="Already Configured",
            ),
            ButtonConfig(
                id=stable_id(
                    prompt_id,
                    "button",
                    "rejected",
                    stable_override="prompt:linux-permission:button:rejected",
                ),
                role="rejected",
                label="Cancel",
            ),
        ),
        prompt_glyph="?",
        hint=(
            "Choose Open In Terminal to run the bundled helper in a real terminal window so sudo can prompt there. "
            "Run Setup Here still tries the helper directly from the app, but some desktops do not surface that prompt correctly. "
            "If you already ran setup, this session may just need a log out and back in."
        ),
        minimum_size=(560, 150),
    )
