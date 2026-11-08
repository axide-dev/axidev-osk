"""A registry of named kinds that the profile decoder reads as a mapping."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Generic, Protocol, TypeVar


class _Named(Protocol):
    @property
    def name(self) -> str: ...


KindT = TypeVar("KindT", bound=_Named)


class KindRegistry(Mapping[str, KindT], Generic[KindT]):
    """Hold kinds by name; a name can be registered once."""

    def __init__(self) -> None:
        self._kinds: dict[str, KindT] = {}

    def register(self, kind: KindT) -> None:
        if kind.name in self._kinds:
            raise ValueError(f"Kind {kind.name!r} is already registered")
        self._kinds[kind.name] = kind

    def __getitem__(self, name: str) -> KindT:
        return self._kinds[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._kinds)

    def __len__(self) -> int:
        return len(self._kinds)
