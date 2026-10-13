"""The config check: problems it must find in reachable states, with the trail that reaches them."""

from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from typing import Any
from unittest.mock import patch

from axidev_osk.cli import main
from axidev_osk.config_check import CheckReport, Problem, check_config
from axidev_osk.python_defaults import axidev_osk
from axidev_osk.python_defaults.axidev_osk import std
from axidev_osk.python_defaults.axidev_osk.std import keys, layouts
from axidev_osk.runtime.dispatcher import Dispatcher
from axidev_osk.runtime.engine import build_engine
from axidev_osk.runtime.event_fields import event_samples
from axidev_osk.services.keyboard.names import KeyNamesUnavailable

PAD = "config.profiles.p.windows[0].content"


def _root(children: list[axidev_osk.Map], *, shared: dict[str, Any] | None = None, **profile: Any) -> axidev_osk.Map:
    return axidev_osk.config(
        active_profile="p",
        state=shared,
        profiles={
            "p": axidev_osk.profile(
                windows=[axidev_osk.window(id="pad", title="Pad", content=axidev_osk.box(id="root", children=children))],
                **profile,
            )
        },
    )


def _setter(path: str, value: Any) -> Any:
    return lambda ctx, event: [axidev_osk.state.set(path, value)]


def _problem(report: CheckReport, source: str) -> Problem:
    found = [problem for problem in report.problems if problem.source == source]
    if len(found) != 1:
        raise AssertionError(f"expected one problem at {source}, got {report.problems}")
    return found[0]


class ActionTests(unittest.TestCase):
    def test_a_key_name_that_is_not_the_official_spelling_is_reported_with_the_official_one(self) -> None:
        report = check_config(
            _root([axidev_osk.button(id="escape", label="Esc", on_release=lambda ctx, event: [axidev_osk.keyboard.tap("esc")])])
        )

        problem = _problem(report, f"{PAD}.children[0].on_release")
        self.assertEqual(problem.profile, "p")
        self.assertEqual(problem.message, "Action 'keyboard.tap': Key name 'esc' is not the official spelling; use 'Escape'")
        self.assertEqual(problem.trail, ())

    def test_unknown_windows_profiles_and_modifier_spellings_are_reported(self) -> None:
        report = check_config(
            _root(
                [
                    axidev_osk.button(
                        id="go",
                        label="Go",
                        on_release=lambda ctx, event: [
                            axidev_osk.window.show("nowhere"),
                            axidev_osk.profile.switch("elsewhere"),
                            axidev_osk.keyboard.down("A", mods=["control"]),
                        ],
                    )
                ]
            )
        )

        self.assertEqual(
            sorted(problem.message for problem in report.problems),
            [
                "Action 'keyboard.down': Modifier name 'control' is not the official spelling; use 'Ctrl'",
                "Action 'profile.switch' names profile 'elsewhere', which the config does not have",
                "Action 'window.show' names window 'nowhere', which the profile does not define",
            ],
        )

    def test_a_valid_config_has_no_problems(self) -> None:
        report = check_config(
            _root(
                [axidev_osk.button(id="hide", label="Hide", on_release=lambda ctx, event: [axidev_osk.window.hide("pad")])],
                state={"count": axidev_osk.var("integer", 0)},
            )
        )

        self.assertTrue(report.ok, report.problems)
        self.assertEqual([(summary.profile, summary.states) for summary in report.profiles], [("p", 1)])


class ExplorationTests(unittest.TestCase):
    def test_a_layout_set_to_a_name_the_tables_lack_is_reported_with_the_change_that_led_there(self) -> None:
        layout = lambda state: axidev_osk.read(state, "settings.layout")  # noqa: E731
        report = check_config(
            _root(
                [
                    keys.at("AD01", layouts.LAYOUTS, layout),
                    axidev_osk.button(id="pick", label="Pick", on_release=_setter("settings.layout", "colemak")),
                ],
                shared={"settings": {"layout": axidev_osk.var("string", "us")}},
                state=std.with_state(),
            )
        )

        problem = _problem(report, f"{PAD}.children[0]")
        self.assertIn("KeyError", problem.message)
        self.assertIn("colemak", problem.message)
        self.assertEqual(len(problem.trail), 1)
        self.assertEqual(problem.trail[0].source, f"{PAD}.children[1].on_release")
        self.assertEqual(problem.trail[0].event, "button.released")
        self.assertEqual(problem.trail[0].changes, (("settings.layout", "colemak"),))

    def test_an_append_that_does_not_fit_its_list_is_reported(self) -> None:
        report = check_config(
            _root(
                [axidev_osk.button(id="log", label="Log", on_release=lambda ctx, event: [axidev_osk.state.append("log", 3)])],
                state={"log": axidev_osk.var(axidev_osk.list_of("string"))},
            )
        )

        problem = _problem(report, f"{PAD}.children[0].on_release")
        self.assertIn("state.append log", problem.message)
        self.assertEqual(problem.trail, ())

    def test_the_depth_bounds_how_many_units_may_differ_and_a_given_depth_overrides_the_profile(self) -> None:
        def fails_when(*names: str) -> Any:
            def label(state: Any) -> str:
                if all(axidev_osk.read(state, name) for name in names):
                    raise ValueError("all set")
                return ""

            return label

        state = {name: axidev_osk.var("boolean", False) for name in ("a", "b", "c")}
        buttons = [axidev_osk.button(id=name, label=name, on_release=_setter(name, True)) for name in ("a", "b", "c")]

        def needing(*names: str, **profile: Any) -> axidev_osk.Map:
            return _root([*buttons, axidev_osk.label(id="needs", text=fails_when(*names))], state=state, **profile)

        shallow = check_config(needing("a", "b"))
        two = check_config(needing("a", "b", check_depth=2))
        three = check_config(needing("a", "b", "c", check_depth=2))
        overridden = check_config(needing("a", "b", "c", check_depth=2), depth=3)

        # Without a check_depth, at most one of the three differs from the start: 1 + 3 states.
        self.assertTrue(shallow.ok, shallow.problems)
        self.assertEqual(shallow.states, 4)
        problem = _problem(two, f"{PAD}.children[3]")
        self.assertEqual(sorted(step.changes for step in problem.trail), [(("a", True),), (("b", True),)])
        # At most two of the three: 1 + 3 + 3.
        self.assertTrue(three.ok, three.problems)
        self.assertEqual(three.states, 7)
        self.assertEqual(len(_problem(overridden, f"{PAD}.children[3]").trail), 3)
        self.assertEqual([summary.depth for summary in overridden.profiles], [3])

    def test_profile_handlers_receive_every_marked_value_of_their_event(self) -> None:
        def on_corner(ctx: Any, event: Any) -> list[axidev_osk.Map]:
            if event["corner"] == "bottom_right":
                raise ValueError("no bottom right")
            return []

        report = check_config(
            _root(
                [],
                on={
                    "hot_corner.triggered": on_corner,
                    # Real close requests only ever name windows the profile has.
                    "window.close_requested": lambda ctx, event: [axidev_osk.window.hide(event["window"])],
                },
            )
        )

        self.assertEqual(
            [(problem.source, problem.message) for problem in report.problems],
            [("config.profiles.p.on.hot_corner.triggered[0]", "ValueError: no bottom right")],
        )

    def test_every_registered_event_has_marked_values_its_decoder_accepts(self) -> None:
        dispatcher = Dispatcher()
        build_engine(dispatcher, keyboard=object(), processes=object())  # type: ignore[arg-type]
        for name in sorted(dispatcher.event_names()):
            decoder = dispatcher.event_decoder(name)
            assert decoder is not None
            with self.subTest(event=name):
                samples = event_samples(decoder, windows=["pad"], nodes=["root"])
                self.assertTrue(samples)
                for arguments in samples:
                    decoder(arguments)


class FailureTests(unittest.TestCase):
    def test_the_check_fails_when_axidev_io_cannot_be_imported(self) -> None:
        with patch(
            "axidev_osk.config_check.KeyNames.load",
            side_effect=KeyNamesUnavailable("axidev_io cannot be imported: missing"),
        ):
            report = check_config(_root([]))

        self.assertFalse(report.ok)
        self.assertEqual(report.problems[0].source, "axidev_io")

    def test_a_config_the_decoder_rejects_is_one_problem(self) -> None:
        report = check_config({"active_profile": "missing", "profiles": {}})

        self.assertEqual([problem.source for problem in report.problems], ["config"])


class CommandTests(unittest.TestCase):
    def test_check_prints_each_problem_and_exits_nonzero_only_when_one_is_found(self) -> None:
        broken = _root([axidev_osk.button(id="escape", label="Esc", on_release=lambda ctx, event: [axidev_osk.keyboard.tap("esc")])])
        for config, code in ((broken, 1), (_root([]), 0)):
            output = StringIO()
            with (
                patch("axidev_osk.python_defaults.default_profile.build_default_config", return_value=config),
                redirect_stdout(output),
            ):
                result = main(["check"])

            with self.subTest(code=code):
                self.assertEqual(result, code)
                self.assertIn("states in", output.getvalue())
                self.assertEqual("use 'Escape'" in output.getvalue(), code == 1)

    def test_the_depth_argument_reaches_every_profile(self) -> None:
        state = {"a": axidev_osk.var("boolean", False), "b": axidev_osk.var("boolean", False)}

        def label(state: Any) -> str:
            if axidev_osk.read(state, "a") and axidev_osk.read(state, "b"):
                raise ValueError("both set")
            return ""

        config = _root(
            [
                axidev_osk.button(id="a", label="a", on_release=_setter("a", True)),
                axidev_osk.button(id="b", label="b", on_release=_setter("b", True)),
                axidev_osk.label(id="both", text=label),
            ],
            state=state,
        )
        for argv, code in ((["check"], 0), (["check", "--depth", "2"], 1)):
            output = StringIO()
            with (
                patch("axidev_osk.python_defaults.default_profile.build_default_config", return_value=config),
                redirect_stdout(output),
            ):
                result = main(argv)

            with self.subTest(argv=argv):
                self.assertEqual(result, code)


if __name__ == "__main__":
    unittest.main()
