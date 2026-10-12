"""Central state: a registry of declared variables read by profile functions and written through actions.

Every value lives in a declared variable. The engine declares what it
observes, the root config declares what every profile shares, and the active
profile declares its own. The tree stores values and checks them against
their declared type, but it never knows what any of them mean.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy

from ..config.variables import (
    MapOf,
    Record,
    Slot,
    StatePath,
    Variable,
    VariableError,
    VarType,
    check,
    descend,
    empty_value,
    path_text,
)
from ..messages import DataMap, DataValue, copy_data_value, data_equal

__all__ = [
    "ReadRecorder",
    "StatePath",
    "StateTree",
    "StateView",
    "VariableError",
    "parse_state_path",
    "path_text",
    "paths_overlap",
]


def parse_state_path(text: str) -> StatePath:
    """Parse a dot-separated profile state path such as ``std.latched.shift``."""

    if not text:
        raise ValueError("State path must be a non-empty string")
    segments = tuple(text.split("."))
    if any(not segment for segment in segments):
        raise ValueError(f"State path {text!r} contains an empty segment")
    return segments


def paths_overlap(left: StatePath, right: StatePath) -> bool:
    """Return whether a change at one path can affect a read at the other."""

    size = min(len(left), len(right))
    return left[:size] == right[:size]


class StateTree:
    """Own durable state as declared variables in one tree of native data.

    Variables are declared by an owner (``engine``, ``shared``, or
    ``profile``) and hold their default until set. Reading or writing a path no
    declaration covers raises ``VariableError``. Setting ``None`` resets a
    variable or record field to its default and removes a map entry. Every
    value is copied on the way in and on the way out.
    """

    def __init__(self) -> None:
        self._root: DataMap = {}
        self._variables: dict[StatePath, Variable] = {}
        self._owners: dict[StatePath, str] = {}

    def declare(self, variables: Mapping[StatePath, Variable], owner: str) -> None:
        """Add variables with their default values; a path overlapping a declared one is rejected."""

        for path in variables:
            clash = next((other for other in (*self._variables, *variables) if other != path and paths_overlap(path, other)), None)
            if clash is not None or path in self._variables:
                raise VariableError(f"State variable {path_text(path)!r} overlaps {path_text(clash or path)!r}")
        for path, variable in variables.items():
            self._variables[path] = variable
            self._owners[path] = owner
            branch = self._root
            for segment in path[:-1]:
                child = branch.setdefault(segment, {})
                assert isinstance(child, dict)
                branch = child
            branch[path[-1]] = copy_data_value(variable.default)

    def undeclare(self, owner: str) -> None:
        """Remove every variable ``owner`` declared, with its value."""

        for path in [path for path, declared_by in self._owners.items() if declared_by == owner]:
            del self._variables[path]
            del self._owners[path]
            self._prune(path)

    def declarations(self, owner: str) -> dict[StatePath, Variable]:
        return {path: variable for path, variable in self._variables.items() if self._owners[path] == owner}

    def owner(self, path: StatePath) -> str:
        """Return who declared the variable covering ``path``."""

        return self._owners[self.slot(path).variable]

    def slot(self, path: StatePath) -> Slot:
        """Return where ``path`` lands in its declared variable, raising when nothing declares it."""

        for size in range(len(path), 0, -1):
            variable = self._variables.get(path[:size])
            if variable is not None:
                return descend(path[:size], variable, path[size:])
        raise VariableError(f"State path {path_text(path)!r} is not declared")

    def is_branch(self, path: StatePath) -> bool:
        """Whether ``path`` only groups declared variables, such as the root or ``std``."""

        return any(len(declared) > len(path) and declared[: len(path)] == path for declared in self._variables)

    def get(self, path: StatePath) -> DataValue:
        """Return a copy of the value at ``path``; an absent map entry reads as ``None``."""

        if path and not self.is_branch(path):
            self.slot(path)
        return deepcopy(self._lookup(path))

    def set(self, path: StatePath, value: DataValue) -> bool:
        """Store ``value`` at ``path`` and return whether the tree changed, including a map entry it created.

        ``None`` resets a variable or record field to its default and removes a
        map entry, the way Lua's ``nil`` removes a table field.
        """

        if not path:
            raise ValueError("State path cannot be empty")
        slot = self.slot(path)
        if value is None and slot.default is None:
            return self._remove(path, slot)
        stored = copy_data_value(slot.default) if value is None else check(slot.type, value, path_text(path))
        return self._write(path, slot, stored)

    def view(self, recorder: "ReadRecorder | None" = None) -> "StateView":
        """Return a read-only view, optionally recording which paths are read."""

        return StateView(self, (), recorder)

    def _write(self, path: StatePath, slot: Slot, value: DataValue) -> bool:
        container = self._container(slot.variable)
        name = slot.variable[-1]
        var_type: VarType = self._variables[slot.variable].type
        created = False
        for segment in path[len(slot.variable):]:
            child = container[name]
            assert isinstance(child, dict)
            var_type = _child_type(var_type, segment)
            if child.get(segment) is None:
                child[segment] = empty_value(var_type)
                created = True
            container, name = child, segment
        if data_equal(container[name], value):
            return created
        container[name] = value
        return True

    def _remove(self, path: StatePath, slot: Slot) -> bool:
        """Remove a map entry, then any enclosing map entries the removal left empty."""

        trail: list[DataMap] = [self._container(slot.variable)]
        names = [slot.variable[-1], *path[len(slot.variable):]]
        for name in names[:-1]:
            child = trail[-1].get(name)
            if not isinstance(child, dict):
                return False
            trail.append(child)
        if trail[-1].pop(names[-1], None) is None:
            return False
        variable_type = self._variables[slot.variable].type
        types = [variable_type]
        for segment in names[1:]:
            types.append(_child_type(types[-1], segment))
        # trail[depth] is the value named names[depth - 1]; only entries of a map are removed, never the variable.
        for depth in range(len(trail) - 1, 1, -1):
            if trail[depth] or not isinstance(types[depth - 2], MapOf):
                break
            del trail[depth - 1][names[depth - 1]]
        return True

    def _container(self, variable: StatePath) -> DataMap:
        branch = self._root
        for segment in variable[:-1]:
            child = branch[segment]
            assert isinstance(child, dict)
            branch = child
        return branch

    def _prune(self, path: StatePath) -> None:
        trail: list[DataMap] = [self._root]
        for segment in path[:-1]:
            child = trail[-1].get(segment)
            if not isinstance(child, dict):
                return
            trail.append(child)
        trail[-1].pop(path[-1], None)
        for depth in range(len(trail) - 1, 0, -1):
            if trail[depth]:
                break
            del trail[depth - 1][path[depth - 1]]

    def _lookup(self, path: StatePath) -> DataValue:
        node: DataValue = self._root
        for segment in path:
            if not isinstance(node, dict):
                return None
            node = node.get(segment)
            if node is None:
                return None
        return node


def _child_type(var_type: VarType, segment: str) -> VarType:
    if isinstance(var_type, MapOf):
        return var_type.item
    assert isinstance(var_type, Record)
    return var_type.fields[segment].type


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
    """Read-only access to declared state with Lua-like semantics.

    ``view.name`` and ``view["name"]`` return the stored value, a nested view
    for maps, or ``None`` for an absent map entry. Reading a path no
    declaration covers raises ``VariableError``.
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
        if not self._tree.is_branch(child):
            self._tree.slot(child)
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
