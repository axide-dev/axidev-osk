"""Component package and registry wiring."""

from ..runtime.registries import ComponentRegistry
from .button import register as register_button
from .key import register as register_key


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
    register_button(registry)


__all__ = ["register_components"]
