import unittest
from types import SimpleNamespace
from unittest import mock

from app import (
    build_pipeline_config,
    build_youtube_resolve_command,
    get_stream_source_status,
    is_youtube_url,
    resolve_stream_source_url,
    resolve_youtube_stream_url,
    update_stream_source_status,
    validate_stream_url,
)


class StreamUrlResolutionTests(unittest.TestCase):
    def tearDown(self):
        update_stream_source_status(
            source_kind="",
            source_url_resolved=False,
            capture_direct_source_url="",
            capture_source_url="",
            last_resolve_error="",
        )

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

    def test_build_youtube_resolve_command_uses_browser_cookies_when_configured(self):
        command = build_youtube_resolve_command(
            "https://www.youtube.com/watch?v=abc123",
            cookies_from_browser="chrome",
            cookies_file="C:/tmp/cookies.txt",
        )

        self.assertIn("--cookies-from-browser", command)
        self.assertIn("chrome", command)
        self.assertNotIn("--cookies", command)

    def test_build_youtube_resolve_command_uses_cookie_file_when_browser_is_not_configured(self):
        command = build_youtube_resolve_command(
            "https://www.youtube.com/watch?v=abc123",
            cookies_file="C:/tmp/cookies.txt",
        )

        self.assertIn("--cookies", command)
        self.assertIn("C:/tmp/cookies.txt", command)

    def test_resolve_youtube_stream_url_raises_when_yt_dlp_fails(self):
        fake_result = SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="extractor failure",
        )
        subprocess_module = resolve_youtube_stream_url.__globals__["subprocess"]
        with mock.patch.object(subprocess_module, "run", return_value=fake_result):
            with self.assertRaisesRegex(RuntimeError, "yt-dlp nao conseguiu resolver"):
                resolve_youtube_stream_url("https://www.youtube.com/watch?v=abc123")

    def test_resolve_youtube_stream_url_raises_when_no_playable_url_is_returned(self):
        fake_result = SimpleNamespace(
            returncode=0,
            stdout="not-a-stream\n",
            stderr="",
        )
        subprocess_module = resolve_youtube_stream_url.__globals__["subprocess"]
        with mock.patch.object(subprocess_module, "run", return_value=fake_result):
            with self.assertRaisesRegex(RuntimeError, "nao retornou uma URL reproduzivel"):
                resolve_youtube_stream_url("https://www.youtube.com/watch?v=abc123")

    def test_resolves_youtube_with_browser_cookies_when_configured(self):
        fake_result = SimpleNamespace(
            returncode=0,
            stdout="https://rr.youtube.example/videoplayback.m3u8\n",
            stderr="",
        )
        subprocess_module = resolve_youtube_stream_url.__globals__["subprocess"]
        with mock.patch.object(subprocess_module, "run", return_value=fake_result) as run:
            resolve_stream_source_url(
                "https://www.youtube.com/watch?v=abc123",
                {
                    "youtube_cookies_from_browser": "chrome",
                    "youtube_cookies_file": "C:/tmp/cookies.txt",
                },
            )

        command = run.call_args.args[0]
        self.assertIn("--cookies-from-browser", command)
        self.assertIn("chrome", command)
        self.assertNotIn("--cookies", command)

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
        self.assertEqual("", pipeline_cfg["capture_fallback_source_url"])
        self.assertEqual("https://rr.youtube.example/videoplayback.m3u8", pipeline_cfg["capture_direct_source_url"])
        self.assertTrue(pipeline_cfg["source_url_resolved"])

        source_status = get_stream_source_status()
        self.assertEqual("youtube", source_status["sourceKind"])
        self.assertTrue(source_status["sourceUrlResolved"])
        self.assertEqual("https://rr.youtube.example/videoplayback.m3u8", source_status["captureDirectSourceUrl"])
        self.assertEqual("https://rr.youtube.example/videoplayback.m3u8", source_status["captureSourceUrl"])
        self.assertEqual("", source_status["lastResolveError"])

    def test_build_pipeline_uses_rtsp_primary_and_direct_fallback_when_mediamtx_is_ready(self):
        globals_dict = build_pipeline_config.__globals__
        original_mediamtx = globals_dict["ensure_mediamtx_source_path"]
        try:
            globals_dict["ensure_mediamtx_source_path"] = mock.Mock(return_value=True)

            pipeline_cfg = build_pipeline_config(
                {
                    "camera_id": "cam_yt",
                    "stream_url": "https://example.com/live.m3u8",
                    "mediamtx_rtsp_url": "rtsp://127.0.0.1:8554",
                }
            )
        finally:
            globals_dict["ensure_mediamtx_source_path"] = original_mediamtx

        self.assertEqual("rtsp://127.0.0.1:8554/raw/cam_yt", pipeline_cfg["capture_source_url"])
        self.assertEqual("https://example.com/live.m3u8", pipeline_cfg["capture_fallback_source_url"])
        self.assertEqual("https://example.com/live.m3u8", pipeline_cfg["capture_direct_source_url"])

    def test_build_pipeline_records_last_resolve_error_for_local_health(self):
        globals_dict = build_pipeline_config.__globals__
        original_resolver = globals_dict["resolve_stream_source_url"]
        try:
            globals_dict["resolve_stream_source_url"] = mock.Mock(side_effect=RuntimeError("yt-dlp missing"))

            with self.assertRaisesRegex(RuntimeError, "yt-dlp missing"):
                build_pipeline_config(
                    {
                        "camera_id": "cam_yt",
                        "stream_url": "https://www.youtube.com/watch?v=abc123",
                        "mediamtx_rtsp_url": "rtsp://127.0.0.1:8554",
                    }
                )
        finally:
            globals_dict["resolve_stream_source_url"] = original_resolver

        source_status = get_stream_source_status()
        self.assertEqual("youtube", source_status["sourceKind"])
        self.assertFalse(source_status["sourceUrlResolved"])
        self.assertEqual("yt-dlp missing", source_status["lastResolveError"])


if __name__ == "__main__":
    unittest.main()
