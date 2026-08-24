"""Source-path construction for configured windows and components."""

from __future__ import annotations

from collections.abc import Iterator

from ..config.models import (
    AppConfig,
    ButtonConfig,
    ComponentConfig,
    KeyboardGridConfig,
    KeyConfig,
    PromptConfig,
    SpacerConfig,
    WindowConfig,
)
from .source import SourcePath, SourcePathSegment


def app_source_path(config: AppConfig) -> SourcePath:
    """Return the app/profile root shared by all configured source paths."""

    return SourcePath(
        (
            SourcePathSegment("app", config.app_id),
            SourcePathSegment("profile", config.active_profile_id),
        )
    )


def window_source_path(config: AppConfig, window_id: str) -> SourcePath:
    return app_source_path(config).child("window", window_id)


def surface_source_path(config: AppConfig, window_id: str, surface_id: str) -> SourcePath:
    return window_source_path(config, window_id).child("surface", surface_id)


def iter_interactive_source_paths(config: AppConfig) -> Iterator[SourcePath]:
    """Yield exact paths for every configured key and generic button."""

    for window in config.windows:
        yield from _iter_surface_controls(config, window)
    yield from _iter_prompt_controls(config, config.quit_prompt)
    yield from _iter_prompt_controls(config, config.linux_permission_prompt)


def iter_all_source_paths(config: AppConfig) -> Iterator[SourcePath]:
    """Yield every configured source path, including containers and spacers."""

    root = app_source_path(config)
    yield root
    for window in config.windows:
        yield from _iter_window_paths(config, window)
    for prompt in (config.quit_prompt, config.linux_permission_prompt):
        yield from _iter_prompt_paths(config, prompt)


def _iter_window_paths(config: AppConfig, window: WindowConfig) -> Iterator[SourcePath]:
    window_path = window_source_path(config, window.id)
    yield window_path
    surface_path = window_path.child("surface", window.surface.id)
    yield surface_path
    yield from _iter_components(surface_path, window.surface.components)


def _iter_surface_controls(config: AppConfig, window: WindowConfig) -> Iterator[SourcePath]:
    surface_path = surface_source_path(config, window.id, window.surface.id)
    for path, component in _walk_components(surface_path, window.surface.components):
        if isinstance(component, (KeyConfig, ButtonConfig)):
            yield path


def _iter_prompt_paths(config: AppConfig, prompt: PromptConfig) -> Iterator[SourcePath]:
    window_path = window_source_path(config, prompt.window_id)
    yield window_path
    surface_path = window_path.child("surface", prompt.surface_id)
    yield surface_path
    prompt_path = surface_path.child("component", prompt.id)
    yield prompt_path
    for button in prompt.buttons:
        yield prompt_path.child("component", button.id)


def _iter_prompt_controls(config: AppConfig, prompt: PromptConfig) -> Iterator[SourcePath]:
    prompt_path = surface_source_path(config, prompt.window_id, prompt.surface_id).child(
        "component", prompt.id
    )
    for button in prompt.buttons:
        yield prompt_path.child("component", button.id)


def _iter_components(parent: SourcePath, components: tuple[ComponentConfig, ...]) -> Iterator[SourcePath]:
    for component in components:
        path = parent.child("component", component.id)
        yield path
        if isinstance(component, KeyboardGridConfig):
            layout_path = path.child("layout", component.layout.id)
            yield layout_path
            for grid in component.layout.grids:
                grid_path = layout_path.child("grid", grid.id)
                yield grid_path
                for child in grid.components:
                    yield grid_path.child("component", child.id)


def _walk_components(
    parent: SourcePath,
    components: tuple[ComponentConfig, ...],
) -> Iterator[tuple[SourcePath, ComponentConfig | KeyConfig | SpacerConfig]]:
    for component in components:
        path = parent.child("component", component.id)
        yield path, component
        if isinstance(component, KeyboardGridConfig):
            layout_path = path.child("layout", component.layout.id)
            for grid in component.layout.grids:
                grid_path = layout_path.child("grid", grid.id)
                for child in grid.components:
                    yield grid_path.child("component", child.id), child
