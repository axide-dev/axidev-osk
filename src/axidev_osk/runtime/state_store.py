"""Central runtime state store boundary."""

from __future__ import annotations


class StateStore:
    """Owns durable runtime state outside widgets and services.

    The store is intentionally small in this refactor. It provides the boundary that
    future config reloads, profile switches, and queued command replay can target.
    """

    def __init__(self) -> None:
        """Create an empty state store.

        Args:
            None.

        Returns:
            None.

        Side effects:
            Allocates in-memory state dictionaries.
        """

        self._values: dict[str, dict[str, object]] = {}

    def set(self, namespace: str, key: str, value: object) -> None:
        """Store a value in a namespace.

        Args:
            namespace: Durable state namespace.
            key: Key inside the namespace.
            value: Serializable value to store.

        Returns:
            None.

        Side effects:
            Mutates the in-memory state store.
        """

        self._values.setdefault(namespace, {})[key] = value

    def get(self, namespace: str, key: str, default: object | None = None) -> object | None:
        """Read a value from a namespace.

        Args:
            namespace: Durable state namespace.
            key: Key inside the namespace.
            default: Value returned when the key is absent.

        Returns:
            Stored value or ``default``.

        Side effects:
            None.
        """

        return self._values.get(namespace, {}).get(key, default)

    def clear_namespace(self, namespace: str) -> None:
        """Remove all state in a namespace.

        Args:
            namespace: Namespace to remove.

        Returns:
            None.

        Side effects:
            Mutates the in-memory state store.
        """

        self._values.pop(namespace, None)
