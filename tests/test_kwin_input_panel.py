from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from axidev_osk.platform import kwin_input_panel


class KWinInputPanelTests(unittest.TestCase):
    def tearDown(self) -> None:
        kwin_input_panel._clients.clear()

    def test_select_output_matches_qt_screen_name(self) -> None:
        first = kwin_input_panel._Output(10, 100, "HDMI-A-1")
        selected = kwin_input_panel._Output(11, 101, "DP-1")

        self.assertIs(
            kwin_input_panel._select_output((first, selected), "DP-1"),
            selected,
        )

    def test_select_output_rejects_unknown_qt_screen(self) -> None:
        output = kwin_input_panel._Output(10, 100, "HDMI-A-1")

        with self.assertRaisesRegex(
            kwin_input_panel.KWinInputPanelError,
            "available outputs: HDMI-A-1",
        ):
            kwin_input_panel._select_output((output,), "DP-1")

    def test_client_is_reused_for_rebuilt_windows_on_one_display(self) -> None:
        library = Mock()
        client = Mock()
        with patch.object(kwin_input_panel, "_InputPanelClient", return_value=client) as build:
            first = kwin_input_panel._client_for_display(library, 42)
            second = kwin_input_panel._client_for_display(library, 42)

        self.assertIs(first, client)
        self.assertIs(second, client)
        build.assert_called_once_with(library, 42)

    def test_attachment_releases_proxy_once(self) -> None:
        client = Mock()
        attachment = kwin_input_panel.KWinInputPanelAttachment(client, 99)

        attachment.close()
        attachment.close()

        client.destroy_proxy.assert_called_once_with(99)

    def test_failed_client_initialization_removes_listener_proxies(self) -> None:
        library = Mock()
        library.wl_proxy_marshal_flags.return_value = 77
        library.wl_proxy_add_listener.return_value = 0
        protocol = SimpleNamespace(registry=kwin_input_panel._WlInterface())

        with (
            patch.object(kwin_input_panel, "_Protocol", return_value=protocol),
            patch.object(
                kwin_input_panel._InputPanelClient,
                "_roundtrip",
                side_effect=kwin_input_panel.KWinInputPanelError("roundtrip failed"),
            ),
            self.assertRaisesRegex(
                kwin_input_panel.KWinInputPanelError,
                "roundtrip failed",
            ),
        ):
            kwin_input_panel._InputPanelClient(library, 42)

        destroyed = [call.args[0].value for call in library.wl_proxy_destroy.call_args_list]
        self.assertEqual(destroyed, [77])


if __name__ == "__main__":
    unittest.main()
