import unittest

from backend_client import BackendClient


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.last_url = None
        self.last_json = None

    def get(self, url, headers=None, timeout=None):
        self.last_url = url
        return self.response

    def post(self, url, json=None, headers=None, timeout=None):
        self.last_url = url
        self.last_json = json
        return self.response


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
        queued = client._count_queue.get_nowait()
        self.assertEqual("http://localhost:5000/internal/round-count-event", queued["url"])
        self.assertEqual("trk-1", queued["payload"]["trackId"])

    def test_live_detections_is_ignored_in_current_backend_client(self):
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

        snapshot = client.get_health_snapshot()
        self.assertEqual(0, snapshot["liveQueued"])
        self.assertEqual(0, snapshot["liveDropped"])


class BackendClientRoundFetchTests(unittest.TestCase):
    def test_fetch_current_round_includes_camera_id_query_param(self):
        client = BackendClient(
            "http://localhost:8080/internal/round-count-event",
            "SUA_API_KEY",
            start_workers=False,
        )
        fake_session = _FakeSession(_FakeResponse(payload={"roundId": "rnd_1"}))
        client._session = fake_session

        payload = client.fetch_current_round("cam_001")

        self.assertEqual({"roundId": "rnd_1"}, payload)
        self.assertEqual("http://localhost:8080/rounds/current?cameraId=cam_001", fake_session.last_url)

    def test_void_current_round_posts_to_internal_void_endpoint(self):
        client = BackendClient(
            "http://localhost:8080/internal/round-count-event",
            "SUA_API_KEY",
            start_workers=False,
        )

        class _RoundThenVoidSession(_FakeSession):
            def get(self, url, headers=None, timeout=None):
                self.last_url = url
                return _FakeResponse(payload={"roundId": "round-123", "status": "open"})

            def post(self, url, json=None, headers=None, timeout=None):
                self.last_url = url
                self.last_json = json
                return _FakeResponse(status_code=200, payload={"voided": True})

        fake_session = _RoundThenVoidSession(_FakeResponse())
        client._session = fake_session

        result = client.void_current_round("cam_001", "forced switch")

        self.assertTrue(result)
        self.assertEqual("http://localhost:8080/internal/rounds/round-123/void", fake_session.last_url)
        self.assertEqual({"reason": "forced switch"}, fake_session.last_json)


if __name__ == "__main__":
    unittest.main()
