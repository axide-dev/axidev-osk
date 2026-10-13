"""Widget properties the engine sets on windows and nodes, so QSS can target them and no profile style can set them."""

from __future__ import annotations

COMPONENT_TYPE = "componentType"
COMPONENT_ID = "componentId"
CLASSES = "classes"
POINTER_LOCATOR_ENABLED = "pointerLocatorEnabled"
PASSES_INPUT_BLOCK = "passesInputBlock"

ENGINE_WIDGET_PROPERTIES = frozenset({COMPONENT_TYPE, COMPONENT_ID, CLASSES, POINTER_LOCATOR_ENABLED, PASSES_INPUT_BLOCK})
