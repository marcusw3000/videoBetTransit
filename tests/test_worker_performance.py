import threading
import time
import unittest
from unittest import mock

from background_poll import BackgroundPoll, PENDING
from app import PipelineRuntime
from runtime_stats import RuntimeStats
from stream_capture import StreamCapture


class BackgroundPollTests(unittest.TestCase):
    def test_slow_request_does_not_block_or_overlap(self):
        release = threading.Event()
        started = threading.Event()
        calls = []

        def fetch():
            calls.append(1)
            started.set()
            release.wait(2)
            return {"round": 1}

        poll = BackgroundPoll()
        try:
            start = time.monotonic()
            self.assertIs(poll.poll("camera-a", fetch, 1), PENDING)
            self.assertTrue(started.wait(1))
            for _ in range(100):
                self.assertIs(poll.poll("camera-a", fetch, 1), PENDING)
            self.assertLess(time.monotonic() - start, 0.5)
            self.assertEqual(len(calls), 1)
        finally:
            release.set()

    def test_result_from_previous_camera_is_discarded(self):
        poll = BackgroundPoll()
        poll._context = "old-camera"
        poll._result = {"round": "old-round"}
        with mock.patch("background_poll.threading.Thread"):
            self.assertIs(poll.poll("new-camera", lambda: {}, 1), PENDING)

    def test_none_result_is_distinct_from_pending(self):
        poll = BackgroundPoll()
        poll._context = "camera"
        poll._result = None
        poll._next_at = time.monotonic() + 60
        self.assertIsNone(poll.poll("camera", lambda: {}, 1))
        self.assertIs(poll.poll("camera", lambda: {}, 1), PENDING)


class PipelinePacingTests(unittest.TestCase):
    def test_open_only_timeouts_are_passed_to_constructor(self):
        import cv2
        with mock.patch("stream_capture.cv2.VideoCapture") as constructor:
            constructor.return_value.get.return_value = 30
            stream = StreamCapture("https://example.com/live.m3u8", open_timeout_ms=1234, read_timeout_ms=5678)
            self.assertEqual(constructor.call_args.args[2], [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1234, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5678])
            self.assertAlmostEqual(stream.frame_interval_seconds, 1 / 30)

    def test_rtsp_is_not_artificially_paced(self):
        with mock.patch("stream_capture.cv2.VideoCapture") as constructor:
            constructor.return_value.get.return_value = 30
            self.assertEqual(StreamCapture("rtsp://localhost/live").frame_interval_seconds, 0)

    def test_pipeline_defers_network_open_to_capture_thread(self):
        with mock.patch('stream_capture.cv2.VideoCapture') as constructor:
            StreamCapture('https://example.com/live.m3u8', lazy_open=True)
            constructor.assert_not_called()

    def test_stopped_capture_does_not_publish_stale_frames_and_releases_itself(self):
        runtime = PipelineRuntime(RuntimeStats(), mock.Mock())
        stop = threading.Event()
        stream = mock.Mock(frame_interval_seconds=0)
        def read():
            stop.set()
            return True, object()
        stream.read.side_effect = read
        runtime._capture_loop(stream, stop)
        self.assertIsNone(runtime.raw_frames.get_latest()[1])
        stream.release.assert_called_once()

    def test_publisher_does_not_halve_fps_when_no_new_frames(self):
        runtime = PipelineRuntime(RuntimeStats(), mock.Mock())
        runtime.annotated_frames.update(object())
        stop = threading.Event()
        published = []

        def publish(_frame):
            published.append(time.monotonic())
            if len(published) >= 8:
                stop.set()

        runtime._publish_loop(mock.Mock(publish=publish), stop, 20)
        elapsed = published[-1] - published[0]
        self.assertGreater(elapsed, 0.25)
        self.assertLess(elapsed, 0.55)  # old double-wait took >= 0.70s

    def test_hls_burst_is_delivered_at_source_cadence(self):
        runtime = PipelineRuntime(RuntimeStats(), mock.Mock())
        stop = threading.Event()
        captures = []
        stream = mock.Mock(frame_interval_seconds=1 / 20)
        stream.read.return_value = (True, object())

        def update(_frame, _timestamp):
            captures.append(time.monotonic())
            if len(captures) >= 8:
                stop.set()

        runtime.raw_frames.update = update
        runtime._capture_loop(stream, stop)
        self.assertGreater(captures[-1] - captures[0], 0.25)
        self.assertLess(captures[-1] - captures[0], 0.55)


if __name__ == "__main__":
    unittest.main()
