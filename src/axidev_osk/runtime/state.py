"""Central state tree read by profile functions and written through actions."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from typing import TypeAlias

from ..messages import DataMap, DataValue, copy_data_map

StatePath: TypeAlias = tuple[str, ...]

RUNTIME_STATE_ROOTS = frozenset({"input", "windows", "dwell", "keyboard"})
"""Roots written only by the runtime from observations; profiles can read them."""


def parse_state_path(text: str) -> StatePath:
    """Parse a dot-separated profile state path such as ``std.latched.shift``."""

    if not isinstance(text, str) or not text:
        raise ValueError("State path must be a non-empty string")
    segments = tuple(text.split("."))
    if any(not segment for segment in segments):
        raise ValueError(f"State path {text!r} contains an empty segment")
    return segments


def path_text(path: StatePath) -> str:
    return ".".join(path)


def paths_overlap(left: StatePath, right: StatePath) -> bool:
    """Return whether a change at one path can affect a read at the other."""

    size = min(len(left), len(right))
    return left[:size] == right[:size]


class StateTree:
    """Own durable state as one tree of native data.

    Maps are nested state branches. Every stored value is copied on the way in
    and on the way out, so callers never share mutable state with the tree.
    """

    def __init__(self, initial: DataMap | None = None) -> None:
        self._root: DataMap = copy_data_map(initial or {})

    def reset(self, initial: DataMap) -> None:
        """Replace all state, for example on profile start or reload."""

        self._root = copy_data_map(initial)

    def snapshot(self) -> DataMap:
        return deepcopy(self._root)

    def get(self, path: StatePath) -> DataValue:
        """Return a copy of the value at ``path``, or ``None`` when absent."""

        node = self._lookup(path)
        return deepcopy(node)

    def set(self, path: StatePath, value: DataValue) -> bool:
        """Store ``value`` at ``path`` and return whether the tree changed.

        Storing ``None`` removes the key, matching Lua's ``nil`` assignment.
        """

        if not path:
            raise ValueError("State path cannot be empty")
        copied = copy_data_map({"value": value})["value"]
        branch = self._root
        for index, segment in enumerate(path[:-1]):
            child = branch.get(segment)
            if child is None:
                child = {}
                branch[segment] = child
            elif not isinstance(child, dict):
                raise ValueError(
                    f"Cannot set {path_text(path)!r}: {path_text(path[: index + 1])!r} is not a map"
                )
            branch = child
        if copied is None:
            # Like Lua, assigning nil removes the key.
            return branch.pop(path[-1], None) is not None
        if path[-1] in branch and branch[path[-1]] == copied:
            return False
        branch[path[-1]] = copied
        return True

    def view(self, recorder: "ReadRecorder | None" = None) -> "StateView":
        """Return a read-only view, optionally recording which paths are read."""

        return StateView(self, (), recorder)

    def _lookup(self, path: StatePath) -> DataValue:
        node: DataValue = self._root
        for segment in path:
            if not isinstance(node, dict):
                return None
            node = node.get(segment)
            if node is None:
                return None
        return node


class ReadRecorder:
    """Collect the deepest state paths read by one function call."""

    def __init__(self) -> None:
        self._paths: set[StatePath] = set()

    @property
    def paths(self) -> frozenset[StatePath]:
        return frozenset(self._paths)

    def read(self, parent: StatePath, child: StatePath) -> None:
        self._paths.discard(parent)
        self._paths.add(child)

    def read_whole(self, path: StatePath) -> None:
        self._paths.add(path)


class StateView:
    """Read-only access to the state tree with Lua-like semantics.

    ``view.name`` and ``view["name"]`` return the stored value, a nested view
    for maps, or ``None`` when the value is absent.
    """

    __slots__ = ("_tree", "_path", "_recorder")

    def __init__(self, tree: StateTree, path: StatePath, recorder: ReadRecorder | None) -> None:
        self._tree = tree
        self._path = path
        self._recorder = recorder

    def __getattr__(self, name: str) -> "DataValue | StateView":
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def __getitem__(self, name: str) -> "DataValue | StateView":
        if not isinstance(name, str):
            raise TypeError("State keys must be strings")
        child = (*self._path, name)
        if self._recorder is not None:
            self._recorder.read(self._path, child)
        value = self._tree._lookup(child)  # noqa: SLF001
        if isinstance(value, dict):
            return StateView(self._tree, child, self._recorder)
        return deepcopy(value)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self[name] is not None

    def __iter__(self) -> Iterator[str]:
        if self._recorder is not None:
            self._recorder.read_whole(self._path)
        value = self._tree._lookup(self._path)  # noqa: SLF001
        return iter(tuple(value)) if isinstance(value, dict) else iter(())

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, StateView):
            return self.to_data() == other.to_data()
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]

    def to_data(self) -> DataValue:
        """Return a plain copy of this branch, recording a whole-branch read."""

        if self._recorder is not None:
            self._recorder.read_whole(self._path)
        return self._tree.get(self._path)

    def __repr__(self) -> str:
        return f"StateView({path_text(self._path) or '<root>'})"
