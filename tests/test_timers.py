from __future__ import annotations

import unittest
from typing import Any

from PySide6.QtTest import QTest

from axidev_osk.messages import RuntimeAction
from axidev_osk.python_defaults import axidev_osk
from support import RecordingBackend, make_test_engine, qt_app, start_test_profile


class TimerTests(unittest.TestCase):
    def setUp(self) -> None:
        qt_app()
        self.engine = make_test_engine(RecordingBackend())
        self.fired: list[str] = []

        def record(ctx: Any, event: Any) -> list[Any]:
            del ctx
            self.fired.append(event["id"])
            return []

        window = {"id": "pad", "title": "Pad", "content": {"kind": "label", "id": "text"}}
        self.root = {"active_profile": "p", "profiles": {"p": {"windows": [window], "on": {"timer.fired": record}}}}
        start_test_profile(self.engine, self.root)

    def _send(self, action: dict[str, Any]) -> None:
        self.engine.dispatcher.dispatch(RuntimeAction(action["action"], action["arguments"]))

    def test_a_timer_fires_once_after_its_delay_and_a_repeating_one_keeps_firing(self) -> None:
        self._send(axidev_osk.timer.start("once", 10))
        self._send(axidev_osk.timer.start("tick", 10, repeat=True))
        QTest.qWait(80)

        self.assertEqual(self.fired.count("once"), 1)
        self.assertGreaterEqual(self.fired.count("tick"), 3)

    def test_cancelling_or_restarting_a_timer_replaces_what_was_scheduled(self) -> None:
        self._send(axidev_osk.timer.start("hide", 30))
        self._send(axidev_osk.timer.cancel("hide"))
        self._send(axidev_osk.timer.cancel("never-started"))
        self._send(axidev_osk.timer.start("hold", 10))
        self._send(axidev_osk.timer.start("hold", 200))
        QTest.qWait(80)

        self.assertEqual(self.fired, [])

    def test_stopping_the_profile_drops_its_timers(self) -> None:
        self._send(axidev_osk.timer.start("tick", 10, repeat=True))
        self.engine.profile.stop()
        start_test_profile(self.engine, self.root)
        QTest.qWait(60)

        self.assertEqual(self.fired, [])


if __name__ == "__main__":
    unittest.main()
