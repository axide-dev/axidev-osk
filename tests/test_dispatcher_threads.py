from __future__ import annotations

import threading
import unittest

from PySide6.QtCore import QCoreApplication, QDeadlineTimer

from axidev_osk.messages import MessageResult, RuntimeEvent
from axidev_osk.runtime.dispatcher import Dispatcher
from axidev_osk.runtime.qt_wake import QtDispatcherWake


def _ping() -> RuntimeEvent:
    return RuntimeEvent("probe.ping", {})


class DispatcherThreadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.wakes = 0
        self.handled_threads: list[int] = []
        self.dispatcher = Dispatcher(wake=self._wake)
        self.dispatcher.register_event("probe.ping", lambda arguments: arguments)
        self.dispatcher.add_event_handler("probe.ping", self._record)

    def _wake(self) -> None:
        self.wakes += 1

    def _record(self, event: object) -> MessageResult:
        del event
        self.handled_threads.append(threading.get_ident())
        return []

    def _send_from_thread(self, count: int) -> None:
        def send() -> None:
            for _ in range(count):
                self.dispatcher.dispatch_event(_ping())

        thread = threading.Thread(target=send)
        thread.start()
        thread.join()

    def test_messages_from_other_threads_wait_for_the_owner_thread(self) -> None:
        self._send_from_thread(3)

        self.assertEqual(self.handled_threads, [])
        self.assertEqual(self.wakes, 3)

        self.dispatcher.process_pending()

        self.assertEqual(self.handled_threads, [threading.get_ident()] * 3)

    def test_owner_drain_also_runs_waiting_messages_after_its_own(self) -> None:
        order: list[str] = []
        self.dispatcher.register_event("probe.owner", lambda arguments: arguments)
        self.dispatcher.add_event_handler("probe.owner", lambda event: order.append("owner") or [])
        self.dispatcher.add_event_handler("probe.ping", lambda event: order.append("other") or [])
        self._send_from_thread(1)

        self.dispatcher.dispatch_event(RuntimeEvent("probe.owner", {}))

        self.assertEqual(order, ["owner", "other"])

    def test_concurrent_senders_never_run_handlers_off_the_owner_thread(self) -> None:
        owner = threading.get_ident()
        sender = threading.Thread(
            target=lambda: [self.dispatcher.dispatch_event(_ping()) for _ in range(2_000)]
        )
        sender.start()
        for _ in range(2_000):
            self.dispatcher.dispatch_event(_ping())
        sender.join()
        self.dispatcher.process_pending()

        self.assertEqual(len(self.handled_threads), 4_000)
        self.assertEqual(set(self.handled_threads), {owner})

    def test_process_pending_rejects_other_threads(self) -> None:
        errors: list[BaseException] = []

        def process() -> None:
            try:
                self.dispatcher.process_pending()
            except RuntimeError as exc:
                errors.append(exc)

        thread = threading.Thread(target=process)
        thread.start()
        thread.join()

        self.assertEqual(len(errors), 1)


class QtDispatcherWakeTests(unittest.TestCase):
    def test_qt_wake_drains_on_the_qt_thread(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        dispatcher = Dispatcher()
        dispatcher.register_event("probe.ping", lambda arguments: arguments)
        handled: list[int] = []
        dispatcher.add_event_handler("probe.ping", lambda event: handled.append(threading.get_ident()) or [])
        wake = QtDispatcherWake(dispatcher)
        self.addCleanup(wake.deleteLater)

        thread = threading.Thread(target=lambda: dispatcher.dispatch_event(_ping()))
        thread.start()
        thread.join()
        deadline = QDeadlineTimer(2_000)
        while not handled and not deadline.hasExpired():
            app.processEvents()

        self.assertEqual(handled, [threading.get_ident()])


if __name__ == "__main__":
    unittest.main()
