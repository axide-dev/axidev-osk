from __future__ import annotations

from axidev_osk.config.defaults.us_iso import NAV_START
from axidev_osk.config.defaults.us_iso import build_us_iso_layout
from axidev_osk.config.defaults.us_iso import build_us_iso_layout_config


def test_super_keys_use_platform_neutral_labels_and_io_keys() -> None:
    specs = build_us_iso_layout()
    super_specs = [spec for spec in specs if spec.io_key in {"SuperLeft", "SuperRight"}]

    assert [spec.label for spec in super_specs] == ["Super", "Super"]
    assert [spec.io_key for spec in super_specs] == ["SuperLeft", "SuperRight"]


def test_held_modifiers_opt_into_backend_repeat() -> None:
    held_modifiers = [spec for spec in build_us_iso_layout() if spec.holds_when_latched]

    assert held_modifiers
    assert all(spec.repeats for spec in held_modifiers)


def test_us_iso_layout_config_preserves_key_geometry_and_ids() -> None:
    specs = build_us_iso_layout()
    config = build_us_iso_layout_config()
    grid = config.grids[0]

    assert config.name == "us-iso"
    assert len(grid.components) == len(specs)
    assert [(item.spec.row, item.spec.column, item.spec.width) for item in grid.components] == [
        (spec.row, spec.column, spec.width) for spec in specs
    ]
    assert len({item.id for item in grid.components}) == len(grid.components)


def test_us_iso_layout_config_covers_expected_sections_and_key_sizes() -> None:
    config = build_us_iso_layout_config()
    specs = [item.spec for item in config.grids[0].components]

    assert sorted({spec.row for spec in specs}) == [0, 1, 2, 3, 4, 5]
    assert [spec.label for spec in specs if spec.row == 0] == [
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
    ]
    assert {spec.label for spec in specs if spec.column >= NAV_START} == {
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
    }
    assert next(spec.width for spec in specs if spec.label == "Backspace") == 2.0
    assert next(spec.width for spec in specs if spec.label == "Space") == 6.25
    assert [spec.width for spec in specs if spec.label == "Shift"] == [1.25, 2.75]


def test_us_iso_layout_dense_body_columns_match_main_block_width() -> None:
    config = build_us_iso_layout_config()
    body_specs = [item.spec for item in config.grids[0].components if item.spec.row > 0]
    occupied_columns: set[int] = set()

    for spec in body_specs:
        occupied_columns.update(range(spec.column, spec.column + int(spec.width * 4)))

    assert len([column for column in occupied_columns if column < NAV_START]) == 60
    assert len([column for column in occupied_columns if column >= NAV_START]) == 12


def test_ghost_key_uses_the_near_bracket_slot_and_targets_configured_window() -> None:
    target_window_id = "window:alternate"
    specs = build_us_iso_layout(target_window_id=target_window_id)
    ghost = next(spec for spec in specs if spec.label == "Ghost")

    assert (ghost.row, ghost.column, ghost.width) == (2, 54, 1.0)
    assert ghost.io_key is None
    assert ghost.repeats is False
    assert ghost.action is not None
    assert ghost.action.kind == "toggle-opacity"
    assert ghost.action.target_window_id == target_window_id
    assert ghost.action.opacity == 0.01
