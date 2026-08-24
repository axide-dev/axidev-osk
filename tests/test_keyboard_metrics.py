from __future__ import annotations

import unittest

from axidev_osk.components.grid import DEFAULT_KEYBOARD_METRICS


class KeyboardMetricsTests(unittest.TestCase):
    def test_metrics_match_compact_layout_defaults(self) -> None:
        metrics = DEFAULT_KEYBOARD_METRICS

        self.assertEqual(metrics.key_unit_px, 48)
        self.assertEqual(metrics.grid_gap_px, 4)
        self.assertEqual(metrics.span_width(1.0), 48)
        self.assertEqual(metrics.span_width(2.25), 108)
        self.assertEqual(metrics.span_height(1), 48)
        self.assertEqual(metrics.span_height(2), 100)


if __name__ == "__main__":
    unittest.main()
