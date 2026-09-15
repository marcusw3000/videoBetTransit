import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from backend_client import BackendClient
from event_outbox import EventOutbox


class DurableDeliveryTests(unittest.TestCase):
    def test_restart_and_lost_ack_preserve_identifier(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'events.sqlite3')
            outbox = EventOutbox(path)
            event_id = outbox.enqueue('http://backend/internal/round-count-event', {'trackId': '1'})
            first = outbox.claim(now=10)
            outbox.close()  # process exits after the server saved the event, before the response
            restarted = EventOutbox(path)
            self.assertIsNone(restarted.claim(now=11))  # consumer lease
            retry = restarted.claim(now=41)
            self.assertEqual(event_id, retry['payload']['eventHash'])
            restarted.complete(first, accepted=True)  # stale consumer cannot delete a new lease
            self.assertEqual(1, restarted.count())
            restarted.complete(retry, accepted=True)
            self.assertEqual(0, restarted.count())
            restarted.close()

    def test_retry_order_and_permanent_rejection_retained(self):
        outbox = EventOutbox(':memory:')
        outbox.enqueue('url', {'eventHash': 'a'})
        outbox.enqueue('url', {'eventHash': 'b'})
        first = outbox.claim(now=10)
        outbox.complete(first, error='timeout', now=10)
        self.assertIsNone(outbox.claim(now=10.5))
        retry = outbox.claim(now=11)
        self.assertEqual('a', retry['payload']['eventHash'])
        outbox.complete(retry, permanent=True, error='outside round', now=11)
        self.assertEqual(1, outbox.count(rejected=True))
        self.assertEqual('b', outbox.claim(now=12)['payload']['eventHash'])
        outbox.close()

    def test_backend_timeout_keeps_persisted_event_for_retry(self):
        client = BackendClient('http://backend', 'test', start_workers=False, outbox_path=':memory:')
        client.send_count_event({'cameraId': 'cam', 'trackId': '42'})
        client._session.post = Mock(side_effect=TimeoutError())
        client.deliver_pending_once()
        self.assertEqual(1, client.get_health_snapshot()['countQueued'])
        # The next eligible delivery keeps the original eventHash; the backend
        # can therefore acknowledge a prior write idempotently.
        client._session.post = Mock(return_value=Mock(status_code=200, json=lambda: {'received': True}))
        client._outbox._db.execute('UPDATE outbox SET available_at=0')
        client.deliver_pending_once()
        self.assertEqual(0, client.get_health_snapshot()['countQueued'])
        client.close()

    def test_only_explicit_receipt_acknowledges_delivery(self):
        for body, expected_count in [({'received': True}, 0), ({'received': False}, 1), ({}, 1)]:
            with self.subTest(body=body):
                client = BackendClient('http://backend', 'test', start_workers=False, outbox_path=':memory:')
                client.send_count_event({'cameraId': 'cam', 'trackId': '42'})
                client._session.post = Mock(return_value=Mock(status_code=200, json=lambda: body))
                client.deliver_pending_once()
                self.assertEqual(expected_count, client.get_health_snapshot()['countQueued'])
                client.close()

    def test_hash_chain_survives_successful_delivery_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'events.sqlite3')
            outbox = EventOutbox(path)
            outbox.enqueue('url', {'sessionId': 'session', 'eventHash': 'first'})
            job = outbox.claim()
            outbox.complete(job, accepted=True)
            outbox.close()
            restored = EventOutbox(path)
            self.assertEqual('first', restored.previous_hash('session'))
            restored.close()

    def test_review_command_exposes_operational_fields_but_not_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'events.sqlite3')
            outbox = EventOutbox(path)
            outbox.enqueue('url', {
                'eventHash': 'rejected-event', 'cameraId': 'cam-01', 'roundId': 'round-01',
                'crossedAt': '2026-09-14T12:00:00Z', 'privateValue': 'must-not-leak'
            })
            job = outbox.claim(now=10)
            outbox.complete(job, permanent=True, error='HTTP 409', now=10)
            outbox.close()
            script = Path(__file__).resolve().parent.parent / 'scripts' / 'review-outbox.py'
            result = subprocess.run(
                [sys.executable, str(script), '--database', path, '--json'],
                capture_output=True, text=True, check=True)
            listed = json.loads(result.stdout)
            self.assertEqual('rejected-event', listed[0]['eventId'])
            self.assertEqual('round-01', listed[0]['roundId'])
            self.assertNotIn('must-not-leak', result.stdout)
