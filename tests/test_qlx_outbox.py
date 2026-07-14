import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from qlx_outbox import EventOutbox


class OutboxTests(unittest.TestCase):
    def make_outbox(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return EventOutbox(os.path.join(temp_dir.name, "agent_outbox.db"))

    def test_enqueue_adds_idempotency_key_and_pending_event(self):
        outbox = self.make_outbox()
        event_id = outbox.enqueue({"machine": "inbat", "path": "D:\\job.tif", "event_type": "EXPORT"})

        events = outbox.next_pending()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, event_id)
        self.assertEqual(events[0].payload["event_id"], event_id)
        self.assertEqual(events[0].payload["idempotency_key"], event_id)
        self.assertEqual(outbox.pending_count(), 1)

    def test_mark_sent_removes_event_from_pending_queue(self):
        outbox = self.make_outbox()
        event_id = outbox.enqueue({"machine": "cnc", "path": "D:\\CNC\\job.tap", "event_type": "DONE"})

        outbox.mark_sent(event_id)

        self.assertEqual(outbox.next_pending(), [])
        self.assertEqual(outbox.pending_count(), 0)

    def test_failed_event_retries_after_backoff(self):
        outbox = self.make_outbox()
        event_id = outbox.enqueue({"machine": "indecal", "path": "job.prn", "event_type": "RIP"})

        outbox.mark_failed(event_id, "network down", base_delay_seconds=10)

        self.assertEqual(outbox.next_pending(now_ts=0), [])
        self.assertEqual(len(outbox.next_pending(now_ts=10**10)), 1)

    def test_pending_event_survives_restart(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db_path = os.path.join(temp_dir.name, "agent_outbox.db")
        first = EventOutbox(db_path)
        event_id = first.enqueue({"machine": "inbat", "path": "D:\\job.tif", "event_type": "EXPORT"})

        second = EventOutbox(db_path)
        events = second.next_pending()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, event_id)

    def test_same_event_id_is_not_inserted_twice(self):
        outbox = self.make_outbox()
        payload = {
            "event_id": "fixed-event",
            "machine": "inbat",
            "path": "D:\\job.tif",
            "event_type": "EXPORT",
        }

        outbox.enqueue(payload)
        outbox.enqueue(payload)

        self.assertEqual(len(outbox.next_pending()), 1)


if __name__ == "__main__":
    unittest.main()


