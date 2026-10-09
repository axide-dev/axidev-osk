"""Run one profile's functions against the central state tree.

``ProfileRuntime`` owns profile state, the ``state.set`` action, and the
profile ``on`` table. ``BindingTracker`` evaluates node bindings and re-runs
only the bindings whose recorded reads overlap a changed state path.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from ..config.profile import ProfileConfig
from ..config.reader import Bindable
from ..function_registry import FunctionRef, FunctionRegistry
from ..messages import DataMap, DataValue, MessageResult, RuntimeAction, RuntimeEvent, data_equal
from .decoding import (
    non_empty_string_value,
    require_keys,
    string_list_value,
    string_value,
    validated_action,
    validated_event,
)
from .dispatcher import Dispatcher, Unsubscribe
from .functions import call_callback, evaluate_binding
from .state import ReadRecorder, StatePath, StateTree, parse_state_path, paths_overlap

_logger = logging.getLogger(__name__)

STATE_SET = "state.set"
STATE_CHANGED = "state.changed"
CALLBACK_FAILED = "callback.failed"


@dataclass(frozen=True, slots=True)
class StateSetArguments:
    path: StatePath
    value: DataValue


@dataclass(frozen=True, slots=True)
class StateChangedArguments:
    path: StatePath


@dataclass(frozen=True, slots=True)
class CallbackFailedArguments:
    function: str
    kind: str
    source: str
    exception_type: str
    message: str


def state_set(path: str | list[str], value: DataValue) -> RuntimeAction:
    raw_path: DataValue = list(path) if isinstance(path, list) else path
    return validated_action(STATE_SET, {"path": raw_path, "value": value}, decode_state_set)


def state_changed(path: StatePath) -> RuntimeEvent:
    return validated_event(STATE_CHANGED, {"path": list(path)}, decode_state_changed)


def callback_failed(ref: FunctionRef, kind: str, source: str, error: Exception) -> RuntimeEvent:
    return validated_event(
        CALLBACK_FAILED,
        {
            "function": ref.id,
            "kind": kind,
            "source": source,
            "exception_type": type(error).__name__,
            "message": str(error),
        },
        decode_callback_failed,
    )


def decode_state_set(arguments: DataMap) -> StateSetArguments:
    """Decode ``state.set``; ``path`` is ``"a.b"`` or ``["a", "b"]`` for names containing dots."""

    require_keys(arguments, ("path",), optional=("value",))
    if isinstance(arguments["path"], list):
        path = string_list_value(arguments, "path", non_empty=True)
    else:
        path = parse_state_path(string_value(arguments, "path"))
    return StateSetArguments(path=path, value=arguments.get("value"))


def decode_state_changed(arguments: DataMap) -> StateChangedArguments:
    require_keys(arguments, ("path",))
    return StateChangedArguments(path=string_list_value(arguments, "path", non_empty=True))


def decode_callback_failed(arguments: DataMap) -> CallbackFailedArguments:
    require_keys(arguments, ("function", "kind", "source", "exception_type", "message"))
    return CallbackFailedArguments(
        function=non_empty_string_value(arguments, "function"),
        kind=non_empty_string_value(arguments, "kind"),
        source=string_value(arguments, "source"),
        exception_type=string_value(arguments, "exception_type"),
        message=string_value(arguments, "message"),
    )


def register_profile_events(dispatcher: Dispatcher) -> None:
    dispatcher.register_event(STATE_CHANGED, decode_state_changed)
    dispatcher.register_event(CALLBACK_FAILED, decode_callback_failed)


class ProfileRuntime:
    """Own profile state and run the profile ``on`` table through the queue.

    State roots written from observations are declared by their owners with
    ``declare_root``. Profiles can read them but not set them, and they keep
    their values when a profile starts.
    """

    def __init__(self, dispatcher: Dispatcher, functions: FunctionRegistry, state: StateTree) -> None:
        self._dispatcher = dispatcher
        self._functions = functions
        self._state = state
        self._runtime_roots: set[str] = set()
        self._unsubscribes: list[Unsubscribe] = []
        dispatcher.register_action(STATE_SET, decode_state_set, self._handle_state_set)

    def declare_root(self, root: str, initial: DataMap) -> None:
        """Reserve a runtime-owned state root and give it its starting value."""

        if root in self._runtime_roots:
            raise ValueError(f"State root {root!r} is already declared")
        self._runtime_roots.add(root)
        self._state.set((root,), initial)

    @property
    def state(self) -> StateTree:
        return self._state

    def start(self, profile: ProfileConfig) -> None:
        """Load profile state and install its ``on`` callbacks.

        Every check runs before anything changes, so a rejected profile leaves
        the running one untouched.
        """

        path = f"config.profiles.{profile.id}"
        unknown = sorted(name for name in profile.on if not self._dispatcher.has_event(name))
        if unknown:
            raise ValueError(f"{path}.on handles unknown events: {', '.join(unknown)}")
        reserved = sorted(name for name in profile.state if name in self._runtime_roots)
        if reserved:
            raise ValueError(f"{path}.state cannot define runtime roots: {', '.join(reserved)}")
        self.stop()
        runtime_state = {root: self._state.get((root,)) for root in self._runtime_roots}
        self._state.reset(profile.state)
        for root, value in runtime_state.items():
            if value is not None:
                self._state.set((root,), value)
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
            _logger.exception("Profile callback %s failed for %s", ref.id, source)
            return [callback_failed(ref, "callback", source, exc)]

    def set_observed(self, path: StatePath, value: DataValue) -> MessageResult:
        """Write runtime-observed state, which profiles may read but not set."""

        if not path or path[0] not in self._runtime_roots:
            raise ValueError(f"{'.'.join(path)!r} is not a runtime state path")
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
        if arguments.path[0] in self._runtime_roots:
            raise ValueError(f"Profiles cannot set runtime state {'.'.join(arguments.path)!r}")
        return [state_changed(arguments.path)] if self._state.set(arguments.path, arguments.value) else []


@dataclass(slots=True, eq=False)
class _Binding:
    ref: FunctionRef
    source: str
    apply: Callable[[DataValue], None]
    value: DataValue
    reads: frozenset[StatePath]
    applied: bool = False


class BindingTracker:
    """Evaluate bindings and re-run them when the state they read changes."""

    def __init__(self, dispatcher: Dispatcher, functions: FunctionRegistry, state: StateTree) -> None:
        self._dispatcher = dispatcher
        self._functions = functions
        self._state = state
        self._bindings: list[_Binding] = []
        dispatcher.add_event_handler(STATE_CHANGED, self._handle_state_changed)

    def bind(self, value: Bindable, source: str, apply: Callable[[DataValue], None]) -> Unsubscribe:
        """Apply a plain value once, or track and apply a binding function."""

        if not isinstance(value, FunctionRef):
            apply(value)
            return lambda: None
        binding = _Binding(ref=value, source=source, apply=apply, value=None, reads=frozenset())
        failure = self._evaluate(binding)
        if failure is not None:
            self._dispatcher.dispatch(failure)
        self._bindings.append(binding)

        def unbind() -> None:
            if binding in self._bindings:
                self._bindings.remove(binding)

        return unbind

    def _handle_state_changed(self, event: StateChangedArguments) -> MessageResult:
        messages: MessageResult = []
        for binding in tuple(self._bindings):
            if any(paths_overlap(event.path, read) for read in binding.reads):
                failure = self._evaluate(binding)
                if failure is not None:
                    messages.append(failure)
        return messages

    def _evaluate(self, binding: _Binding) -> RuntimeEvent | None:
        """Run and apply one binding; a failure keeps the reads made so far so a later change retries it."""

        recorder = ReadRecorder()
        try:
            value = evaluate_binding(self._functions, binding.ref, self._state, recorder)
            if not binding.applied or not data_equal(value, binding.value):
                binding.apply(value)
                binding.value = value
                binding.applied = True
        except Exception as exc:
            _logger.exception("Binding %s failed for %s", binding.ref.id, binding.source)
            return callback_failed(binding.ref, "binding", binding.source, exc)
        finally:
            binding.reads = recorder.paths
        return None
