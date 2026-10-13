"""Check a root config by exploring the states its callbacks reach, without starting the app.

``check_config`` decodes the root config as the app does, then explores every
profile from the state it starts in, as many units deep as the profile's
``check_depth`` or the depth the caller gives (``explorer`` says what a unit
is), and reports
every binding that fails or returns an invalid value, every callback that
fails, and every action a callback returns that could not run. Key and
modifier names are checked against axidev_io's official spelling, so the
check fails when axidev_io cannot be imported.
"""

from __future__ import annotations

import time
from collections.abc import Mapping

from ..config.profile import ProfileConfig, RootConfig
from ..config.reader import ConfigError
from ..messages import DataMap
from ..runtime.app_messages import APP_ACTION_DECODERS
from ..runtime.dispatcher import Dispatcher
from ..runtime.engine import Engine, build_engine
from ..runtime.event_fields import event_samples
from ..runtime.profile_runtime import ENGINE, PROFILE, SHARED
from ..runtime.state import StateTree
from ..services.keyboard.names import KeyNames, KeyNamesUnavailable
from .actions import ActionRules
from .explorer import ProfileExplorer, profile_items
from .report import CheckReport, Problem, ProfileSummary, Step, format_report

__all__ = ["CheckReport", "Problem", "ProfileSummary", "Step", "check_config", "format_report"]


class _NoEffects:
    """Keyboard and process effects for an engine that never runs an action."""

    def __getattr__(self, name: str) -> object:
        raise RuntimeError(f"The config check never runs actions ({name})")


def check_config(data: object, depth: int | None = None) -> CheckReport:
    """Decode ``data`` as a root config and explore every profile in it, ``depth`` units deep when given."""

    started = time.perf_counter()
    try:
        names = KeyNames.load()
    except KeyNamesUnavailable as exc:
        return _failed(Problem(None, "axidev_io", f"{exc}; key names cannot be checked"), started)
    engine = build_engine(Dispatcher(), keyboard=_NoEffects(), processes=_NoEffects())  # type: ignore[arg-type]
    try:
        root = engine.decoder().decode_config(data)
    except ConfigError as exc:
        return _failed(Problem(None, "config", str(exc)), started)
    problems: list[Problem] = []
    summaries: list[ProfileSummary] = []
    for profile in root.profiles.values():
        profile_depth = profile.check_depth if depth is None else depth
        explorer = _explorer(engine, root, profile, names, profile_depth)
        explorer.run()
        problems.extend(explorer.problems)
        summaries.append(ProfileSummary(profile.id, profile_depth, explorer.states))
    return CheckReport(tuple(problems), tuple(summaries), time.perf_counter() - started)


def _explorer(engine: Engine, root: RootConfig, profile: ProfileConfig, names: KeyNames, depth: int) -> ProfileExplorer:
    tree = StateTree()
    tree.declare(engine.profile.state.declarations(ENGINE), ENGINE)
    tree.declare(profile.shared, SHARED)
    tree.declare(profile.state, PROFILE)
    # What the engine writes when a profile starts, so the check starts where the profile does.
    tree.set(("app", "profiles"), list(root.profiles))
    tree.set(("app", "profile"), profile.id)
    windows = [window.id for window in profile.windows]
    nodes = [node.id for node in profile.nodes()]
    dispatcher = engine.dispatcher

    def callback_fields(kind: str) -> Mapping[str, str]:
        return {event: field for field, event in engine.nodes[kind].callbacks.items()}

    def samples(event: str) -> list[DataMap]:
        decoder = dispatcher.event_decoder(event)
        assert decoder is not None, f"profile handles unregistered event {event!r}"
        return event_samples(decoder, windows=windows, nodes=nodes)

    records, callbacks = profile_items(profile, callback_fields=callback_fields, samples=samples)
    rules = ActionRules(
        decoder_for=lambda name: APP_ACTION_DECODERS.get(name) or dispatcher.action_decoder(name),
        names=names,
        windows=windows,
        profiles=root.profiles,
    )
    return ProfileExplorer(
        profile,
        tree=tree,
        functions=engine.functions,
        records=records,
        callbacks=callbacks,
        rules=rules,
        depth=depth,
    )


def _failed(problem: Problem, started: float) -> CheckReport:
    return CheckReport((problem,), (), time.perf_counter() - started)
