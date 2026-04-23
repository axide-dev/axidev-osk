from __future__ import annotations

from axidev_osk.components.keyboard_metrics import DEFAULT_KEYBOARD_METRICS


def test_keyboard_metrics_match_compact_layout_defaults() -> None:
    metrics = DEFAULT_KEYBOARD_METRICS

    assert metrics.key_unit_px == 48
    assert metrics.grid_gap_px == 4
    assert metrics.span_width(1.0) == 48
    assert metrics.span_width(2.25) == 108
    assert metrics.span_height(1) == 48
    assert metrics.span_height(2) == 100
