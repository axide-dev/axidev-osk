"""Run one profile's functions against the central state tree.

``ProfileRuntime`` owns the state registry, the ``state.set`` action, and the
profile ``on`` table. ``BindingTracker`` decodes values that may follow state
(node, window, theme, and attachment values) and decodes them again only when a
state path one of their bindings read changes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from typing import Generic, TypeVar

from ..config.profile import ProfileConfig
from ..config.reader import ConfigError, Resolver
from ..config.variables import Variable
from ..function_registry import FunctionRef, FunctionRegistry
from ..messages import DataMap, DataValue, MessageResult, RuntimeAction, RuntimeEvent, data_equal
from .decoding import (
    non_empty_string_value,
    optional_string_value,
    require_keys,
    string_list_value,
    string_value,
    validated_action,
    validated_event,
)
from .dispatcher import Dispatcher, Unsubscribe
from .event_fields import one_of, stand_in
from .functions import call_callback, evaluate_binding
from .hints import CHECK_HINT
from .state import ReadRecorder, StatePath, StateTree, parse_state_path, path_text, paths_overlap

T = TypeVar("T")

ENGINE = "engine"
SHARED = "shared"
PROFILE = "profile"

_logger = logging.getLogger(__name__)

STATE_SET = "state.set"
STATE_APPEND = "state.append"
STATE_CHANGED = "state.changed"
CALLBACK_FAILED = "callback.failed"


@dataclass(frozen=True, slots=True)
class StateSetArguments:
    path: StatePath
    value: DataValue


@dataclass(frozen=True, slots=True)
class StateAppendArguments:
    path: StatePath
    value: DataValue


@dataclass(frozen=True, slots=True)
class StateChangedArguments:
    path: StatePath = stand_in(["app", "profile"])


@dataclass(frozen=True, slots=True)
class CallbackFailedArguments:
    function: str | None = stand_in("fn:1")
    kind: str = one_of("callback", "binding")
    source: str = stand_in("example")
    exception_type: str = stand_in("ValueError")
    message: str = stand_in("example failure")
    hint: str = stand_in(CHECK_HINT)


def state_set(path: str | list[str], value: DataValue) -> RuntimeAction:
    raw_path: DataValue = list(path) if isinstance(path, list) else path
    return validated_action(STATE_SET, {"path": raw_path, "value": value}, decode_state_set)


def state_append(path: str | list[str], value: DataValue) -> RuntimeAction:
    raw_path: DataValue = list(path) if isinstance(path, list) else path
    return validated_action(STATE_APPEND, {"path": raw_path, "value": value}, decode_state_append)


def state_changed(path: StatePath) -> RuntimeEvent:
    return validated_event(STATE_CHANGED, {"path": list(path)}, decode_state_changed)


def callback_failed(ref: FunctionRef | None, kind: str, source: str, error: Exception) -> RuntimeEvent:
    """Report a failed callback or binding; ``ref`` is ``None`` when a binding's result was invalid."""

    return validated_event(
        CALLBACK_FAILED,
        {
            "function": ref.id if ref is not None else None,
            "kind": kind,
            "source": source,
            "exception_type": type(error).__name__,
            "message": str(error),
            "hint": CHECK_HINT,
        },
        decode_callback_failed,
    )


def decode_state_set(arguments: DataMap) -> StateSetArguments:
    """Decode ``state.set``; ``path`` is ``"a.b"`` or ``["a", "b"]`` for names containing dots."""

    require_keys(arguments, ("path",), optional=("value",))
    return StateSetArguments(path=_state_path(arguments), value=arguments.get("value"))


def decode_state_append(arguments: DataMap) -> StateAppendArguments:
    """Decode ``state.append``; the value goes at the end of the declared list at ``path``."""

    require_keys(arguments, ("path", "value"))
    if arguments["value"] is None:
        raise ValueError("state.append needs a value")
    return StateAppendArguments(path=_state_path(arguments), value=arguments["value"])


def _state_path(arguments: DataMap) -> StatePath:
    if isinstance(arguments["path"], list):
        return string_list_value(arguments, "path", non_empty=True)
    return parse_state_path(string_value(arguments, "path"))


def decode_state_changed(arguments: DataMap) -> StateChangedArguments:
    require_keys(arguments, ("path",))
    return StateChangedArguments(path=string_list_value(arguments, "path", non_empty=True))


def decode_callback_failed(arguments: DataMap) -> CallbackFailedArguments:
    require_keys(arguments, ("kind", "source", "exception_type", "message", "hint"), optional=("function",))
    return CallbackFailedArguments(
        function=optional_string_value(arguments, "function") if "function" in arguments else None,
        kind=non_empty_string_value(arguments, "kind"),
        source=string_value(arguments, "source"),
        exception_type=string_value(arguments, "exception_type"),
        message=string_value(arguments, "message"),
        hint=string_value(arguments, "hint"),
    )


def register_profile_events(dispatcher: Dispatcher) -> None:
    dispatcher.register_event(STATE_CHANGED, decode_state_changed)
    dispatcher.register_event(CALLBACK_FAILED, decode_callback_failed)


class ProfileRuntime:
    """Own the state registry and run the profile ``on`` table through the queue.

    The engine declares what it observes with ``declare_observed``; profiles
    read those variables but cannot set them. A profile's shared declarations
    stay installed across profile starts, so their values survive a switch,
    while its own declarations reset every time it starts.
    """

    def __init__(self, dispatcher: Dispatcher, functions: FunctionRegistry, state: StateTree) -> None:
        self._dispatcher = dispatcher
        self._functions = functions
        self._state = state
        self._unsubscribes: list[Unsubscribe] = []
        dispatcher.register_action(STATE_SET, decode_state_set, self._handle_state_set)
        dispatcher.register_action(STATE_APPEND, decode_state_append, self._handle_state_append)

    def declare_observed(self, variables: Mapping[StatePath, Variable]) -> None:
        """Declare variables the engine writes from observations, at their default values."""

        self._state.declare(variables, ENGINE)

    @property
    def state(self) -> StateTree:
        return self._state

    def load_state(self, shared: Mapping[StatePath, Variable], own: Mapping[StatePath, Variable]) -> Resolver:
        """Return a resolver over the default state a profile starts from, for checking it at load.

        Raises ``VariableError`` when the shared or profile declarations overlap
        each other or the engine's.
        """

        tree = StateTree()
        tree.declare(self._state.declarations(ENGINE), ENGINE)
        tree.declare(shared, SHARED)
        tree.declare(own, PROFILE)
        return lambda function, path: _resolve(self._functions, tree, None, function, path)

    def check(self, profile: ProfileConfig, path: str) -> None:
        """Reject a profile that handles unknown events.

        The config decoder runs this on every profile it decodes.
        """

        unknown = sorted(name for name in profile.on if not self._dispatcher.has_event(name))
        if unknown:
            raise ConfigError(f"{path}.on handles unknown events: {', '.join(unknown)}")

    def start(self, profile: ProfileConfig) -> None:
        """Install the profile's declarations and its ``on`` callbacks.

        Starting replaces a running profile: its own variables reset to their
        defaults, and shared variables keep their values unless the shared
        declarations changed. Every top-level state key whose value differs
        afterwards is reported with ``state.changed`` before the new callbacks
        are installed, so values already built decode again.
        """

        self.stop()
        before = self._state.get(())
        if self._state.declarations(SHARED) != dict(profile.shared):
            self._state.undeclare(SHARED)
            self._state.declare(profile.shared, SHARED)
        self._state.undeclare(PROFILE)
        self._state.declare(profile.state, PROFILE)
        after = self._state.get(())
        assert isinstance(before, dict) and isinstance(after, dict)
        changed = sorted(key for key in before.keys() | after.keys() if not data_equal(before.get(key), after.get(key)))
        self._dispatcher.dispatch(*(state_changed((key,)) for key in changed))
        for event_name, refs in profile.on.items():
            self._unsubscribes.append(
                self._dispatcher.add_raw_event_handler(event_name, self._callback_runner(event_name, refs))
            )
        node_callbacks: dict[str, dict[str, FunctionRef]] = {}
        for node in profile.nodes():
            for event_name, ref in node.callbacks.items():
                node_callbacks.setdefault(event_name, {})[node.id] = ref
        for event_name, refs_by_node in node_callbacks.items():
            self._unsubscribes.append(
                self._dispatcher.add_raw_event_handler(event_name, self._node_callback_runner(event_name, refs_by_node))
            )

    def stop(self) -> None:
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes.clear()

    def run_callback(self, ref: FunctionRef, source: str, event: DataMap) -> MessageResult:
        """Run one profile callback, turning failures into ``callback.failed``."""

        try:
            return list(call_callback(self._functions, ref, self._state, event))
        except Exception as exc:
            _logger.exception("Profile callback %s failed for %s. %s", ref.id, source, CHECK_HINT)
            return [callback_failed(ref, "callback", source, exc)]

    def set_observed(self, path: StatePath, value: DataValue) -> MessageResult:
        """Write an engine-observed variable, which profiles may read but not set."""

        if self._state.owner(path) != ENGINE:
            raise ValueError(f"{path_text(path)!r} is not an engine-observed variable")
        return [state_changed(path)] if self._state.set(path, value) else []

    def _callback_runner(
        self,
        event_name: str,
        refs: tuple[FunctionRef, ...],
    ) -> Callable[[DataMap], MessageResult]:
        def run(arguments: DataMap) -> MessageResult:
            messages: MessageResult = []
            for ref in refs:
                messages.extend(self.run_callback(ref, event_name, arguments))
            return messages

        return run

    def _node_callback_runner(
        self,
        event_name: str,
        refs_by_node: dict[str, FunctionRef],
    ) -> Callable[[DataMap], MessageResult]:
        def run(arguments: DataMap) -> MessageResult:
            node_id = arguments.get("node")
            ref = refs_by_node.get(node_id) if isinstance(node_id, str) else None
            if ref is None:
                return []
            return self.run_callback(ref, f"{node_id}.{event_name}", arguments)

        return run

    def _handle_state_set(self, arguments: StateSetArguments) -> MessageResult:
        if self._state.owner(arguments.path) == ENGINE:
            raise ValueError(f"Profiles cannot set engine-observed state {path_text(arguments.path)!r}")
        return [state_changed(arguments.path)] if self._state.set(arguments.path, arguments.value) else []

    def _handle_state_append(self, arguments: StateAppendArguments) -> MessageResult:
        # The list is read when the action runs, so appends queued together all land, in order.
        if self._state.owner(arguments.path) == ENGINE:
            raise ValueError(f"Profiles cannot set engine-observed state {path_text(arguments.path)!r}")
        self._state.append(arguments.path, arguments.value)
        return [state_changed(arguments.path)]


class BindingFailed(ConfigError):
    """A binding function raised while its values were decoded.

    At load this rejects the profile like any other config error; at runtime the
    tracker reports it and keeps the last value.
    """

    def __init__(self, ref: FunctionRef, path: str, error: Exception) -> None:
        super().__init__(f"{path}: {type(error).__name__}: {error}")
        self.ref = ref


def _resolve(
    functions: FunctionRegistry,
    state: StateTree,
    recorder: ReadRecorder | None,
    function: Callable[..., object],
    path: str,
) -> DataValue:
    ref = functions.register(function)
    try:
        return evaluate_binding(functions, ref, state, recorder or ReadRecorder())
    except Exception as exc:
        raise BindingFailed(ref, path, exc) from exc


@dataclass(slots=True, eq=False)
class _Binding(Generic[T]):
    decode: Callable[[Resolver], T]
    source: str
    apply: Callable[[T, T | None], None]
    reads: frozenset[StatePath]
    value: T | None = None
    applied: bool = False


class BindingTracker:
    """Decode values that may follow state and decode them again when the state they read changes.

    The tracker keeps the last values it applied for each binding and hands
    them to ``apply`` with the new ones, so appliers change only what differs.
    """

    def __init__(self, dispatcher: Dispatcher, functions: FunctionRegistry, state: StateTree) -> None:
        self._dispatcher = dispatcher
        self._functions = functions
        self._state = state
        self._bindings: list[_Binding[object]] = []
        dispatcher.add_event_handler(STATE_CHANGED, self._handle_state_changed)

    def bind(
        self,
        decode: Callable[[Resolver], T],
        source: str,
        apply: Callable[[T, T | None], None],
        *,
        fallback: T,
    ) -> Unsubscribe:
        """Decode and apply values now, then again whenever a state path they read changes.

        ``apply`` receives each new value that differs from the last one,
        with the last one, or ``None`` the first time. When the first decode
        fails, ``fallback`` (the values decoded from default state at load) is
        applied instead, and the failure is posted, so binding never runs
        profile handlers before it returns. When the fallback cannot be
        applied either, nothing stays bound and the error is raised.
        """

        binding: _Binding[object] = _Binding(decode=decode, source=source, apply=apply, reads=frozenset())  # type: ignore[arg-type]
        self._bindings.append(binding)

        def unbind() -> None:
            if binding in self._bindings:
                self._bindings.remove(binding)

        failure = self._evaluate(binding)
        if failure is not None:
            if not binding.applied:
                try:
                    apply(fallback, None)
                except Exception:
                    unbind()
                    raise
                binding.value = fallback
                binding.applied = True
            self._dispatcher.post(failure)
        return unbind

    def _handle_state_changed(self, event: StateChangedArguments) -> MessageResult:
        messages: MessageResult = []
        for binding in tuple(self._bindings):
            if any(paths_overlap(event.path, read) for read in binding.reads):
                failure = self._evaluate(binding)
                if failure is not None:
                    messages.append(failure)
        return messages

    def _evaluate(self, binding: _Binding[object]) -> RuntimeEvent | None:
        """Decode and apply one value set; a failure keeps the last value and the reads made so far."""

        recorder = ReadRecorder()
        try:
            value = binding.decode(
                lambda function, path: _resolve(self._functions, self._state, recorder, function, path)
            )
            if not binding.applied or not _same_values(value, binding.value):
                binding.apply(value, binding.value if binding.applied else None)
                binding.value = value
                binding.applied = True
        except BindingFailed as exc:
            _logger.exception("Binding %s failed for %s. %s", exc.ref.id, binding.source, CHECK_HINT)
            return callback_failed(exc.ref, "binding", binding.source, exc)
        except Exception as exc:
            _logger.exception("Values of %s are invalid. %s", binding.source, CHECK_HINT)
            return callback_failed(None, "binding", binding.source, exc)
        finally:
            binding.reads = recorder.paths
        return None


def _same_values(left: object, right: object) -> bool:
    """Compare decoded values field by field, with plain data compared the way Lua does."""

    if is_dataclass(left) and not isinstance(left, type):
        return type(left) is type(right) and all(
            _same_values(getattr(left, item.name), getattr(right, item.name)) for item in fields(left)
        )
    if isinstance(left, tuple) and isinstance(right, tuple):
        return len(left) == len(right) and all(_same_values(a, b) for a, b in zip(left, right))
    if isinstance(left, Mapping) and isinstance(right, Mapping) and not isinstance(left, dict):
        return left.keys() == right.keys() and all(_same_values(left[key], right[key]) for key in left)
    return data_equal(left, right)  # type: ignore[arg-type]
