import unittest
from types import SimpleNamespace
from unittest import mock

from app import (
    build_pipeline_config,
    is_youtube_url,
    resolve_stream_source_url,
    resolve_youtube_stream_url,
    validate_stream_url,
)


class StreamUrlResolutionTests(unittest.TestCase):
    def test_detects_youtube_urls(self):
        self.assertTrue(is_youtube_url("https://www.youtube.com/watch?v=abc123"))
        self.assertTrue(is_youtube_url("https://youtu.be/abc123"))
        self.assertTrue(is_youtube_url("https://www.youtube.com/live/abc123"))
        self.assertFalse(is_youtube_url("https://example.com/live.m3u8"))

    def test_rejects_browser_blob_url(self):
        with self.assertRaisesRegex(ValueError, "URL blob"):
            validate_stream_url("blob:https://www.youtube.com/session-only")

    def test_preserves_direct_stream_url(self):
        resolution = resolve_stream_source_url("https://example.com/live.m3u8")

        self.assertEqual("https://example.com/live.m3u8", resolution.original_url)
        self.assertEqual("https://example.com/live.m3u8", resolution.capture_url)
        self.assertFalse(resolution.resolved)

    def test_resolves_youtube_with_yt_dlp(self):
        fake_result = SimpleNamespace(
            returncode=0,
            stdout="https://rr.youtube.example/videoplayback.m3u8\n",
            stderr="",
        )
        subprocess_module = resolve_youtube_stream_url.__globals__["subprocess"]
        with mock.patch.object(subprocess_module, "run", return_value=fake_result) as run:
            resolution = resolve_stream_source_url("https://www.youtube.com/watch?v=abc123")

        self.assertEqual("https://www.youtube.com/watch?v=abc123", resolution.original_url)
        self.assertEqual("https://rr.youtube.example/videoplayback.m3u8", resolution.capture_url)
        self.assertTrue(resolution.resolved)
        self.assertIn("yt_dlp", run.call_args.args[0])

    def test_build_pipeline_uses_resolved_capture_url_but_keeps_original_url(self):
        fake_resolution = SimpleNamespace(
            original_url="https://www.youtube.com/watch?v=abc123",
            capture_url="https://rr.youtube.example/videoplayback.m3u8",
            resolved=True,
        )
        globals_dict = build_pipeline_config.__globals__
        original_resolver = globals_dict["resolve_stream_source_url"]
        original_mediamtx = globals_dict["ensure_mediamtx_source_path"]
        try:
            globals_dict["resolve_stream_source_url"] = mock.Mock(return_value=fake_resolution)
            globals_dict["ensure_mediamtx_source_path"] = mock.Mock(return_value=False)

            pipeline_cfg = build_pipeline_config(
                {
                    "camera_id": "cam_yt",
                    "stream_url": "https://www.youtube.com/watch?v=abc123",
                    "mediamtx_rtsp_url": "rtsp://127.0.0.1:8554",
                }
            )
        finally:
            globals_dict["resolve_stream_source_url"] = original_resolver
            globals_dict["ensure_mediamtx_source_path"] = original_mediamtx

        self.assertEqual("https://www.youtube.com/watch?v=abc123", pipeline_cfg["stream_url"])
        self.assertEqual("https://rr.youtube.example/videoplayback.m3u8", pipeline_cfg["capture_source_url"])
        self.assertTrue(pipeline_cfg["source_url_resolved"])


if __name__ == "__main__":
    unittest.main()
