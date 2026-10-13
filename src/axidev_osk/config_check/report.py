"""What a config check found: each problem with the trail that leads to it, and how far it explored."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..messages import DataMap, DataValue


@dataclass(frozen=True, slots=True)
class Step:
    """One callback run on the way to a state, and the state it set."""

    source: str
    """Config path of the callback, such as ``config.profiles.default.windows[0].content.on_release``."""
    event: str
    arguments: DataMap
    changes: tuple[tuple[str, DataValue], ...]
    """Each ``state.set`` the callback returned, as ``(path, value)``; ``None`` resets or removes."""


@dataclass(frozen=True, slots=True)
class Problem:
    """One failure, reported once, with the shortest trail of steps from the start state that reaches it."""

    profile: str | None
    """The profile it was found in, or ``None`` when the config as a whole cannot be checked."""
    source: str
    """Config path of the binding record or callback that failed."""
    message: str
    trail: tuple[Step, ...] = ()


@dataclass(frozen=True, slots=True)
class ProfileSummary:
    profile: str
    depth: int
    states: int


@dataclass(frozen=True, slots=True)
class CheckReport:
    problems: tuple[Problem, ...]
    profiles: tuple[ProfileSummary, ...]
    seconds: float

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def states(self) -> int:
        return sum(summary.states for summary in self.profiles)


def format_report(report: CheckReport) -> str:
    """The report as plain text: every problem with its trail, then what was explored."""

    lines: list[str] = []
    for problem in report.problems:
        where = f"profile {problem.profile!r}" if problem.profile is not None else "config"
        lines.append(f"Problem in {where}: {problem.source}")
        lines.append(f"  {problem.message}")
        if problem.trail:
            lines.append("  Reached from the start state by:")
            for index, step in enumerate(problem.trail, start=1):
                changes = ", ".join(f"{path} = {_show(value)}" for path, value in step.changes)
                lines.append(f"    {index}. {step.source} on {step.event} {_show(step.arguments)}: {changes}")
        else:
            lines.append("  Reached in the start state.")
        lines.append("")
    for summary in report.profiles:
        lines.append(f"Profile {summary.profile!r}: {summary.states} states explored, {summary.depth} deep.")
    count = len(report.problems)
    verdict = "no problems" if count == 0 else f"{count} problem{'s' if count != 1 else ''}"
    lines.append(f"Checked {report.states} states in {report.seconds:.2f} s: {verdict}.")
    return "\n".join(lines)


def _show(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)
