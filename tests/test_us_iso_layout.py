from __future__ import annotations

from axidev_osk.layouts.us_iso import build_us_iso_layout
from axidev_osk.layouts.us_iso import build_us_iso_layout_config


def test_super_keys_use_platform_neutral_labels_and_io_keys() -> None:
    specs = build_us_iso_layout()
    super_specs = [spec for spec in specs if spec.io_key in {"SuperLeft", "SuperRight"}]

    assert [spec.label for spec in super_specs] == ["Super", "Super"]
    assert [spec.io_key for spec in super_specs] == ["SuperLeft", "SuperRight"]


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
