import unittest
from unittest import mock

from app import StreamCapture


class FakeCapture:
    def __init__(self, url: str):
        self.url = url
        self._opened = url.startswith("https://")

    def isOpened(self):
        return self._opened

    def set(self, *_args, **_kwargs):
        return True

    def get(self, *_args, **_kwargs):
        return 0.0

    def read(self):
        return False, None

    def release(self):
        return None


class StreamCaptureFailoverTests(unittest.TestCase):
    def test_switches_to_fallback_after_repeated_open_failures(self):
        fake_cv2 = StreamCapture.__init__.__globals__["cv2"]

        def fake_video_capture(url, *_args, **_kwargs):
            return FakeCapture(url)

        with mock.patch.object(fake_cv2, "VideoCapture", side_effect=fake_video_capture):
            stream = StreamCapture(
                "rtsp://127.0.0.1:8554/raw/cam_006",
                fallback_url="https://example.com/live.m3u8",
            )
            self.assertEqual("rtsp://127.0.0.1:8554/raw/cam_006", stream.url)

            stream.request_reset()
            stream.read()

            self.assertEqual("https://example.com/live.m3u8", stream.url)
            self.assertTrue(stream.cap.isOpened())
            stream.release()


if __name__ == "__main__":
    unittest.main()
