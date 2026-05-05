"""Component package and registry wiring."""

from ..runtime.registries import ComponentRegistry
from .button import register as register_button
from .grid.builder import register as register_grid
from .key import register as register_key
from .prompt import register as register_prompt


def register_components(registry: ComponentRegistry) -> None:
    """Register all bundled component builders.

    Args:
        registry: Component registry owned by the runtime context.

    Returns:
        None.

    Side effects:
        Mutates the registry.
    """

    register_key(registry)
    register_grid(registry)
    register_button(registry)
    register_prompt(registry)


__all__ = ["register_components"]
