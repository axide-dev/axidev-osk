"""Deterministic identity helpers for config nodes and runtime payloads."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable


def stable_id(parent_id: str, kind: str, *identity_fields: object, stable_override: str | None = None) -> str:
    """Return a deterministic ID for a config node.

    Args:
        parent_id: Stable ID of the parent config node.
        kind: Node kind, such as ``window`` or ``key``.
        identity_fields: Values that distinguish this node from siblings.
        stable_override: Optional explicit ID used to preserve state across structural edits.

    Returns:
        A deterministic, machine-independent ID string.

    Side effects:
        None.
    """

    if stable_override:
        return stable_override

    raw_parts = [parent_id, kind, *(str(field) for field in identity_fields)]
    digest = hashlib.blake2s("\x1f".join(raw_parts).encode("utf-8"), digest_size=8).hexdigest()
    return f"{kind}-{digest}"


def prompt_button_id(parent_id: str, role: str) -> str:
    """Return the deterministic component ID for a prompt action button."""

    return stable_id(parent_id, "button", role, stable_override=f"{parent_id}:button:{role}")


def validate_unique_ids(ids: Iterable[str], *, scope: str) -> None:
    """Raise a clear validation error when duplicate deterministic IDs exist.

    Args:
        ids: IDs produced by config builders.
        scope: Human-readable scope included in error messages.

    Returns:
        None.

    Side effects:
        None.
    """

    seen: set[str] = set()
    duplicates: set[str] = set()
    for item_id in ids:
        if item_id in seen:
            duplicates.add(item_id)
        seen.add(item_id)
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise ValueError(f"Duplicate config IDs in {scope}: {duplicate_list}")
