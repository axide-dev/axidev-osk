from __future__ import annotations

import unittest

from axidev_osk.runtime.identity import key_component_id, prompt_button_id, stable_id, validate_unique_ids


class RuntimeIdentityTests(unittest.TestCase):
    def test_prompt_button_id_is_deterministic(self) -> None:
        self.assertEqual(prompt_button_id("prompt:quit", "accepted"), "prompt:quit:button:accepted")

    def test_duplicate_ids_fail_validation_with_scope_and_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate config IDs in test scope: component:one"):
            validate_unique_ids(("component:one", "component:two", "component:one"), scope="test scope")

    def test_duplicate_ids_are_reported_in_deterministic_order(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate config IDs in test scope: component:a, component:b"):
            validate_unique_ids(
                ("component:b", "component:a", "component:b", "component:a"),
                scope="test scope",
            )

    def test_stable_id_override_returns_explicit_id(self) -> None:
        self.assertEqual(stable_id("parent", "component", "value", stable_override="component:explicit"), "component:explicit")

    def test_key_component_id_collides_for_duplicate_grid_position(self) -> None:
        first = key_component_id(
            "grid:example",
            "key",
            row=1,
            column=2,
            width=1.0,
            height=1,
            key_id="a",
            io_key="A",
            label="A",
        )
        second = key_component_id(
            "grid:example",
            "key",
            row=1,
            column=2,
            width=1.0,
            height=1,
            key_id="b",
            io_key="B",
            label="B",
        )

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
