"""Assemble the profile-facing engine pieces around one dispatcher."""

from __future__ import annotations

from dataclasses import dataclass

from ..attachments import AttachmentKindRegistry, register_builtin_attachments
from ..config.profile import ConfigDecoder
from ..function_registry import FunctionRegistry
from ..nodes import NodeBuilder, NodeKindRegistry, register_builtin_nodes
from .app_messages import register_app_events
from .dispatcher import Dispatcher
from .engine_messages import KeyboardEffects, ProcessEffects, install_engine_handlers, register_engine_events
from .profile_runtime import BindingTracker, ProfileRuntime, register_profile_events
from .state import StateTree


@dataclass(frozen=True, slots=True)
class Engine:
    """State, profile functions, and bindings shared by every subsystem."""

    functions: FunctionRegistry
    profile: ProfileRuntime
    bindings: BindingTracker
    nodes: NodeKindRegistry
    node_builder: NodeBuilder
    attachments: AttachmentKindRegistry

    def decoder(self) -> ConfigDecoder:
        """Return a decoder for root configs using this engine's registered kinds."""

        return ConfigDecoder(node_kinds=self.nodes, attachment_kinds=self.attachments, functions=self.functions)


def build_engine(
    dispatcher: Dispatcher,
    *,
    keyboard: KeyboardEffects,
    processes: ProcessEffects,
) -> Engine:
    """Register every built-in event on ``dispatcher`` and return the engine pieces.

    This is the one place that registers event names, for the app and for
    tests alike. Observation handlers are installed here, before any profile
    starts, so they record state before profile callbacks for the same event
    run. The application registers the actions that need objects it owns.
    """

    register_profile_events(dispatcher)
    register_engine_events(dispatcher)
    register_app_events(dispatcher)
    functions = FunctionRegistry()
    profile = ProfileRuntime(dispatcher, functions, StateTree())
    install_engine_handlers(dispatcher, profile_runtime=profile, keyboard=keyboard, processes=processes)
    bindings = BindingTracker(dispatcher, functions, profile.state)
    nodes = NodeKindRegistry(dispatcher)
    register_builtin_nodes(nodes)
    attachments = AttachmentKindRegistry()
    register_builtin_attachments(attachments)
    return Engine(
        functions=functions,
        profile=profile,
        bindings=bindings,
        nodes=nodes,
        node_builder=NodeBuilder(nodes, dispatcher, bindings),
        attachments=attachments,
    )
