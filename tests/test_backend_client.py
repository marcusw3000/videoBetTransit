import unittest

from backend_client import BackendClient


class BackendClientQueueTests(unittest.TestCase):
    def test_count_event_drops_when_queue_is_full(self):
        client = BackendClient(
            "http://localhost:5000/api/rounds/count-events",
            "SUA_API_KEY",
            count_queue_size=1,
            live_queue_size=1,
            count_worker_count=1,
            live_worker_count=1,
            start_workers=False,
        )

        client.send_count_event({"trackId": "trk-1"})
        client.send_count_event({"trackId": "trk-2"})

        snapshot = client.get_health_snapshot()
        self.assertEqual(1, snapshot["countQueued"])
        self.assertEqual(1, snapshot["countDropped"])
        self.assertEqual({"trackId": "trk-1"}, client._count_queue.get_nowait())

    def test_live_detections_replaces_oldest_payload_when_queue_is_full(self):
        client = BackendClient(
            "http://localhost:5000/api/rounds/count-events",
            "SUA_API_KEY",
            count_queue_size=1,
            live_queue_size=1,
            count_worker_count=1,
            live_worker_count=1,
            start_workers=False,
        )

        first_payload = {"frameId": "frame-1"}
        second_payload = {"frameId": "frame-2"}

        client.send_live_detections(first_payload)
        client.send_live_detections(second_payload)

        replaced = client._live_queue.get_nowait()
        self.assertEqual(second_payload, replaced)

        snapshot = client.get_health_snapshot()
        self.assertEqual(1, snapshot["liveQueued"])
        self.assertEqual(1, snapshot["liveDropped"])


if __name__ == "__main__":
    unittest.main()
