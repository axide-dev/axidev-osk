"""Component package and registry wiring."""

from importlib import import_module

from ..runtime.registries import ComponentRegistry

_BUNDLED_COMPONENT_MODULES = (
    "axidev_osk.components.key",
    "axidev_osk.components.grid.builder",
    "axidev_osk.components.button",
    "axidev_osk.components.prompt",
)


def register_components(registry: ComponentRegistry) -> None:
    """Register all bundled component builders.

    Args:
        registry: Component registry owned by the runtime context.

    Returns:
        None.

    Side effects:
        Mutates the registry.
    """

    for module_name in _BUNDLED_COMPONENT_MODULES:
        module = import_module(module_name)
        module.register(registry)


__all__ = ["register_components"]
