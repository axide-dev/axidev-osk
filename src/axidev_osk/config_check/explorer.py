"""Explore the states one profile can reach through its callbacks, and check every binding and callback in them.

A state is described by how it differs from the start state, unit by unit. A
unit is one declared variable of the root config or the profile, or one entry
of a declared map variable (``std.menus.<group>``, ``std.latched.<latch>``),
since a map holds independent values by name. Engine-observed variables (keys,
locks, windows, node sizes, the running profile) keep their start values and
are never explored.

From the start state the explorer follows every chain of ``state.set``
actions the callbacks return, and keeps every state where at most ``depth``
units differ from the start. In each state it runs every binding record and calls
every callback whose recorded reads overlap the units that differ, and reuses
the start results for the rest: profile functions are pure, so a function
that read nothing that changed returns what it returned before. A record or
callback already run with the same values of the units it reads is not run
again.

A returned ``state.append`` is checked in the state its callback ran in (its
path is a declared list and its value fits the list), but the states it leads
to are not explored, since a list can grow forever.

Each failure is reported once, with the shortest trail of callbacks and state
changes from the start state that reaches it.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from ..config.profile import ProfileConfig, profile_path
from ..config.reader import ConfigError, Resolver
from ..config.variables import MapOf, StatePath, Variable, path_text
from ..function_registry import FunctionRef, FunctionRegistry
from ..messages import DataMap, DataValue, copy_data_map
from ..runtime.functions import call_callback, evaluate_binding
from ..runtime.profile_runtime import (
    ENGINE,
    PROFILE,
    SHARED,
    STATE_APPEND,
    STATE_SET,
    BindingFailed,
    StateSetArguments,
    decode_state_append,
    decode_state_set,
)
from ..runtime.state import ReadRecorder, StateTree, paths_overlap
from .actions import ActionRules
from .report import Problem, Step

Frozen = Hashable
Unit = StatePath
State = tuple[tuple[Unit, Frozen], ...]
"""A state as the units that differ from the start state, ordered by unit."""
Memo = tuple[int, State]

@dataclass(eq=False, slots=True)
class Record:
    """Values decoded together from one config map, any of which may be a binding."""

    source: str
    decode: Callable[[Resolver], object]
    reads: set[StatePath] = field(default_factory=set)


@dataclass(eq=False, slots=True)
class Callback:
    """The callbacks one event runs: a node's callback for its own event, or the profile handlers of one event."""

    calls: tuple[tuple[FunctionRef, str], ...]
    """Each function with its config path, run in order in the same state."""
    source: str
    event: str
    arguments: DataMap
    reads: set[StatePath] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class _Writes:
    """What one set of changes touches: the variables its valid paths land in, those paths, and its invalid paths."""

    variables: frozenset[StatePath]
    sets: tuple[tuple[StatePath, Frozen], ...]
    failures: tuple[str, ...]


class ProfileExplorer:
    """Explore one profile from its start state and collect the problems found on the way.

    ``tree`` holds the start state; the explorer writes a state into it to run
    functions there and puts the start values back afterwards.
    """

    def __init__(
        self,
        profile: ProfileConfig,
        *,
        tree: StateTree,
        functions: FunctionRegistry,
        records: Sequence[Record],
        callbacks: Sequence[Callback],
        rules: ActionRules,
        depth: int,
    ) -> None:
        self._profile = profile
        self._depth = depth
        self._tree = tree
        self._functions = functions
        self._records = list(records)
        self._callbacks = list(callbacks)
        self._rules = rules
        self._variables: dict[StatePath, Variable] = {**tree.declarations(SHARED), **tree.declarations(PROFILE)}
        self._start_values: dict[StatePath, DataValue] = {path: tree.get(path) for path in self._variables}
        self._start_units: dict[Unit, Frozen] = {}
        self._start_units_by_variable: dict[StatePath, tuple[Unit, ...]] = {}
        for path, value in self._start_values.items():
            units = self._units_of(path, value)
            self._start_units.update(units)
            self._start_units_by_variable[path] = tuple(units)
        self._unit_variables: dict[Unit, StatePath] = {}
        self._record_readers: dict[Unit, set[int]] = {}
        self._callback_readers: dict[Unit, set[int]] = {}
        self._checked: set[Memo] = set()
        self._results: dict[Memo, int | None] = {}
        # Every distinct list of state changes a callback returned, by number, and what applying it touches.
        self._change_ids: dict[tuple[tuple[StatePath, Frozen], ...], int] = {}
        self._changes: list[tuple[tuple[StatePath, Frozen], ...]] = []
        self._writes: list[_Writes] = []
        self._transitions: dict[Memo, tuple[State, tuple[str, ...]]] = {}
        self._parents: dict[State, tuple[State, int, int]] = {}
        self._problems: dict[tuple[str, str], Problem] = {}
        self.states = 0

    @property
    def problems(self) -> list[Problem]:
        return list(self._problems.values())

    def run(self) -> None:
        """Explore every state within ``depth`` changed units of the start, breadth first."""

        start: State = ()
        start_results: list[int | None] = []
        for index in range(len(self._records)):
            self._checked.add((index, ()))
            self._check_record(index, start)
        for index in range(len(self._callbacks)):
            result = self._call(index, start)
            self._results[(index, ())] = result
            start_results.append(result)
        producers: dict[int, list[int]] = {}
        for index, result in enumerate(start_results):
            if result is not None:
                producers.setdefault(result, []).append(index)
        start_sources = {changes: indexes[0] for changes, indexes in producers.items()}
        self.states = 1
        queue: deque[State] = deque()
        seen: set[State] = {start}
        self._follow(start, start_sources, queue, seen)
        while queue:
            state = queue.popleft()
            self.states += 1
            changed = self._run_affected(state, start_results)
            sources = start_sources
            if changed:
                sources = dict(start_sources)
                for index, result in changed.items():
                    before = start_results[index]
                    if before is not None and sources.get(before) == index:
                        other = next((other for other in producers[before] if other not in changed), None)
                        if other is None:
                            del sources[before]
                        else:
                            sources[before] = other
                for index, result in changed.items():
                    if result is not None:
                        sources.setdefault(result, index)
            self._follow(state, sources, queue, seen)

    def _run_affected(self, state: State, start_results: list[int | None]) -> dict[int, int | None]:
        """Check the records and run the callbacks that read a unit ``state`` changed.

        Returns the callbacks whose changes differ from the start state's, with their changes here.
        """

        records: set[int] = set()
        callbacks: set[int] = set()
        for unit, _value in state:
            found_records, found_callbacks = self._readers(unit)
            records |= found_records
            callbacks |= found_callbacks
        written = False
        changed: dict[int, int | None] = {}
        try:
            for index in records:
                memo = (index, self._relevant(state, index, self._record_readers))
                if memo in self._checked:
                    continue
                self._checked.add(memo)
                written = written or self._write(state)
                self._check_record(index, state)
            for index in callbacks:
                memo = (index, self._relevant(state, index, self._callback_readers))
                result = self._results.get(memo, -1)
                if result == -1:
                    written = written or self._write(state)
                    result = self._results[memo] = self._call(index, state)
                if result != start_results[index]:
                    changed[index] = result
        finally:
            if written:
                self._restore(state)
        return changed

    def _follow(self, state: State, sources: Mapping[int, int], queue: deque[State], seen: set[State]) -> None:
        """Apply every distinct list of changes some callback returns in ``state``, and queue the new states."""

        for changes, index in sources.items():
            after, failures = self._apply(changes, state)
            for message in failures:
                self._report(self._callbacks[index].source, message, state, (index, changes))
            if len(after) > self._depth or after in seen:
                continue
            seen.add(after)
            self._parents[after] = (state, index, changes)
            queue.append(after)

    def _check_record(self, index: int, state: State) -> None:
        record = self._records[index]
        recorder = ReadRecorder()

        def resolve(function: Callable[..., object], path: str) -> object:
            ref = self._functions.register(function)
            try:
                return evaluate_binding(self._functions, ref, self._tree, recorder)
            except Exception as exc:
                raise BindingFailed(ref, path, exc) from exc

        try:
            record.decode(resolve)
        except ConfigError as exc:
            self._report(record.source, str(exc), state)
        except Exception as exc:
            self._report(record.source, f"{type(exc).__name__}: {exc}", state)
        finally:
            self._learn(record.reads, recorder.paths, index, self._record_readers)

    def _call(self, index: int, state: State) -> int | None:
        """Run the callbacks of one event in the tree's current state; return the number of the changes they ask for."""

        callback = self._callbacks[index]
        sets: list[tuple[StatePath, Frozen]] = []
        for ref, source in callback.calls:
            recorder = ReadRecorder()
            try:
                actions = call_callback(self._functions, ref, self._tree, copy_data_map(callback.arguments), recorder)
            except Exception as exc:
                self._report(source, f"{type(exc).__name__}: {exc}", state)
                continue
            finally:
                self._learn(callback.reads, recorder.paths, index, self._callback_readers)
            for action in actions:
                for message in self._rules.problems(action):
                    self._report(source, message, state)
                if action.action == STATE_SET:
                    try:
                        arguments: StateSetArguments = decode_state_set(action.arguments)
                    except Exception:
                        continue
                    sets.append((arguments.path, freeze(arguments.value)))
                elif action.action == STATE_APPEND:
                    problem = self._append_problem(action.arguments)
                    if problem is not None:
                        self._report(source, problem, state)
        if not sets:
            return None
        changes = tuple(sets)
        number = self._change_ids.get(changes)
        if number is None:
            number = self._change_ids[changes] = len(self._changes)
            self._changes.append(changes)
            self._writes.append(self._plan(changes))
        return number

    def _append_problem(self, arguments: DataMap) -> str | None:
        """Why a ``state.append`` would fail in the tree's current state, or ``None`` when it would land."""

        try:
            path = decode_state_append(arguments).path
        except Exception:
            return None  # The action rules already report arguments that do not decode.
        try:
            if self._tree.owner(path) == ENGINE:
                return f"state.append {path_text(path)}: profiles cannot set engine-observed state"
            before = self._tree.get(path)
            self._tree.append(path, arguments["value"])
            self._tree.set(path, before)
        except Exception as exc:
            return f"state.append {path_text(path)}: {exc}"
        return None

    def _apply(self, changes: int, state: State) -> tuple[State, tuple[str, ...]]:
        """The state after list ``changes`` applies in ``state``, and why any of its changes failed."""

        writes = self._writes[changes]
        variables = writes.variables
        kept: State = ()
        before: State = ()
        for item in state:
            if self._variable_of(item[0]) in variables:
                before += (item,)
            else:
                kept += (item,)
        memo = (changes, before)
        result = self._transitions.get(memo)
        if result is None:
            result = self._transitions[memo] = self._transition(writes, before)
        touched, failures = result
        if not kept:
            return touched, failures
        if not touched:
            return kept, failures
        return tuple(sorted(kept + touched, key=_unit_order)), failures

    def _transition(self, writes: _Writes, before: State) -> tuple[State, tuple[str, ...]]:
        """Apply ``writes`` in the start state changed by ``before``; return the touched units that differ from the start."""

        written = self._write(before)
        failures = list(writes.failures)
        touched: dict[Unit, Frozen] = {}
        try:
            for path, value in writes.sets:
                try:
                    self._tree.set(path, thaw(value))
                except Exception as exc:
                    failures.append(f"state.set {path_text(path)}: {exc}")
            for variable in writes.variables:
                units = self._units_of(variable, self._tree.get(variable))
                for unit in self._start_units_by_variable[variable]:
                    units.setdefault(unit, None)
                touched.update({unit: value for unit, value in units.items() if self._start_units.get(unit) != value})
        finally:
            if written:
                self._restore(before)
            for variable in writes.variables:
                self._tree.set(variable, self._start_values[variable])
        return tuple(sorted(touched.items(), key=_unit_order)), tuple(failures)

    def _plan(self, changes: tuple[tuple[StatePath, Frozen], ...]) -> _Writes:
        variables: set[StatePath] = set()
        sets: list[tuple[StatePath, Frozen]] = []
        failures: list[str] = []
        for path, value in changes:
            try:
                variable = self._tree.slot(path).variable
            except Exception as exc:
                failures.append(f"state.set {path_text(path)}: {exc}")
                continue
            if self._tree.owner(path) == ENGINE:
                failures.append(f"state.set {path_text(path)}: profiles cannot set engine-observed state")
                continue
            variables.add(variable)
            sets.append((path, value))
        return _Writes(frozenset(variables), tuple(sets), tuple(failures))

    def _write(self, state: State) -> bool:
        """Write ``state``'s units into the tree; return whether anything was written, for ``_restore``."""

        for unit, value in state:
            self._tree.set(unit, thaw(value))
        return bool(state)

    def _restore(self, state: State) -> None:
        for variable in {self._variable_of(unit) for unit, _value in state}:
            self._tree.set(variable, self._start_values[variable])

    def _units_of(self, variable: StatePath, value: DataValue) -> dict[Unit, Frozen]:
        if isinstance(self._variables[variable].type, MapOf):
            assert isinstance(value, dict)
            return {(*variable, name): freeze(item) for name, item in value.items()}
        return {variable: freeze(value)}

    def _variable_of(self, unit: Unit) -> StatePath:
        variable = self._unit_variables.get(unit)
        if variable is None:
            variable = self._unit_variables[unit] = self._tree.slot(unit).variable
        return variable

    def _readers(self, unit: Unit) -> tuple[set[int], set[int]]:
        records = self._record_readers.get(unit)
        if records is None:
            records = self._record_readers[unit] = _overlapping(unit, (record.reads for record in self._records))
        callbacks = self._callback_readers.get(unit)
        if callbacks is None:
            callbacks = self._callback_readers[unit] = _overlapping(unit, (callback.reads for callback in self._callbacks))
        return records, callbacks

    def _relevant(self, state: State, index: int, readers: dict[Unit, set[int]]) -> State:
        """The units of ``state`` that function ``index`` has ever read, which decide what it returns there."""

        return tuple(item for item in state if index in readers[item[0]])

    def _learn(self, known: set[StatePath], read: Iterable[StatePath], index: int, readers: dict[Unit, set[int]]) -> None:
        """Add newly read paths to a function's reads and to every cached unit they overlap."""

        new = [path for path in read if path not in known]
        if not new:
            return
        known.update(new)
        for unit, indexes in readers.items():
            if index not in indexes and any(paths_overlap(unit, path) for path in new):
                indexes.add(index)

    def _report(self, source: str, message: str, state: State, step: tuple[int, int] | None = None) -> None:
        if (source, message) in self._problems:
            return
        trail = self._trail(state) + ((self._step(*step),) if step is not None else ())
        self._problems[(source, message)] = Problem(self._profile.id, source, message, trail)

    def _trail(self, state: State) -> tuple[Step, ...]:
        steps: list[Step] = []
        while state in self._parents:
            state, index, changes = self._parents[state]
            steps.append(self._step(index, changes))
        return tuple(reversed(steps))

    def _step(self, index: int, changes: int) -> Step:
        callback = self._callbacks[index]
        shown = tuple((path_text(path), thaw(value)) for path, value in self._changes[changes])
        return Step(callback.source, callback.event, callback.arguments, shown)


def profile_items(
    profile: ProfileConfig,
    *,
    callback_fields: Callable[[str], Mapping[str, str]],
    samples: Callable[[str], list[DataMap]],
) -> tuple[list[Record], list[Callback]]:
    """Every binding record and callback of ``profile``, named by config path.

    ``callback_fields`` maps a node kind to its callback fields by event, and
    ``samples`` lists every event a profile handler of that event can receive.
    """

    base = profile_path(profile.id)
    records = [Record(f"{base}.theme", profile.theme.decode)]
    records.extend(Record(f"{base}.windows[{index}]", window.values.decode) for index, window in enumerate(profile.windows))
    records.extend(Record(node.path, node.values.decode) for node in profile.nodes())
    records.extend(
        Record(f"{base}.attachments[{index}]", attachment.values.decode)
        for index, attachment in enumerate(profile.attachments)
    )
    callbacks: list[Callback] = []
    for node in profile.nodes():
        fields = callback_fields(node.kind)
        for event, ref in node.callbacks.items():
            source = f"{node.path}.{fields.get(event, event)}"
            callbacks.append(Callback(((ref, source),), source, event, {"node": node.id}))
    for event, refs in profile.on.items():
        calls = tuple((ref, f"{base}.on.{event}[{index}]") for index, ref in enumerate(refs))
        for arguments in samples(event):
            callbacks.append(Callback(calls, f"{base}.on.{event}", event, arguments))
    return records, callbacks


def _overlapping(unit: Unit, reads: Iterable[set[StatePath]]) -> set[int]:
    return {index for index, paths in enumerate(reads) if any(paths_overlap(unit, path) for path in paths)}


def _unit_order(item: tuple[Unit, Frozen]) -> Unit:
    return item[0]


def freeze(value: DataValue) -> Frozen:
    """A hashable copy of plain data that keeps ``True`` apart from ``1``, as Lua does."""

    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, list):
        return ("list", tuple(freeze(item) for item in value))
    if isinstance(value, dict):
        return ("map", tuple(sorted((key, freeze(item)) for key, item in value.items())))
    return value


def thaw(value: Frozen) -> DataValue:
    """The plain data ``freeze`` made ``value`` from."""

    if isinstance(value, tuple):
        tag, content = value
        if tag == "bool":
            return content
        if tag == "list":
            return [thaw(item) for item in content]
        return {key: thaw(item) for key, item in content}
    return value  # type: ignore[return-value]
