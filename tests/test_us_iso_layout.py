from __future__ import annotations

import unittest

from axidev_osk.config.defaults import build_default_app_config
from axidev_osk.config.defaults.us_iso import (
    NAV_START,
    build_us_iso_behavior_configs,
    build_us_iso_layout,
    build_us_iso_layout_config,
)
from axidev_osk.runtime.behaviors import decode_keyboard_behavior


def _visual_output_pairs():
    config = build_us_iso_layout_config()
    behaviors = build_us_iso_behavior_configs()
    return [
        (
            component.visual,
            decode_keyboard_behavior(behaviors[component.id].arguments).output,
        )
        for component in config.grids[0].components
        if component.id in behaviors
    ]


class UsIsoLayoutTests(unittest.TestCase):
    def test_super_keys_use_platform_neutral_labels_and_outputs(self) -> None:
        pairs = [
            (visual, output)
            for visual, output in _visual_output_pairs()
            if output.output_key in {"SuperLeft", "SuperRight"}
        ]

        self.assertEqual([visual.label for visual, _output in pairs], ["Super", "Super"])
        self.assertEqual(
            [output.output_key for _visual, output in pairs],
            ["SuperLeft", "SuperRight"],
        )

    def test_held_modifiers_opt_into_backend_repeat(self) -> None:
        held_keys = {
            "ShiftLeft",
            "ShiftRight",
            "CtrlLeft",
            "CtrlRight",
            "SuperLeft",
            "SuperRight",
            "AltLeft",
            "AltRight",
        }
        outputs = [
            output
            for _visual, output in _visual_output_pairs()
            if output.output_key in held_keys
        ]

        self.assertEqual({output.output_key for output in outputs}, held_keys)
        self.assertTrue(all(output.repeats for output in outputs))

    def test_layout_config_preserves_visual_geometry_and_explicit_ids(self) -> None:
        visuals = build_us_iso_layout()
        config = build_us_iso_layout_config()
        grid = config.grids[0]

        self.assertEqual(config.name, "us-iso")
        self.assertEqual(
            [component.visual for component in grid.components],
            visuals,
        )
        self.assertEqual(len({component.id for component in grid.components}), len(visuals))

    def test_layout_covers_expected_sections_and_key_sizes(self) -> None:
        visuals = [
            component.visual
            for component in build_us_iso_layout_config().grids[0].components
        ]

        self.assertEqual(sorted({visual.row for visual in visuals}), [0, 1, 2, 3, 4, 5])
        self.assertEqual(
            [visual.label for visual in visuals if visual.row == 0],
            [
                "Esc",
                "F1",
                "F2",
                "F3",
                "F4",
                "F5",
                "F6",
                "F7",
                "F8",
                "F9",
                "F10",
                "F11",
                "F12",
                "PrtSc",
                "ScrLk",
                "Pause",
            ],
        )
        self.assertEqual(
            {visual.label for visual in visuals if visual.column >= NAV_START},
            {
                "PrtSc",
                "ScrLk",
                "Pause",
                "Ins",
                "Home",
                "PgUp",
                "Del",
                "End",
                "PgDn",
                "↑",
                "←",
                "↓",
                "→",
            },
        )
        self.assertEqual(
            next(visual.width for visual in visuals if visual.label == "Backspace"),
            2.0,
        )
        self.assertEqual(
            next(visual.width for visual in visuals if visual.label == "Space"),
            6.25,
        )
        self.assertEqual(
            [visual.width for visual in visuals if visual.label == "Shift"],
            [1.25, 2.75],
        )

    def test_dense_body_columns_match_main_block_width(self) -> None:
        visuals = [
            component.visual
            for component in build_us_iso_layout_config().grids[0].components
            if component.visual.row > 0
        ]
        occupied_columns: set[int] = set()

        for visual in visuals:
            occupied_columns.update(
                range(visual.column, visual.column + int(visual.width * 4))
            )

        self.assertEqual(
            len([column for column in occupied_columns if column < NAV_START]),
            60,
        )
        self.assertEqual(
            len([column for column in occupied_columns if column >= NAV_START]),
            12,
        )

    def test_ghost_key_is_visual_only_and_has_root_behavior(self) -> None:
        config = build_default_app_config()
        keyboard = config.windows[0].surface.components[0]
        grid = keyboard.layout.grids[0]
        ghost = next(
            component
            for component in grid.components
            if component.visual.label == "Ghost"
        )
        binding = next(
            behavior
            for behavior in config.behaviors
            if behavior.target.segments[-1].id == ghost.id
        )
        actions = binding.default.arguments["pressed_actions"]

        self.assertEqual(
            (ghost.visual.row, ghost.visual.column, ghost.visual.width),
            (2, 54, 1.0),
        )
        self.assertNotIn(ghost.id, build_us_iso_behavior_configs())
        self.assertIsInstance(actions, list)
        self.assertEqual(actions[0]["action"], "window.toggle_opacity")
        self.assertEqual(actions[0]["arguments"]["window_id"], "window:keyboard")
        self.assertEqual(actions[0]["arguments"]["component_id"], ghost.id)


if __name__ == "__main__":
    unittest.main()
