from __future__ import annotations

from axidev_osk.layouts.us_iso import build_us_iso_layout


def test_super_keys_use_platform_neutral_labels_and_io_keys() -> None:
    specs = build_us_iso_layout()
    super_specs = [spec for spec in specs if spec.io_key in {"SuperLeft", "SuperRight"}]

    assert [spec.label for spec in super_specs] == ["Super", "Super"]
    assert [spec.io_key for spec in super_specs] == ["SuperLeft", "SuperRight"]
