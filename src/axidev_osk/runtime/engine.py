"""Assemble the profile-facing engine pieces around one dispatcher."""

from __future__ import annotations

from dataclasses import dataclass

from ..nodes import NodeBuilder, NodeKindRegistry, register_builtin_nodes
from .dispatcher import Dispatcher
from .engine_messages import KeyboardEffects, ProcessEffects, install_engine_handlers, register_engine_events
from .functions import FunctionRegistry
from .profile_runtime import BindingTracker, ProfileRuntime, register_profile_events
from .state import StateTree


@dataclass(frozen=True, slots=True)
class Engine:
    """State, profile functions, and bindings shared by every subsystem."""

    functions: FunctionRegistry
    state: StateTree
    profile: ProfileRuntime
    bindings: BindingTracker
    nodes: NodeKindRegistry
    node_builder: NodeBuilder


def build_engine(
    dispatcher: Dispatcher,
    *,
    keyboard: KeyboardEffects,
    processes: ProcessEffects,
) -> Engine:
    """Register engine messages on ``dispatcher`` and return the engine pieces.

    Observation handlers are installed here, before any profile starts, so they
    record state before profile callbacks for the same event run.
    """

    register_profile_events(dispatcher)
    register_engine_events(dispatcher)
    functions = FunctionRegistry()
    state = StateTree()
    profile = ProfileRuntime(dispatcher, functions, state)
    install_engine_handlers(dispatcher, profile_runtime=profile, keyboard=keyboard, processes=processes)
    bindings = BindingTracker(dispatcher, functions, state)
    nodes = NodeKindRegistry()
    register_builtin_nodes(nodes)
    nodes.register_events(dispatcher)
    return Engine(
        functions=functions,
        state=state,
        profile=profile,
        bindings=bindings,
        nodes=nodes,
        node_builder=NodeBuilder(nodes, dispatcher, bindings),
    )
