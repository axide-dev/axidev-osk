"""Bundled default app configuration."""

from __future__ import annotations

from ...components.prompt import prompt_button_config
from ...runtime.actions import prompt_resolve, window_toggle_opacity
from ...runtime.behaviors import action_behavior
from ...runtime.identity import stable_id, validate_unique_ids
from ...runtime.source import SourcePath, SourcePathSegment
from ...windows.overlay import AlwaysOnTopWindowConfig, OverlayPlacement
from ..models import (
    AppConfig,
    BehaviorBinding,
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
from .us_iso import build_us_iso_behavior_configs, build_us_iso_layout_config


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
    active_profile_id = "profile:default"
    keyboard_window_id = stable_id(app_id, "window", "keyboard", stable_override="window:keyboard")
    keyboard_surface_id = stable_id(keyboard_window_id, "surface", "keyboard", stable_override="surface:keyboard")
    keyboard_grid_id = stable_id(keyboard_surface_id, "component", "keyboard-grid", stable_override="component:keyboard-grid")
    keyboard_status_id = stable_id(keyboard_surface_id, "component", "keyboard-status", stable_override="component:keyboard-status")
    keyboard_layout = build_us_iso_layout_config()
    keyboard_window = WindowConfig(
        id=keyboard_window_id,
        title="axidev OSK",
        surface=SurfaceConfig(
            id=keyboard_surface_id,
            components=(
                KeyboardGridConfig(
                    id=keyboard_grid_id,
                    layout=keyboard_layout,
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
        opacity=0.85,
    )

    quit_prompt = _build_default_quit_prompt(app_id)
    linux_permission_prompt = _build_default_linux_permission_prompt(app_id)
    behaviors = _build_default_behaviors(
        app_id=app_id,
        active_profile_id=active_profile_id,
        keyboard_window=keyboard_window,
        keyboard_grid_id=keyboard_grid_id,
        quit_prompt=quit_prompt,
        linux_permission_prompt=linux_permission_prompt,
    )
    validate_unique_ids((keyboard_window.id,), scope="default app windows")
    return AppConfig(
        app_id=app_id,
        active_profile_id=active_profile_id,
        windows=(keyboard_window,),
        behaviors=behaviors,
        startup_window_ids=(keyboard_window.id,),
        keyboard_window_id=keyboard_window.id,
        quit_prompt=quit_prompt,
        linux_permission_prompt=linux_permission_prompt,
        hot_corner=HotCornerConfig(
            bindings={
                "top_left": [keyboard_window.id],
                "top_right": [keyboard_window.id],
                "bottom_left": [keyboard_window.id],
                "bottom_right": [keyboard_window.id],
            }
        ),
    )


def _build_default_behaviors(
    *,
    app_id: str,
    active_profile_id: str,
    keyboard_window: WindowConfig,
    keyboard_grid_id: str,
    quit_prompt: PromptConfig,
    linux_permission_prompt: PromptConfig,
) -> tuple[BehaviorBinding, ...]:
    root = SourcePath(
        (
            SourcePathSegment("app", app_id),
            SourcePathSegment("profile", active_profile_id),
        )
    )
    surface_path = root.child("window", keyboard_window.id).child(
        "surface", keyboard_window.surface.id
    )
    keyboard_config = keyboard_window.surface.components[0]
    if not isinstance(keyboard_config, KeyboardGridConfig):
        raise TypeError("Default keyboard surface must start with a keyboard grid")
    layout_path = surface_path.child("component", keyboard_grid_id).child(
        "layout", keyboard_config.layout.id
    )
    grid = keyboard_config.layout.grids[0]
    grid_path = layout_path.child("grid", grid.id)
    keyboard_behaviors = build_us_iso_behavior_configs()
    bindings = [
        BehaviorBinding(
            target=grid_path.child("component", component_id),
            default=behavior,
        )
        for component_id, behavior in keyboard_behaviors.items()
    ]

    all_key_ids = {component.id for component in grid.components}
    ghost_ids = all_key_ids - keyboard_behaviors.keys()
    if len(ghost_ids) != 1:
        raise ValueError("US ISO layout must contain exactly one non-keyboard control")
    ghost_id = next(iter(ghost_ids))
    bindings.append(
        BehaviorBinding(
            target=grid_path.child("component", ghost_id),
            default=action_behavior(
                pressed_actions=(
                    window_toggle_opacity(keyboard_window.id, ghost_id, 0.01),
                )
            ),
        )
    )
    bindings.extend(
        _prompt_behavior_bindings(
            root,
            quit_prompt,
            ("accepted", "rejected"),
        )
    )
    bindings.extend(
        _prompt_behavior_bindings(
            root,
            linux_permission_prompt,
            ("open_terminal", "already_configured", "rejected"),
        )
    )
    return tuple(bindings)


def _prompt_behavior_bindings(
    root: SourcePath,
    prompt: PromptConfig,
    results: tuple[str, ...],
) -> list[BehaviorBinding]:
    if len(prompt.buttons) != len(results):
        raise ValueError(f"Prompt {prompt.id!r} button/result counts differ")
    prompt_path = (
        root.child("window", prompt.window_id)
        .child("surface", prompt.surface_id)
        .child("component", prompt.id)
    )
    return [
        BehaviorBinding(
            target=prompt_path.child("component", button.id),
            default=action_behavior(
                released_actions=(prompt_resolve(prompt.id, result),)
            ),
        )
        for button, result in zip(prompt.buttons, results, strict=True)
    ]


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
                label="Open In Terminal",
            ),
            ButtonConfig(
                id=stable_id(
                    prompt_id,
                    "button",
                    "already_configured",
                    stable_override="prompt:linux-permission:button:already_configured",
                ),
                label="Already Configured",
            ),
            ButtonConfig(
                id=stable_id(
                    prompt_id,
                    "button",
                    "rejected",
                    stable_override="prompt:linux-permission:button:rejected",
                ),
                label="Cancel",
            ),
        ),
        prompt_glyph="?",
        hint=(
            "Choose Open In Terminal to run permission setup where sudo can prompt. "
            "If you already ran setup, this session may just need a log out and back in."
        ),
        minimum_size=(560, 150),
    )
