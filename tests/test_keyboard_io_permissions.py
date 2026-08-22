from __future__ import annotations

import unittest

from axidev_osk.services.keyboard.io import AxidevIoKeyboardBackend


class KeyboardIoPermissionTests(unittest.TestCase):
    def test_permission_text_uses_axidev_osk_cli(self) -> None:
        backend = AxidevIoKeyboardBackend()

        text = backend.permission_setup_text

        self.assertIn("axidev-osk linux setup-permissions", text)
        self.assertIn("Run that command from a real terminal so sudo can prompt there.", text)
        self.assertIn("sg uinput -c axidev-osk", text)


if __name__ == "__main__":
    unittest.main()
