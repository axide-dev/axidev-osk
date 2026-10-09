"""Central state tree read by profile functions and written through actions."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from typing import TypeAlias

from ..messages import DataMap, DataValue, copy_data_value, data_equal

StatePath: TypeAlias = tuple[str, ...]


def parse_state_path(text: str) -> StatePath:
    """Parse a dot-separated profile state path such as ``std.latched.shift``."""

    if not text:
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


def _stored(value: object) -> DataValue:
    """Copy a value for storage, dropping map entries set to ``None`` the way Lua drops ``nil`` fields."""

    copied = copy_data_value(value)
    return _without_none(copied)


def _without_none(value: DataValue) -> DataValue:
    if isinstance(value, dict):
        return {key: _without_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_without_none(item) for item in value]
    return value


class StateTree:
    """Own durable state as one tree of native data, with Lua table semantics.

    Maps are nested state branches. Every stored value is copied on the way in
    and on the way out, so callers never share mutable state with the tree. A
    map never holds ``None``: assigning ``None`` removes the key, and a branch
    left empty by a removal is removed too.
    """

    def __init__(self, initial: DataMap | None = None) -> None:
        self._root: DataMap = {}
        self.reset(initial or {})

    def reset(self, initial: DataMap) -> None:
        """Replace all state, for example when a profile starts."""

        stored = _stored(initial)
        if not isinstance(stored, dict):
            raise TypeError("Initial state must be a map")
        self._root = stored

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
        copied = _stored(value)
        if copied is None:
            return self._remove(path)
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
        if path[-1] in branch and data_equal(branch[path[-1]], copied):
            return False
        branch[path[-1]] = copied
        return True

    def _remove(self, path: StatePath) -> bool:
        """Remove ``path`` and any branch the removal leaves empty; a missing path changes nothing."""

        branches: list[DataMap] = [self._root]
        for segment in path[:-1]:
            child = branches[-1].get(segment)
            if not isinstance(child, dict):
                return False
            branches.append(child)
        if branches[-1].pop(path[-1], None) is None:
            return False
        for depth in range(len(branches) - 1, 0, -1):
            if branches[depth]:
                break
            del branches[depth - 1][path[depth - 1]]
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
    """Collect the state paths read by one function call.

    Stepping from a branch to a child keeps only the child, so ``s.a.b`` records
    ``a.b``. Reading a whole branch, by iterating or copying it, is kept even
    when the call later reads its children.
    """

    def __init__(self) -> None:
        self._steps: set[StatePath] = set()
        self._whole: set[StatePath] = set()

    @property
    def paths(self) -> frozenset[StatePath]:
        return frozenset(self._steps | self._whole)

    def read(self, parent: StatePath, child: StatePath) -> None:
        self._steps.discard(parent)
        self._steps.add(child)

    def read_whole(self, path: StatePath) -> None:
        self._whole.add(path)


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

    def __bool__(self) -> bool:
        # Every Lua table is true, even an empty one.
        return True

    def __eq__(self, other: object) -> bool:
        if isinstance(other, StateView):
            return data_equal(self.to_data(), other.to_data())
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]

    def to_data(self) -> DataValue:
        """Return a plain copy of this branch, recording a whole-branch read."""

        if self._recorder is not None:
            self._recorder.read_whole(self._path)
        return self._tree.get(self._path)

    def __repr__(self) -> str:
        return f"StateView({path_text(self._path) or '<root>'})"
