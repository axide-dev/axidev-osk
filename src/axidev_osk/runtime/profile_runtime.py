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
from ..messages import DataMap, DataValue, MessageResult, RuntimeAction, RuntimeEvent
from .decoding import data_value, non_empty_string_value, require_keys, string_value
from .dispatcher import Dispatcher, Unsubscribe
from .functions import FunctionRef, FunctionRegistry, call_callback, evaluate_binding
from .state import RUNTIME_STATE_ROOTS, StatePath, StateTree, parse_state_path, paths_overlap

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


def state_set(path: str, value: DataValue) -> RuntimeAction:
    return RuntimeAction(STATE_SET, {"path": path, "value": value})


def state_changed(path: StatePath) -> RuntimeEvent:
    return RuntimeEvent(STATE_CHANGED, {"path": list(path)})


def callback_failed(ref: FunctionRef, kind: str, source: str, error: Exception) -> RuntimeEvent:
    return RuntimeEvent(
        CALLBACK_FAILED,
        {
            "function": ref.id,
            "kind": kind,
            "source": source,
            "exception_type": type(error).__name__,
            "message": str(error),
        },
    )


def decode_state_set(arguments: DataMap) -> StateSetArguments:
    require_keys(arguments, ("path",), optional=("value",))
    return StateSetArguments(
        path=parse_state_path(string_value(arguments, "path")),
        value=data_value(arguments, "value") if "value" in arguments else None,
    )


def decode_state_changed(arguments: DataMap) -> StateChangedArguments:
    require_keys(arguments, ("path",))
    value = arguments["path"]
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError("state.changed path must be a non-empty list of strings")
    return StateChangedArguments(path=tuple(item for item in value if isinstance(item, str)))


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
    """Own profile state and run the profile ``on`` table through the queue."""

    def __init__(self, dispatcher: Dispatcher, functions: FunctionRegistry, state: StateTree) -> None:
        self._dispatcher = dispatcher
        self._functions = functions
        self._state = state
        self._unsubscribes: list[Unsubscribe] = []
        dispatcher.register_action(STATE_SET, decode_state_set, self._handle_state_set)

    @property
    def state(self) -> StateTree:
        return self._state

    def start(self, profile: ProfileConfig) -> None:
        """Load profile state and install its ``on`` callbacks."""

        self.stop()
        unknown = sorted(name for name in profile.on if not self._dispatcher.has_event(name))
        if unknown:
            raise ValueError(f"Profile {profile.id!r} handles unknown events: {', '.join(unknown)}")
        reserved = sorted(name for name in profile.state if name in RUNTIME_STATE_ROOTS)
        if reserved:
            raise ValueError(f"Profile {profile.id!r} state cannot define runtime roots: {', '.join(reserved)}")
        runtime_state = {root: self._state.get((root,)) for root in RUNTIME_STATE_ROOTS}
        self._state.reset(profile.state)
        for root, value in runtime_state.items():
            if value is not None:
                self._state.set((root,), value)
        for event_name, refs in profile.on.items():
            self._unsubscribes.append(
                self._dispatcher.add_raw_event_handler(event_name, self._callback_runner(event_name, refs))
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

        if path[0] not in RUNTIME_STATE_ROOTS:
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

    def _handle_state_set(self, arguments: StateSetArguments) -> MessageResult:
        if arguments.path[0] in RUNTIME_STATE_ROOTS:
            raise ValueError(f"Profiles cannot set runtime state {'.'.join(arguments.path)!r}")
        return [state_changed(arguments.path)] if self._state.set(arguments.path, arguments.value) else []


@dataclass(slots=True)
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
            self._dispatcher.dispatch_event(failure)
        self._bindings.append(binding)

        def unbind() -> None:
            if binding in self._bindings:
                self._bindings.remove(binding)

        return unbind

    def clear(self) -> None:
        self._bindings.clear()

    def _handle_state_changed(self, event: StateChangedArguments) -> MessageResult:
        messages: MessageResult = []
        for binding in tuple(self._bindings):
            if any(paths_overlap(event.path, read) for read in binding.reads):
                failure = self._evaluate(binding)
                if failure is not None:
                    messages.append(failure)
        return messages

    def _evaluate(self, binding: _Binding) -> RuntimeEvent | None:
        try:
            value, reads = evaluate_binding(self._functions, binding.ref, self._state)
        except Exception as exc:
            _logger.exception("Binding %s failed for %s", binding.ref.id, binding.source)
            return callback_failed(binding.ref, "binding", binding.source, exc)
        binding.reads = reads
        if not binding.applied or value != binding.value:
            binding.value = value
            binding.applied = True
            binding.apply(value)
        return None
