from __future__ import annotations
import threading
import time


class RuntimeStats:
    def __init__(self):
        self._lock = threading.Lock()
        self._started_at = time.time()
        self._captured_frames = 0
        self._frames_processed = 0
        self._published_frames = 0
        self._last_capture_at = None
        self._last_capture_frame_at = None
        self._last_frame_at = None
        self._last_publish_at = None
        self._capture_fps_instant = 0.0
        self._capture_fps_average = 0.0
        self._fps_instant = 0.0
        self._fps_average = 0.0
        self._publish_fps_instant = 0.0
        self._publish_fps_average = 0.0
        self._last_inference_ms = 0.0
        self._avg_inference_ms = 0.0
        self._last_jpeg_encode_ms = 0.0
        self._avg_jpeg_encode_ms = 0.0
        self._last_pipeline_ms = 0.0
        self._avg_pipeline_ms = 0.0
        self._mjpeg_clients = 0
        self._stream_connected = False
        self._stream_failures = 0
        self._last_stream_error_at = None
        self._total_count = 0
        self._publisher_healthy = False
        self._publisher_restart_count = 0
        self._active_transport = "mjpeg"

    def record_capture(self, captured_at: float):
        with self._lock:
            self._captured_frames += 1
            if self._last_capture_frame_at is not None:
                elapsed = captured_at - self._last_capture_frame_at
                if elapsed > 0:
                    self._capture_fps_instant = 1.0 / elapsed
            total_elapsed = captured_at - self._started_at
            if total_elapsed > 0:
                self._capture_fps_average = self._captured_frames / total_elapsed
            self._last_capture_frame_at = captured_at
            self._last_capture_at = captured_at

    def record_processed_frame(self, total_count: int):
        now_ts = time.time()
        with self._lock:
            self._frames_processed += 1
            self._total_count = total_count
            if self._last_frame_at is not None:
                elapsed = now_ts - self._last_frame_at
                if elapsed > 0:
                    self._fps_instant = 1.0 / elapsed
            total_elapsed = now_ts - self._started_at
            if total_elapsed > 0:
                self._fps_average = self._frames_processed / total_elapsed
            self._last_frame_at = now_ts

    def record_published_frame(self, published_at: float | None = None):
        now_ts = published_at or time.time()
        with self._lock:
            self._published_frames += 1
            if self._last_publish_at is not None:
                elapsed = now_ts - self._last_publish_at
                if elapsed > 0:
                    self._publish_fps_instant = 1.0 / elapsed
            total_elapsed = now_ts - self._started_at
            if total_elapsed > 0:
                self._publish_fps_average = self._published_frames / total_elapsed
            self._last_publish_at = now_ts

    def record_inference_ms(self, duration_ms: float):
        with self._lock:
            self._last_inference_ms = duration_ms
            n = self._frames_processed or 1
            self._avg_inference_ms += (duration_ms - self._avg_inference_ms) / n

    def record_jpeg_encode_ms(self, duration_ms: float):
        with self._lock:
            self._last_jpeg_encode_ms = duration_ms
            n = self._frames_processed or 1
            self._avg_jpeg_encode_ms += (duration_ms - self._avg_jpeg_encode_ms) / n

    def record_pipeline_ms(self, duration_ms: float):
        with self._lock:
            self._last_pipeline_ms = duration_ms
            n = self._frames_processed or 1
            self._avg_pipeline_ms += (duration_ms - self._avg_pipeline_ms) / n

    def set_stream_status(self, connected: bool, failures: int):
        with self._lock:
            self._stream_connected = connected
            self._stream_failures = failures
            if not connected:
                self._last_stream_error_at = time.time()

    def add_mjpeg_client(self):
        with self._lock:
            self._mjpeg_clients += 1

    def remove_mjpeg_client(self):
        with self._lock:
            self._mjpeg_clients = max(0, self._mjpeg_clients - 1)

    def set_publisher_status(
        self,
        healthy: bool,
        *,
        restart_count: int | None = None,
        active_transport: str | None = None,
    ):
        with self._lock:
            self._publisher_healthy = healthy
            if restart_count is not None:
                self._publisher_restart_count = max(0, int(restart_count))
            if active_transport:
                self._active_transport = str(active_transport)

    def reset_pipeline_readiness(self):
        with self._lock:
            self._last_capture_at = None
            self._last_capture_frame_at = None
            self._last_frame_at = None
            self._last_publish_at = None
            self._stream_connected = False
            self._stream_failures = 0
            self._publisher_healthy = False
            self._active_transport = "mjpeg"

    def snapshot(self, backend_health: dict | None = None) -> dict:
        now_ts = time.time()
        with self._lock:
            raw_frame_age_ms = (
                round((now_ts - self._last_capture_at) * 1000, 2)
                if self._last_capture_at is not None
                else None
            )
            annotated_frame_age_ms = (
                round((now_ts - self._last_frame_at) * 1000, 2)
                if self._last_frame_at is not None
                else None
            )
            return {
                "ok": self._stream_connected,
                "captureFps": round(self._capture_fps_average, 2),
                "captureFpsInstant": round(self._capture_fps_instant, 2),
                "inferenceFps": round(self._fps_average, 2),
                "capturedFrames": self._captured_frames,
                "publishedFrames": self._published_frames,
                "framesProcessed": self._frames_processed,
                "fpsInstant": round(self._fps_instant, 2),
                "fpsAverage": round(self._fps_average, 2),
                "publishFps": round(self._publish_fps_average, 2),
                "publishFpsInstant": round(self._publish_fps_instant, 2),
                "lastInferenceMs": round(self._last_inference_ms, 2),
                "avgInferenceMs": round(self._avg_inference_ms, 2),
                "lastJpegEncodeMs": round(self._last_jpeg_encode_ms, 2),
                "avgJpegEncodeMs": round(self._avg_jpeg_encode_ms, 2),
                "lastPipelineMs": round(self._last_pipeline_ms, 2),
                "avgPipelineMs": round(self._avg_pipeline_ms, 2),
                "mjpegClients": self._mjpeg_clients,
                "streamConnected": self._stream_connected,
                "streamFailures": self._stream_failures,
                "lastCaptureAt": self._last_capture_at,
                "lastFrameAt": self._last_frame_at,
                "lastPublishAt": self._last_publish_at,
                "lastStreamErrorAt": self._last_stream_error_at,
                "totalCount": self._total_count,
                "rawFrameAgeMs": raw_frame_age_ms,
                "annotatedFrameAgeMs": annotated_frame_age_ms,
                "publisherHealthy": self._publisher_healthy,
                "publisherRestartCount": self._publisher_restart_count,
                "activeTransport": "mjpeg" if self._mjpeg_clients > 0 else self._active_transport,
                "backend": backend_health or {},
            }

