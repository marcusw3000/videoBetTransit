import json
import logging
import os
import queue
import random
import requests
import subprocess
import sys
import threading
import time
import atexit
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import cv2
from flask import Flask, Response, jsonify, request
from ultralytics import YOLO
from waitress import create_server

from backend_client import BackendClient
from supabase_sync import SupabaseStreamProfileSync

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


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


runtime_stats = RuntimeStats()
backend_client_ref: BackendClient | None = None
mjpeg_token_ref: str = ""
active_stream_ref = None
active_mjpeg_server_ref = None
active_control_panel_ref = None
active_snapshot_writer_ref = None
stream_rotation_status_lock = threading.Lock()
stream_rotation_status_ref = {
    "enabled": False,
    "mode": "round_boundary",
    "strategy": "uniform_excluding_current",
    "pending": False,
    "pendingProfileId": "",
    "selectedStreamProfileId": "",
    "activeProfileLabel": "",
    "lastMessage": "",
}
camera_activation_status_lock = threading.Lock()
camera_activation_status_ref = {
    "phase": "ready",
    "requestedCameraId": "",
    "readyCameraId": "",
    "requestedStreamProfileId": "",
    "readyStreamProfileId": "",
    "requestedProcessedStreamPath": "",
    "readyProcessedStreamPath": "",
    "requestedProfileLabel": "",
    "readyProfileLabel": "",
    "readyForRounds": True,
}

# ---------------------------------------------------------------------------
# Annotated MJPEG stream
# ---------------------------------------------------------------------------
class AnnotatedFrameStreamer:
    def __init__(self, jpeg_quality: int = 80, stats: RuntimeStats | None = None):
        self.jpeg_quality = jpeg_quality
        self.stats = stats
        self._lock = threading.Lock()
        self._latest_jpeg: bytes | None = None
        self._min_interval: float = 0.0  # 0 = sem limite

    def set_jpeg_quality(self, jpeg_quality: int):
        self.jpeg_quality = max(30, min(95, int(jpeg_quality)))

    def set_fps_limit(self, fps: float):
        self._min_interval = (1.0 / max(1.0, float(fps))) if fps > 0 else 0.0

    def update(self, frame):
        encode_start = time.perf_counter()
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        )
        if self.stats is not None:
            self.stats.record_jpeg_encode_ms((time.perf_counter() - encode_start) * 1000)
        if not ok:
            return

        with self._lock:
            self._latest_jpeg = encoded.tobytes()

    def get_latest(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def clear(self):
        with self._lock:
            self._latest_jpeg = None


streamer = AnnotatedFrameStreamer(jpeg_quality=80, stats=runtime_stats)


class LatestFrameSlot:
    def __init__(self):
        self._lock = threading.Lock()
        self._seq = 0
        self._frame = None
        self._timestamp = None

    def update(self, frame, timestamp: float | None = None):
        with self._lock:
            self._seq += 1
            self._frame = frame
            self._timestamp = timestamp or time.time()
            return self._seq

    def wait_for_new(self, last_seq: int, timeout: float = 0.25):
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            with self._lock:
                if self._seq > last_seq and self._frame is not None:
                    return self._seq, self._frame, self._timestamp
            if time.monotonic() >= deadline:
                return last_seq, None, None
            time.sleep(0.005)

    def get_latest(self):
        with self._lock:
            return self._seq, self._frame, self._timestamp

    def clear(self):
        with self._lock:
            self._seq = 0
            self._frame = None
            self._timestamp = None


@dataclass
class PipelineStartRequest:
    session_id: str = ""
    camera_id: str = ""
    source_url: str = ""
    raw_stream_path: str = ""
    processed_stream_path: str = ""
    direction: str = "any"
    count_line: dict | None = None


class RtspFramePublisher:
    def __init__(
        self,
        *,
        rtsp_url: str,
        fps: float,
        ffmpeg_bin: str = "ffmpeg",
        stats: RuntimeStats | None = None,
    ):
        self.rtsp_url = rtsp_url
        self.fps = max(1.0, float(fps))
        self.ffmpeg_bin = ffmpeg_bin or "ffmpeg"
        self.stats = stats
        self._process: subprocess.Popen | None = None
        self._shape = None
        self._restart_count = 0
        self._lock = threading.Lock()

    @property
    def restart_count(self) -> int:
        with self._lock:
            return self._restart_count

    def _build_command(self, frame_shape) -> list[str]:
        height, width = frame_shape[:2]
        gop = max(1, int(round(self.fps)))
        return [
            self.ffmpeg_bin,
            "-loglevel", "warning",
            "-fflags", "nobuffer",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", f"{self.fps:.02f}",
            "-i", "-",
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-bf", "0",
            "-g", str(gop),
            "-keyint_min", str(gop),
            "-rtsp_transport", "tcp",
            "-f", "rtsp",
            self.rtsp_url,
        ]

    def _set_stats(self, healthy: bool):
        if self.stats is not None:
            self.stats.set_publisher_status(
                healthy,
                restart_count=self.restart_count,
                active_transport="webrtc" if healthy else "mjpeg",
            )

    def _start_process(self, frame_shape):
        self.stop()
        command = self._build_command(frame_shape)
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        logger.info("Iniciando publisher RTSP: %s", self.rtsp_url)
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            self._shape = tuple(frame_shape[:2])
            self._set_stats(True)
            return True
        except Exception as exc:
            logger.warning("Falha ao iniciar publisher RTSP: %s", exc)
            self._process = None
            self._shape = None
            self._set_stats(False)
            return False

    def publish(self, frame):
        if frame is None:
            return False

        frame_shape = tuple(frame.shape[:2])
        process = self._process
        if process is None or self._shape != frame_shape or process.poll() is not None:
            with self._lock:
                self._restart_count += 1
            if not self._start_process(frame.shape):
                return False
            process = self._process

        try:
            assert process is not None and process.stdin is not None
            process.stdin.write(frame.tobytes())
            process.stdin.flush()
            if self.stats is not None:
                self.stats.record_published_frame()
            self._set_stats(True)
            return True
        except Exception as exc:
            logger.warning("Falha ao publicar frame no RTSP: %s", exc)
            self._set_stats(False)
            self.stop()
            return False

    def stop(self):
        process = self._process
        self._process = None
        self._shape = None
        if process is None:
            self._set_stats(False)
            return

        try:
            if process.stdin is not None:
                process.stdin.close()
        except Exception:
            pass

        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        finally:
            self._set_stats(False)


class PipelineRuntime:
    def __init__(self, stats: RuntimeStats, mjpeg_streamer: AnnotatedFrameStreamer):
        self.stats = stats
        self.mjpeg_streamer = mjpeg_streamer
        self.raw_frames = LatestFrameSlot()
        self.annotated_frames = LatestFrameSlot()
        self._lock = threading.Lock()
        self._capture_thread = None
        self._publish_thread = None
        self._capture_stop = None
        self._publish_stop = None
        self._stream = None
        self._publisher = None
        self._config = None
        self._running = False

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def get_config(self) -> dict | None:
        with self._lock:
            return dict(self._config or {}) if self._config else None

    def start(self, config: dict):
        self.stop()

        capture_source_url = str(config.get("capture_source_url") or config.get("stream_url") or "").strip()
        if not capture_source_url:
            raise ValueError("Nenhuma URL de captura configurada para a pipeline.")

        stream = StreamCapture(
            capture_source_url,
            stats=self.stats,
            ffmpeg_options=config.get("ffmpeg_capture_options"),
            buffer_size=int(config.get("stream_buffer_size", 1)),
            open_timeout_ms=int(config.get("stream_open_timeout_ms", 5000)),
            read_timeout_ms=int(config.get("stream_read_timeout_ms", 5000)),
            target_fps=float(config.get("stream_target_fps", 0)),
        )

        publisher = RtspFramePublisher(
            rtsp_url=str(config.get("publisher_rtsp_url") or "").strip(),
            fps=float(config.get("publisher_fps", 10)),
            ffmpeg_bin=str(config.get("publisher_ffmpeg_bin") or "ffmpeg"),
            stats=self.stats,
        )

        capture_stop = threading.Event()
        publish_stop = threading.Event()

        capture_thread = threading.Thread(
            target=self._capture_loop,
            args=(stream, capture_stop),
            daemon=True,
            name="capture-loop",
        )
        publish_thread = threading.Thread(
            target=self._publish_loop,
            args=(publisher, publish_stop, float(config.get("publisher_fps", 10))),
            daemon=True,
            name="publish-loop",
        )

        with self._lock:
            self._stream = stream
            self._publisher = publisher
            self._capture_stop = capture_stop
            self._publish_stop = publish_stop
            self._capture_thread = capture_thread
            self._publish_thread = publish_thread
            self._config = dict(config)
            self._running = True

        self.raw_frames.clear()
        self.annotated_frames.clear()
        capture_thread.start()
        publish_thread.start()

    def stop(self):
        with self._lock:
            stream = self._stream
            publisher = self._publisher
            capture_stop = self._capture_stop
            publish_stop = self._publish_stop
            capture_thread = self._capture_thread
            publish_thread = self._publish_thread
            self._stream = None
            self._publisher = None
            self._capture_stop = None
            self._publish_stop = None
            self._capture_thread = None
            self._publish_thread = None
            self._config = None
            self._running = False

        if capture_stop is not None:
            capture_stop.set()
        if publish_stop is not None:
            publish_stop.set()

        if capture_thread is not None and capture_thread.is_alive():
            capture_thread.join(timeout=2)
        if publish_thread is not None and publish_thread.is_alive():
            publish_thread.join(timeout=2)

        if stream is not None:
            stream.release()
        if publisher is not None:
            publisher.stop()

        self.raw_frames.clear()
        self.annotated_frames.clear()

    def request_capture_reset(self):
        with self._lock:
            stream = self._stream
        if stream is not None:
            stream.request_refresh_latest()

    def wait_for_raw_frame(self, last_seq: int, timeout: float = 0.25):
        return self.raw_frames.wait_for_new(last_seq, timeout)

    def push_annotated_frame(self, frame):
        self.annotated_frames.update(frame, time.time())
        self.mjpeg_streamer.update(frame)

    def _capture_loop(self, stream: "StreamCapture", stop_event: threading.Event):
        while not stop_event.is_set():
            ret, frame = stream.read()
            if not ret:
                time.sleep(0.005)
                continue

            captured_at = time.time()
            self.stats.record_capture(captured_at)
            self.raw_frames.update(frame, captured_at)

    def _publish_loop(self, publisher: RtspFramePublisher, stop_event: threading.Event, fps: float):
        interval = 1.0 / max(1.0, fps)
        last_seq = 0
        last_frame = None

        while not stop_event.is_set():
            seq, frame, _ = self.annotated_frames.wait_for_new(last_seq, timeout=interval)
            if frame is not None:
                last_seq = seq
                last_frame = frame

            if last_frame is None:
                time.sleep(0.01)
                continue

            publisher.publish(last_frame)
            time.sleep(interval)


pipeline_runtime = PipelineRuntime(runtime_stats, streamer)
pipeline_request_lock = threading.Lock()
pending_pipeline_start: PipelineStartRequest | None = None
pending_pipeline_stop = False
pending_pipeline_refresh = False


def queue_pipeline_start(request_data: PipelineStartRequest):
    global pending_pipeline_start, pending_pipeline_stop, pending_pipeline_refresh
    with pipeline_request_lock:
        pending_pipeline_start = request_data
        pending_pipeline_stop = False
        pending_pipeline_refresh = False


def queue_pipeline_stop():
    global pending_pipeline_start, pending_pipeline_stop, pending_pipeline_refresh
    with pipeline_request_lock:
        pending_pipeline_stop = True
        pending_pipeline_start = None
        pending_pipeline_refresh = False


def queue_pipeline_refresh():
    global pending_pipeline_refresh
    with pipeline_request_lock:
        pending_pipeline_refresh = True


def consume_pipeline_commands():
    global pending_pipeline_start, pending_pipeline_stop, pending_pipeline_refresh
    with pipeline_request_lock:
        next_start = pending_pipeline_start
        next_stop = pending_pipeline_stop
        next_refresh = pending_pipeline_refresh
        pending_pipeline_start = None
        pending_pipeline_stop = False
        pending_pipeline_refresh = False
    return next_start, next_stop, next_refresh


def update_stream_rotation_status(**values):
    with stream_rotation_status_lock:
        stream_rotation_status_ref.update(values)


def get_stream_rotation_status() -> dict:
    with stream_rotation_status_lock:
        return dict(stream_rotation_status_ref)


def update_camera_activation_status(**values):
    with camera_activation_status_lock:
        camera_activation_status_ref.update(values)


def get_camera_activation_status() -> dict:
    with camera_activation_status_lock:
        return dict(camera_activation_status_ref)


def is_mjpeg_request_authorized() -> bool:
    if not mjpeg_token_ref:
        return True

    header_token = request.headers.get("X-API-Key", "")
    query_token = request.args.get("token", "")
    return header_token == mjpeg_token_ref or query_token == mjpeg_token_ref


def create_mjpeg_app() -> Flask:
    app = Flask(__name__)

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.get("/health")
    def health():
        backend_health = (
            backend_client_ref.get_health_snapshot() if backend_client_ref else {}
        )
        payload = runtime_stats.snapshot(backend_health)
        active_config = pipeline_runtime.get_config() or {}
        stream_profiles = active_config.get("stream_profiles", [])
        eligible_camera_ids = sorted({
            str(profile.get("camera_id") or "").strip()
            for profile in stream_profiles
            if str(profile.get("camera_id") or "").strip()
        })
        payload["pipelineRunning"] = pipeline_runtime.is_running()
        activation = get_camera_activation_status()
        payload["cameraId"] = activation.get("readyCameraId") or active_config.get("camera_id", "")
        payload["sourceUrl"] = active_config.get("stream_url", "")
        payload["captureSourceUrl"] = active_config.get("capture_source_url", "")
        payload["processedStreamPath"] = activation.get("readyProcessedStreamPath") or active_config.get("processed_stream_path", "")
        payload["selectedStreamProfileId"] = active_config.get("selected_stream_profile_id", "")
        payload["streamProfileCameraIds"] = eligible_camera_ids
        payload["streamRotation"] = get_stream_rotation_status()
        payload["cameraActivation"] = activation
        return jsonify(payload)

    @app.post("/pipeline/start")
    def pipeline_start():
        data = request.get_json(silent=True) or {}
        source_url = str(data.get("sourceUrl") or "").strip()
        camera_id = str(data.get("cameraId") or "").strip()
        processed_stream_path = str(data.get("processedStreamPath") or "").strip()

        if not source_url:
            return jsonify({"message": "sourceUrl is required."}), 400
        if not camera_id:
            return jsonify({"message": "cameraId is required."}), 400
        if not processed_stream_path:
            processed_stream_path = f"processed/{camera_id}"

        queue_pipeline_start(PipelineStartRequest(
            session_id=str(data.get("sessionId") or "").strip(),
            camera_id=camera_id,
            source_url=source_url,
            raw_stream_path=str(data.get("rawStreamPath") or "").strip(),
            processed_stream_path=processed_stream_path,
            direction=normalize_count_direction(data.get("direction")),
            count_line=data.get("countLine") if isinstance(data.get("countLine"), dict) else None,
        ))

        return jsonify({
            "ok": True,
            "cameraId": camera_id,
            "processedStreamPath": processed_stream_path,
        })

    @app.post("/pipeline/stop")
    def pipeline_stop():
        queue_pipeline_stop()
        return jsonify({"ok": True})

    @app.get("/video_feed")
    def video_feed():
        if not is_mjpeg_request_authorized():
            return jsonify({"message": "Invalid or missing MJPEG token."}), 401

        def generate():
            last_sent = None
            last_sent_at = 0.0
            runtime_stats.add_mjpeg_client()

            try:
                while True:
                    frame = streamer.get_latest()
                    if frame is None:
                        time.sleep(0.03)
                        continue

                    if frame is last_sent:
                        time.sleep(0.01)
                        continue

                    if streamer._min_interval > 0:
                        now = time.monotonic()
                        wait = streamer._min_interval - (now - last_sent_at)
                        if wait > 0:
                            time.sleep(wait)

                    last_sent = frame
                    last_sent_at = time.monotonic()
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Cache-Control: no-cache\r\n\r\n"
                        + frame
                        + b"\r\n"
                    )
            finally:
                runtime_stats.remove_mjpeg_client()

        return Response(
            generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    return app


class MjpegServer:
    def __init__(self, app: Flask, host: str, port: int, threads: int = 8):
        self._server = create_server(
            app,
            host=host,
            port=port,
            threads=threads,
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self.host = host
        self.port = port

    def start(self):
        self._thread.start()
        logger.info("MJPEG server iniciado em http://%s:%s/video_feed", self.host, self.port)

    def stop(self):
        logger.info("Encerrando servidor MJPEG...")
        self._server.close()
        self._thread.join(timeout=5)


mjpeg_app = create_mjpeg_app()


def run_mjpeg_server(host: str = "0.0.0.0", port: int = 8090) -> MjpegServer:
    server = MjpegServer(mjpeg_app, host=host, port=port)
    server.start()
    return server


class AsyncSnapshotWriter:
    def __init__(self, *, queue_size: int = 32, jpeg_quality: int = 85):
        self.jpeg_quality = max(30, min(95, int(jpeg_quality)))
        self._queue: queue.Queue = queue.Queue(maxsize=max(1, int(queue_size)))
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def enqueue(self, path: str, frame):
        try:
            self._queue.put_nowait((path, frame.copy()))
            return True
        except queue.Full:
            logger.warning("Fila de snapshots cheia; snapshot descartado: %s", path)
            return False

    def _worker_loop(self):
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                path, frame = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                ok, encoded = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
                )
                if ok:
                    with open(path, "wb") as f:
                        f.write(encoded.tobytes())
                else:
                    logger.warning("Falha ao codificar snapshot %s", path)
            except Exception as exc:
                logger.warning("Falha ao salvar snapshot %s: %s", path, exc)
            finally:
                self._queue.task_done()

    def stop(self):
        self._stop_event.set()
        if self._worker.is_alive():
            self._worker.join(timeout=2.0)


def cleanup_runtime():
    global active_stream_ref, active_mjpeg_server_ref, active_control_panel_ref, active_snapshot_writer_ref

    pipeline_runtime.stop()

    if active_stream_ref is not None:
        active_stream_ref.release()
        active_stream_ref = None

    if active_mjpeg_server_ref is not None:
        active_mjpeg_server_ref.stop()
        active_mjpeg_server_ref = None

    if active_control_panel_ref is not None:
        active_control_panel_ref.close()
        active_control_panel_ref = None

    if active_snapshot_writer_ref is not None:
        active_snapshot_writer_ref.stop()
        active_snapshot_writer_ref = None

    cv2.destroyAllWindows()


atexit.register(cleanup_runtime)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
DEFAULT_ROI = {"x": 0, "y": 0, "w": 0, "h": 0}
DEFAULT_LINE = {"x1": 0, "y1": 0, "x2": 0, "y2": 0}
DEFAULT_STREAM_ROTATION = {
    "enabled": False,
    "mode": "round_boundary",
    "strategy": "uniform_excluding_current",
    "min_rounds_per_stream": 6,
    "max_rounds_per_stream": 11,
    "current_stream_profile_id": "",
    "rounds_on_current_stream": 0,
    "target_rounds_for_current_stream": 0,
    "last_counted_round_id": "",
}
STREAM_ROTATION_SAFE_STATUSES = {"settling", "settled", "void"}
STREAM_ROTATION_DEFER_STATUSES = {"open", "closing"}


def normalize_roi_config(value, fallback: dict | None = None) -> dict:
    source = value if isinstance(value, dict) else {}
    base = fallback if isinstance(fallback, dict) else DEFAULT_ROI
    return {
        "x": int(source.get("x", base.get("x", 0)) or 0),
        "y": int(source.get("y", base.get("y", 0)) or 0),
        "w": int(source.get("w", base.get("w", 0)) or 0),
        "h": int(source.get("h", base.get("h", 0)) or 0),
    }


def normalize_line_config(value, fallback: dict | None = None) -> dict:
    source = value if isinstance(value, dict) else {}
    base = fallback if isinstance(fallback, dict) else DEFAULT_LINE
    return {
        "x1": int(source.get("x1", base.get("x1", 0)) or 0),
        "y1": int(source.get("y1", base.get("y1", 0)) or 0),
        "x2": int(source.get("x2", base.get("x2", 0)) or 0),
        "y2": int(source.get("y2", base.get("y2", 0)) or 0),
    }


def normalize_count_direction(value) -> str:
    direction = str(value or "any").strip().lower()
    aliases = {
        "down_to_up": "up",
        "up_to_down": "down",
        "left_to_right": "right",
        "right_to_left": "left",
    }
    direction = aliases.get(direction, direction)
    if direction in {"up", "down", "left", "right", "any"}:
        return direction
    return "any"


def normalize_stream_rotation_config(value) -> dict:
    source = value if isinstance(value, dict) else {}
    mode = str(source.get("mode") or DEFAULT_STREAM_ROTATION["mode"]).strip().lower()
    strategy = str(source.get("strategy") or DEFAULT_STREAM_ROTATION["strategy"]).strip().lower()
    min_rounds = int(source.get("min_rounds_per_stream", DEFAULT_STREAM_ROTATION["min_rounds_per_stream"]) or 0)
    max_rounds = int(source.get("max_rounds_per_stream", DEFAULT_STREAM_ROTATION["max_rounds_per_stream"]) or 0)
    min_rounds = max(1, min_rounds)
    max_rounds = max(min_rounds, max_rounds)
    target_rounds = int(source.get("target_rounds_for_current_stream", 0) or 0)

    if mode != "round_boundary":
        mode = DEFAULT_STREAM_ROTATION["mode"]
    if strategy != "uniform_excluding_current":
        strategy = DEFAULT_STREAM_ROTATION["strategy"]

    return {
        "enabled": bool(source.get("enabled", DEFAULT_STREAM_ROTATION["enabled"])),
        "mode": mode,
        "strategy": strategy,
        "min_rounds_per_stream": min_rounds,
        "max_rounds_per_stream": max_rounds,
        "current_stream_profile_id": str(source.get("current_stream_profile_id") or "").strip(),
        "rounds_on_current_stream": max(0, int(source.get("rounds_on_current_stream", 0) or 0)),
        "target_rounds_for_current_stream": target_rounds if min_rounds <= target_rounds <= max_rounds else 0,
        "last_counted_round_id": str(source.get("last_counted_round_id") or "").strip(),
    }


def get_round_status(backend_round: dict | None) -> str:
    if not isinstance(backend_round, dict):
        return ""
    return str(backend_round.get("status") or "").strip().lower()


def get_round_id(backend_round: dict | None) -> str:
    if not isinstance(backend_round, dict):
        return ""
    return str(backend_round.get("roundId") or "").strip()


def is_round_safe_for_stream_rotation(backend_round: dict | None) -> bool:
    return get_round_status(backend_round) in STREAM_ROTATION_SAFE_STATUSES


def should_defer_stream_rotation(backend_round: dict | None) -> bool:
    status = get_round_status(backend_round)
    return not status or status in STREAM_ROTATION_DEFER_STATUSES or status not in STREAM_ROTATION_SAFE_STATUSES


def select_random_stream_profile(
    profiles: list[dict],
    current_profile_id: str = "",
    *,
    rng=random,
) -> dict | None:
    eligible = [
        dict(profile)
        for profile in profiles
        if str(profile.get("id") or "").strip()
        and str(profile.get("stream_url") or "").strip()
        and str(profile.get("camera_id") or "").strip()
    ]
    if len(eligible) < 2:
        return None

    current_profile_id = str(current_profile_id or "").strip()
    candidates = [
        profile for profile in eligible
        if str(profile.get("id") or "").strip() != current_profile_id
    ]
    if not candidates:
        candidates = eligible

    return dict(rng.choice(candidates))


def should_apply_pending_stream_rotation(
    pending_profile: dict | None,
    backend_round: dict | None,
) -> bool:
    return isinstance(pending_profile, dict) and is_round_safe_for_stream_rotation(backend_round)


def choose_stream_rotation_target(rotation: dict, *, rng=random) -> int:
    normalized = normalize_stream_rotation_config(rotation)
    return int(rng.randint(
        normalized["min_rounds_per_stream"],
        normalized["max_rounds_per_stream"],
    ))


def ensure_stream_rotation_profile_state(
    rotation: dict,
    stream_profile_id: str,
    *,
    rng=random,
    force_new_target: bool = False,
) -> bool:
    profile_id = str(stream_profile_id or "").strip()
    previous_profile_id = str(rotation.get("current_stream_profile_id") or "").strip()
    changed = previous_profile_id != profile_id

    if changed:
        rotation["current_stream_profile_id"] = profile_id
        rotation["rounds_on_current_stream"] = 0
        rotation["last_counted_round_id"] = ""

    if changed or force_new_target or int(rotation.get("target_rounds_for_current_stream", 0) or 0) <= 0:
        rotation["target_rounds_for_current_stream"] = choose_stream_rotation_target(rotation, rng=rng)
        return True

    return changed


def count_settled_round_for_stream_rotation(rotation: dict, backend_round: dict | None) -> bool:
    if get_round_status(backend_round) not in {"settling", "settled"}:
        return False

    round_id = get_round_id(backend_round)
    if not round_id or round_id == str(rotation.get("last_counted_round_id") or ""):
        return False

    rotation["last_counted_round_id"] = round_id
    rotation["rounds_on_current_stream"] = max(
        0,
        int(rotation.get("rounds_on_current_stream", 0) or 0),
    ) + 1
    return True


def stream_rotation_target_reached(rotation: dict) -> bool:
    target = int(rotation.get("target_rounds_for_current_stream", 0) or 0)
    if target <= 0:
        return False
    rounds = int(rotation.get("rounds_on_current_stream", 0) or 0)
    return rounds >= target


def format_stream_rotation_progress(rotation: dict) -> str:
    if not rotation.get("enabled"):
        return "Rotacao randômica desativada."
    rounds = int(rotation.get("rounds_on_current_stream", 0) or 0)
    target = int(rotation.get("target_rounds_for_current_stream", 0) or 0)
    if target <= 0:
        return "Rotacao ativa: alvo ainda nao sorteado."
    return f"Rotacao ativa: {rounds}/{target} rounds nesta stream"


def shorten_text(value: str, max_len: int = 56) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3]}..."


def guess_stream_profile_name(stream_url: str, camera_id: str = "", index: int = 1) -> str:
    camera_id = str(camera_id or "").strip()
    if camera_id:
        return camera_id

    url = str(stream_url or "").strip()
    if url:
        parsed = urlparse(url)
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[-1].lower().startswith("stream"):
            return path_parts[-2]
        if path_parts:
            return path_parts[-1]
        if parsed.netloc:
            return parsed.netloc

    return f"Stream {index}"


def format_stream_profile_label(profile: dict) -> str:
    name = str(profile.get("name") or "").strip() or guess_stream_profile_name(
        profile.get("stream_url", ""),
        profile.get("camera_id", ""),
    )
    camera_id = str(profile.get("camera_id") or "").strip()
    hint = camera_id or str(profile.get("stream_url") or "").strip()
    hint = shorten_text(hint, max_len=48)
    if hint and hint != name:
        return f"{name} | {hint}"
    return name


def format_stream_profile_table_row(profile: dict, *, active: bool = False) -> tuple[str, str, str, str]:
    name = str(profile.get("name") or "").strip() or guess_stream_profile_name(
        profile.get("stream_url", ""),
        profile.get("camera_id", ""),
    )
    camera_id = str(profile.get("camera_id") or "").strip()
    stream_url = shorten_text(str(profile.get("stream_url") or "").strip(), max_len=72)
    return ("*" if active else "", name, camera_id, stream_url)


def make_stream_profile_id(existing_ids: set[str]) -> str:
    base = f"stream_{int(time.time() * 1000)}"
    candidate = base
    suffix = 1
    while candidate in existing_ids:
        suffix += 1
        candidate = f"{base}_{suffix}"
    return candidate


def build_stream_profile(source: dict | None, fallback_cfg: dict, *, index: int) -> dict:
    source = source if isinstance(source, dict) else {}
    stream_url = validate_stream_url(
        source.get("stream_url")
        or source.get("url")
        or fallback_cfg.get("stream_url", "")
    )
    camera_id = str(source.get("camera_id") or fallback_cfg.get("camera_id", "")).strip()
    profile = {
        "id": str(source.get("id") or "").strip(),
        "name": str(source.get("name") or "").strip(),
        "stream_url": stream_url,
        "camera_id": camera_id,
        "roi": normalize_roi_config(source.get("roi"), fallback_cfg.get("roi")),
        "line": normalize_line_config(source.get("line"), fallback_cfg.get("line")),
        "count_direction": normalize_count_direction(
            source.get("count_direction") or fallback_cfg.get("count_direction", "any")
        ),
    }
    if not profile["name"]:
        profile["name"] = guess_stream_profile_name(stream_url, camera_id, index=index)
    return profile


def sync_config_with_selected_profile(cfg: dict, profile: dict) -> dict:
    profile["roi"] = normalize_roi_config(profile.get("roi"), cfg.get("roi"))
    profile["line"] = normalize_line_config(profile.get("line"), cfg.get("line"))
    profile["count_direction"] = normalize_count_direction(
        profile.get("count_direction") or cfg.get("count_direction", "any")
    )
    profile["camera_id"] = str(profile.get("camera_id") or cfg.get("camera_id", "")).strip()
    profile["stream_url"] = validate_stream_url(profile.get("stream_url") or "")
    if not profile["name"]:
        profile["name"] = guess_stream_profile_name(profile["stream_url"], profile["camera_id"])

    cfg["selected_stream_profile_id"] = profile["id"]
    cfg["stream_url"] = profile["stream_url"]
    cfg["camera_id"] = profile["camera_id"]
    cfg["roi"] = dict(profile["roi"])
    cfg["line"] = dict(profile["line"])
    cfg["count_direction"] = profile["count_direction"]
    return profile


def normalize_config(cfg: dict | None) -> dict:
    cfg = dict(cfg or {})
    cfg["stream_rotation"] = normalize_stream_rotation_config(cfg.get("stream_rotation"))
    raw_profiles = cfg.get("stream_profiles")
    profiles = []

    if isinstance(raw_profiles, list):
        for index, raw_profile in enumerate(raw_profiles, start=1):
            try:
                profile = build_stream_profile(raw_profile, cfg, index=index)
            except ValueError as exc:
                logger.warning("Stream profile ignorado: %s", exc)
                continue
            if profile["stream_url"]:
                profiles.append(profile)

    if not profiles:
        try:
            profiles.append(build_stream_profile({}, cfg, index=1))
        except ValueError:
            fallback_cfg = dict(cfg)
            fallback_cfg["stream_url"] = ""
            profiles.append(build_stream_profile({}, fallback_cfg, index=1))

    existing_ids: set[str] = set()
    for index, profile in enumerate(profiles, start=1):
        if not profile["id"] or profile["id"] in existing_ids:
            profile["id"] = make_stream_profile_id(existing_ids)
        if not profile["name"]:
            profile["name"] = guess_stream_profile_name(
                profile["stream_url"],
                profile["camera_id"],
                index=index,
            )
        existing_ids.add(profile["id"])

    cfg["stream_profiles"] = profiles
    selected_profile_id = str(cfg.get("selected_stream_profile_id") or "").strip()
    selected_profile = next((profile for profile in profiles if profile["id"] == selected_profile_id), None)
    if selected_profile is None:
        current_stream_url = validate_stream_url(cfg.get("stream_url") or "")
        selected_profile = next((profile for profile in profiles if profile["stream_url"] == current_stream_url), None)
    if selected_profile is None:
        selected_profile = profiles[0]

    sync_config_with_selected_profile(cfg, selected_profile)
    return cfg


def load_config(path: str = "config.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = normalize_config(json.load(f))

    env_overrides = {
        "backend_url": os.getenv("BACKEND_URL"),
        "api_key": os.getenv("BACKEND_API_KEY") or os.getenv("API_KEY"),
        "mjpeg_token": os.getenv("MJPEG_TOKEN"),
        "mediamtx_api_url": os.getenv("MEDIAMTX_API_URL"),
        "mediamtx_rtsp_url": os.getenv("MEDIAMTX_RTSP_URL"),
        "publisher_ffmpeg_bin": os.getenv("FFMPEG_BIN"),
        "supabase_url": os.getenv("SUPABASE_URL"),
        "supabase_service_key": os.getenv("SUPABASE_SERVICE_KEY"),
        "supabase_stream_profiles_table": os.getenv("SUPABASE_STREAM_PROFILES_TABLE"),
        "supabase_stream_profiles_scope": os.getenv("SUPABASE_STREAM_PROFILES_SCOPE"),
        "camera_id": os.getenv("CAMERA_ID"),
        "session_id": os.getenv("SESSION_ID"),
        "line_id": os.getenv("LINE_ID"),
        "stream_url": os.getenv("STREAM_URL"),
    }

    for key, value in env_overrides.items():
        if value is not None and str(value).strip():
            cfg[key] = value.strip()

    return normalize_config(cfg)


def save_config(path: str, cfg: dict):
    normalized_cfg = normalize_config(cfg)
    cfg.clear()
    cfg.update(normalized_cfg)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized_cfg, f, indent=2)


def bootstrap_stream_profiles_from_supabase(
    cfg: dict,
    config_path: str,
    sync_client: SupabaseStreamProfileSync | None,
) -> None:
    if sync_client is None:
        return

    try:
        remote_profiles, remote_selected_profile_id = sync_client.fetch_profiles()
    except Exception as exc:
        logger.warning("Falha ao carregar stream profiles do Supabase: %s", exc)
        return

    if remote_profiles:
        cfg["stream_profiles"] = remote_profiles
        if remote_selected_profile_id:
            cfg["selected_stream_profile_id"] = remote_selected_profile_id
        normalize_config(cfg)
        save_config(config_path, cfg)
        logger.info(
            "Stream profiles carregados do Supabase: %d perfil(is)",
            len(cfg.get("stream_profiles", [])),
        )
        return

    try:
        sync_client.upsert_profiles(
            cfg.get("stream_profiles", []),
            cfg.get("selected_stream_profile_id"),
        )
        logger.info(
            "Supabase sem stream profiles. Config local publicada com %d perfil(is).",
            len(cfg.get("stream_profiles", [])),
        )
    except Exception as exc:
        logger.warning("Falha ao publicar stream profiles iniciais no Supabase: %s", exc)


def sync_stream_profiles_to_supabase(
    cfg: dict,
    sync_client: SupabaseStreamProfileSync | None,
) -> None:
    if sync_client is None:
        return

    try:
        sync_client.upsert_profiles(
            cfg.get("stream_profiles", []),
            cfg.get("selected_stream_profile_id"),
        )
    except Exception as exc:
        logger.warning("Falha ao sincronizar esteira no Supabase: %s", exc)


def get_selected_stream_profile(cfg: dict) -> dict:
    selected_id = str(cfg.get("selected_stream_profile_id") or "").strip()
    profiles = cfg.get("stream_profiles", [])
    for profile in profiles:
        if profile.get("id") == selected_id:
            return profile
    if profiles:
        return profiles[0]
    profile = build_stream_profile({}, cfg, index=1)
    cfg["stream_profiles"] = [profile]
    return sync_config_with_selected_profile(cfg, profile)


class StreamProfileStore:
    def __init__(self, cfg: dict):
        normalized_cfg = normalize_config(cfg)
        cfg.clear()
        cfg.update(normalized_cfg)
        self.cfg = cfg

    def list_profiles(self) -> list[dict]:
        return [dict(profile) for profile in self.cfg.get("stream_profiles", [])]

    def get_selected_profile(self) -> dict:
        return dict(get_selected_stream_profile(self.cfg))

    def select_profile(self, profile_id: str) -> dict:
        for profile in self.cfg.get("stream_profiles", []):
            if profile.get("id") == profile_id:
                return dict(sync_config_with_selected_profile(self.cfg, profile))
        raise ValueError("Stream selecionada nao encontrada.")

    def delete_profile(self, profile_id: str) -> dict:
        target_id = str(profile_id or "").strip()
        profiles = self.cfg.get("stream_profiles", [])
        if len(profiles) <= 1:
            raise ValueError("A esteira precisa manter pelo menos uma stream salva.")

        selected_id = str(self.cfg.get("selected_stream_profile_id") or "").strip()
        if target_id == selected_id:
            raise ValueError("Carregue outra stream antes de apagar esta.")

        for index, profile in enumerate(profiles):
            if str(profile.get("id") or "") == target_id:
                deleted = dict(profile)
                del profiles[index]
                self.cfg["stream_profiles"] = profiles
                return deleted

        raise ValueError("Stream selecionada nao encontrada.")

    def save_selected_profile(
        self,
        *,
        name: str | None = None,
        camera_id: str | None = None,
        stream_url: str | None = None,
        roi: dict | None = None,
        line: dict | None = None,
        count_direction: str | None = None,
    ) -> dict:
        current = get_selected_stream_profile(self.cfg)
        target_url = validate_stream_url(stream_url or current.get("stream_url") or "")
        target_camera_id = str(camera_id or current.get("camera_id") or self.cfg.get("camera_id") or "").strip()
        if not target_url:
            raise ValueError("Informe uma URL de stream antes de salvar.")
        if not target_camera_id:
            raise ValueError("Informe um camera_id antes de salvar.")

        selected_stream_url = str(current.get("stream_url") or "").strip()
        selected_camera_id = str(current.get("camera_id") or "").strip()
        if target_url != selected_stream_url or target_camera_id != selected_camera_id:
            for profile in self.cfg.get("stream_profiles", []):
                if (
                    str(profile.get("stream_url") or "").strip() == target_url
                    and str(profile.get("camera_id") or "").strip() == target_camera_id
                ):
                    current = profile
                    break
            else:
                current = {
                    "id": make_stream_profile_id({str(profile.get("id") or "") for profile in self.cfg.get("stream_profiles", [])}),
                    "name": "",
                    "stream_url": target_url,
                    "camera_id": target_camera_id,
                    "roi": dict(self.cfg.get("roi") or DEFAULT_ROI),
                    "line": dict(self.cfg.get("line") or DEFAULT_LINE),
                    "count_direction": self.cfg.get("count_direction", "any"),
                }
                self.cfg.setdefault("stream_profiles", []).append(current)

        if name is not None:
            current["name"] = str(name).strip()
        current["stream_url"] = target_url
        current["camera_id"] = target_camera_id
        if roi is not None:
            current["roi"] = normalize_roi_config(roi, current.get("roi"))
        if line is not None:
            current["line"] = normalize_line_config(line, current.get("line"))
        if count_direction is not None:
            current["count_direction"] = normalize_count_direction(count_direction)

        return dict(sync_config_with_selected_profile(self.cfg, current))

    def save_profile_entry(
        self,
        *,
        name: str | None = None,
        camera_id: str | None = None,
        stream_url: str | None = None,
    ) -> tuple[dict, bool]:
        target_url = validate_stream_url(stream_url or "")
        target_camera_id = str(camera_id or "").strip()
        if not target_url:
            raise ValueError("Informe uma URL de stream antes de salvar.")
        if not target_camera_id:
            raise ValueError("Informe um camera_id antes de salvar.")

        current = None
        for profile in self.cfg.get("stream_profiles", []):
            if (
                str(profile.get("stream_url") or "").strip() == target_url
                and str(profile.get("camera_id") or "").strip() == target_camera_id
            ):
                current = profile
                break

        created = current is None
        if current is None:
            current = {
                "id": make_stream_profile_id({str(profile.get("id") or "") for profile in self.cfg.get("stream_profiles", [])}),
                "name": "",
                "stream_url": target_url,
                "camera_id": target_camera_id,
                "roi": dict(DEFAULT_ROI),
                "line": dict(DEFAULT_LINE),
                "count_direction": "any",
            }
            self.cfg.setdefault("stream_profiles", []).append(current)

        if name is not None:
            current["name"] = str(name).strip()
        if not current.get("name"):
            current["name"] = guess_stream_profile_name(target_url, target_camera_id)
        current["stream_url"] = target_url
        current["camera_id"] = target_camera_id

        return dict(current), created

    def apply_stream_url(
        self,
        stream_url: str,
        *,
        name: str | None = None,
        camera_id: str | None = None,
    ) -> tuple[dict, bool]:
        target_url = validate_stream_url(stream_url or "")
        target_camera_id = str(camera_id or self.cfg.get("camera_id") or "").strip()
        if not target_url:
            raise ValueError("Informe uma URL de stream.")
        if not target_camera_id:
            raise ValueError("Informe um camera_id.")

        for profile in self.cfg.get("stream_profiles", []):
            if (
                str(profile.get("stream_url") or "").strip() == target_url
                and str(profile.get("camera_id") or "").strip() == target_camera_id
            ):
                if name is not None and str(name).strip():
                    profile["name"] = str(name).strip()
                return dict(sync_config_with_selected_profile(self.cfg, profile)), False

        profile = {
            "id": make_stream_profile_id({str(existing.get("id") or "") for existing in self.cfg.get("stream_profiles", [])}),
            "name": str(name or "").strip()
            or guess_stream_profile_name(
                target_url,
                target_camera_id,
                index=len(self.cfg.get("stream_profiles", [])) + 1,
            ),
            "stream_url": target_url,
            "camera_id": target_camera_id,
            "roi": dict(DEFAULT_ROI),
            "line": dict(DEFAULT_LINE),
            "count_direction": "any",
        }
        self.cfg.setdefault("stream_profiles", []).append(profile)
        return dict(sync_config_with_selected_profile(self.cfg, profile)), True


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_round_sync(
    current_round_id: str,
    backend_round: dict | None,
    current_total: int,
) -> tuple[str, int, bool]:
    if not backend_round:
        return current_round_id, current_total, False

    backend_round_id = str(backend_round.get("roundId", "")).strip()
    if not backend_round_id:
        return current_round_id, current_total, False

    backend_total = int(backend_round.get("currentCount", 0) or 0)
    if backend_round_id != current_round_id:
        return backend_round_id, backend_total, True

    return backend_round_id, current_total, False


def normalize_ffmpeg_capture_options(options) -> str:
    if isinstance(options, str):
        return options.strip()

    if isinstance(options, dict):
        parts = []
        for key, value in options.items():
            parts.append(f"{key};{value}")
        return "|".join(parts)

    return ""


@dataclass(frozen=True)
class StreamUrlResolution:
    original_url: str
    capture_url: str
    resolved: bool = False


def is_blob_url(value: str) -> bool:
    return str(value or "").strip().lower().startswith("blob:")


def is_youtube_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    host = parsed.netloc.lower()
    return host.endswith("youtube.com") or host.endswith("youtu.be") or host.endswith("youtube-nocookie.com")


def validate_stream_url(value: str) -> str:
    stream_url = str(value or "").strip()
    if is_blob_url(stream_url):
        raise ValueError("URL blob do navegador nao pode ser usada. Cole a URL normal do YouTube.")
    return stream_url


def resolve_youtube_stream_url(stream_url: str, *, timeout_seconds: int = 20) -> str:
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-warnings",
        "--no-playlist",
        "-f",
        "best[protocol^=m3u8]/best",
        "-g",
        stream_url,
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=max(5, int(timeout_seconds)),
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"yt-dlp nao conseguiu resolver a URL do YouTube. {detail[:240]}")

    for line in (result.stdout or "").splitlines():
        candidate = line.strip()
        if candidate.startswith(("http://", "https://", "rtsp://", "rtmp://")):
            return candidate

    raise RuntimeError("yt-dlp nao retornou uma URL reproduzivel para esta stream.")


def resolve_stream_source_url(stream_url: str, cfg: dict | None = None) -> StreamUrlResolution:
    original_url = validate_stream_url(stream_url)
    if not original_url:
        return StreamUrlResolution(original_url="", capture_url="", resolved=False)

    if not is_youtube_url(original_url):
        return StreamUrlResolution(original_url=original_url, capture_url=original_url, resolved=False)

    timeout_seconds = int((cfg or {}).get("youtube_resolve_timeout_seconds", 20) or 20)
    capture_url = resolve_youtube_stream_url(original_url, timeout_seconds=timeout_seconds)
    return StreamUrlResolution(original_url=original_url, capture_url=capture_url, resolved=True)


def normalize_media_path_name(value: str, fallback: str = "cam_001") -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        raw = fallback
    normalized = []
    for char in raw:
        if char.isalnum() or char in {"-", "_"}:
            normalized.append(char)
        else:
            normalized.append("_")
    path_name = "".join(normalized).strip("_")
    return path_name or fallback


def ensure_mediamtx_source_path(cfg: dict, path_name: str, source_url: str) -> bool:
    api_base = str(cfg.get("mediamtx_api_url") or "").strip().rstrip("/")
    if not api_base or not path_name or not source_url:
        return False

    try:
        exists_response = requests.get(
            f"{api_base}/v3/paths/get/{path_name}",
            timeout=3,
        )
        if exists_response.ok:
            return True
    except Exception:
        pass

    try:
        response = requests.post(
            f"{api_base}/v3/config/paths/add/{path_name}",
            json={"source": source_url},
            timeout=5,
        )
        if response.ok:
            logger.info("Path MediaMTX garantido: %s -> %s", path_name, source_url)
            return True

        logger.warning(
            "Falha ao garantir path MediaMTX %s (HTTP %d): %s",
            path_name,
            response.status_code,
            response.text[:200],
        )
        return False
    except Exception as exc:
        logger.warning("Falha ao configurar source path no MediaMTX: %s", exc)
        return False


def remove_mediamtx_source_path(cfg: dict, path_name: str) -> bool:
    api_base = str(cfg.get("mediamtx_api_url") or "").strip().rstrip("/")
    if not api_base or not path_name:
        return False

    try:
        response = requests.delete(
            f"{api_base}/v3/config/paths/remove/{path_name}",
            timeout=5,
        )
        if response.ok or response.status_code == 404:
            logger.info(
                "Path MediaMTX removido para refresh: %s (status=%s)",
                path_name,
                response.status_code,
            )
            return True

        logger.warning(
            "Falha ao remover path MediaMTX %s (HTTP %d): %s",
            path_name,
            response.status_code,
            response.text[:200],
        )
        return False
    except Exception as exc:
        logger.warning("Falha ao remover path MediaMTX %s: %s", path_name, exc)
        return False


def build_pipeline_config(cfg: dict, *, source_url: str | None = None, camera_id: str | None = None,
    raw_stream_path: str | None = None, processed_stream_path: str | None = None) -> dict:
    pipeline_cfg = dict(cfg)
    normalized_camera_id = normalize_media_path_name(
        camera_id or cfg.get("camera_id", "") or "cam_001"
    )
    original_source_url = str(source_url or cfg.get("stream_url") or "").strip()
    resolved_source = resolve_stream_source_url(original_source_url, cfg)
    raw_path = str(raw_stream_path or f"raw/{normalized_camera_id}").strip()
    processed_path = str(processed_stream_path or f"processed/{normalized_camera_id}").strip()
    rtsp_base = str(cfg.get("mediamtx_rtsp_url") or "rtsp://localhost:8554").strip().rstrip("/")

    capture_source_url = resolved_source.capture_url
    if capture_source_url and ensure_mediamtx_source_path(cfg, raw_path, capture_source_url):
        capture_source_url = f"{rtsp_base}/{raw_path}"

    pipeline_cfg["camera_id"] = normalized_camera_id
    pipeline_cfg["raw_stream_path"] = raw_path
    pipeline_cfg["processed_stream_path"] = processed_path
    pipeline_cfg["stream_url"] = resolved_source.original_url
    pipeline_cfg["capture_source_url"] = capture_source_url
    pipeline_cfg["source_url_resolved"] = resolved_source.resolved
    pipeline_cfg["publisher_rtsp_url"] = f"{rtsp_base}/{processed_path}"
    pipeline_cfg.setdefault("publisher_fps", 10)
    pipeline_cfg.setdefault("publisher_ffmpeg_bin", "ffmpeg")
    return pipeline_cfg


def resize_frame_max_width(frame, max_width: int):
    max_width = int(max_width)
    if max_width <= 0:
        return frame

    height, width = frame.shape[:2]
    if width <= max_width:
        return frame

    scale = max_width / float(width)
    target_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)


def should_process_frame(frame_count: int, stride: int) -> bool:
    stride = max(1, int(stride))
    return frame_count == 1 or frame_count % stride == 0


def inside_roi(cx: int, cy: int, roi: dict) -> bool:
    return (
        roi["x"] <= cx <= roi["x"] + roi["w"]
        and roi["y"] <= cy <= roi["y"] + roi["h"]
    )


def crossed_horizontal_segment(
    prev_y: int,
    curr_y: int,
    line_y: int,
    cx: int,
    x1: int,
    x2: int,
    direction: str,
) -> bool:
    inside_segment = min(x1, x2) <= cx <= max(x1, x2)
    if not inside_segment:
        return False

    raw_direction = str(direction or "").strip().lower()
    if raw_direction not in {"up", "down", "any", "down_to_up", "up_to_down"}:
        return False

    direction = normalize_count_direction(direction)

    if direction == "down":
        return prev_y < line_y <= curr_y

    if direction == "up":
        return prev_y > line_y >= curr_y

    if direction == "any":
        return (prev_y < line_y <= curr_y) or (prev_y > line_y >= curr_y)

    return False


def crossed_vertical_segment(
    prev_x: int,
    curr_x: int,
    line_x: int,
    cy: int,
    y1: int,
    y2: int,
    direction: str,
) -> bool:
    inside_segment = min(y1, y2) <= cy <= max(y1, y2)
    if not inside_segment:
        return False

    raw_direction = str(direction or "").strip().lower()
    if raw_direction not in {"left", "right", "any", "left_to_right", "right_to_left"}:
        return False

    direction = normalize_count_direction(direction)

    if direction == "right":
        return prev_x < line_x <= curr_x

    if direction == "left":
        return prev_x > line_x >= curr_x

    if direction == "any":
        return (prev_x < line_x <= curr_x) or (prev_x > line_x >= curr_x)

    return False


def count_line_is_horizontal(line: dict) -> bool:
    return abs(int(line["x2"]) - int(line["x1"])) >= abs(int(line["y2"]) - int(line["y1"]))


def should_count_track(
    prev_position: tuple[int, int] | None,
    curr_position: tuple[int, int],
    line: dict,
    direction: str,
    hits: int,
    min_hits_to_count: int,
    already_counted: bool,
) -> bool:
    if prev_position is None or already_counted or hits < min_hits_to_count:
        return False

    prev_x, prev_y = prev_position
    curr_x, curr_y = curr_position

    if count_line_is_horizontal(line):
        return crossed_horizontal_segment(
            prev_y=prev_y,
            curr_y=curr_y,
            line_y=line["y1"],
            cx=curr_x,
            x1=line["x1"],
            x2=line["x2"],
            direction=direction,
        )

    return crossed_vertical_segment(
        prev_x=prev_x,
        curr_x=curr_x,
        line_x=line["x1"],
        cy=curr_y,
        y1=line["y1"],
        y2=line["y2"],
        direction=direction,
    )


def count_direction_display_name(direction: str) -> str:
    return {
        "any": "any",
        "up": "up",
        "down": "down",
        "left": "left",
        "right": "right",
    }.get(normalize_count_direction(direction), "any")


def anchor_point(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int]:
    return (int((x1 + x2) / 2), int(y2))


def clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(val, hi))


def build_class_names(allowed_classes: dict) -> dict[int, str]:
    return {v: k for k, v in allowed_classes.items()}


def is_countable_vehicle(vehicle_name: str) -> bool:
    return str(vehicle_name or "").strip().lower() == "car"


def bbox_area(x1: int, y1: int, x2: int, y2: int) -> int:
    return max(0, x2 - x1) * max(0, y2 - y1)


def annotate_frame(
    frame,
    roi: dict,
    line: dict,
    detections_list: list[dict],
    total: int,
    *,
    show_roi: bool = True,
    show_labels: bool = True,
    show_centers: bool = True,
    show_total: bool = True,
):
    annotated = frame.copy()

    cv2.line(
        annotated,
        (line["x1"], line["y1"]),
        (line["x2"], line["y2"]),
        (0, 0, 255),
        3,
    )

    if show_roi:
        cv2.rectangle(
            annotated,
            (roi["x"], roi["y"]),
            (roi["x"] + roi["w"], roi["y"] + roi["h"]),
            (255, 255, 0),
            2,
        )

    for det in detections_list:
        dx = det["bbox"]["x"]
        dy = det["bbox"]["y"]
        dw = det["bbox"]["w"]
        dh = det["bbox"]["h"]
        tid = det["trackId"]
        vtype = det["vehicleType"]
        color = (0, 255, 0) if det["counted"] else (0, 165, 255)

        cv2.rectangle(annotated, (dx, dy), (dx + dw, dy + dh), color, 2)
        if show_labels:
            cv2.putText(
                annotated,
                f"#{tid} {vtype}",
                (dx, dy - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
            )

        if show_centers:
            cx_d = det["center"]["x"]
            cy_d = det["center"]["y"]
            cv2.circle(annotated, (cx_d, cy_d), 4, (0, 0, 255), -1)

    if show_total:
        cv2.putText(
            annotated,
            f"TOTAL: {total}",
            (30, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (0, 255, 0),
            3,
        )

    return annotated


class ConfigEditor:
    HANDLE_RADIUS = 10
    LINE_HIT_TOLERANCE = 12

    def __init__(self, roi: dict, line: dict):
        self.mode = "idle"
        self.message = "R: ROI | L: line | S: save | C: cancel | Q: quit"
        self.roi = dict(roi)
        self.line = dict(line)
        self._saved_roi = dict(roi)
        self._saved_line = dict(line)
        self._drag_action = None
        self._drag_start = None
        self._roi_start = None
        self._line_start = None
        self._frame_w = 0
        self._frame_h = 0
        self.dirty = False

    def set_frame_size(self, width: int, height: int):
        self._frame_w = width
        self._frame_h = height

    def sync_external_values(self, roi: dict, line: dict):
        if self.dirty or self.mode != "idle":
            return
        self.roi = dict(roi)
        self.line = dict(line)
        self._saved_roi = dict(roi)
        self._saved_line = dict(line)

    def load_values(self, roi: dict, line: dict, message: str | None = None):
        self.mode = "idle"
        self.roi = dict(roi)
        self.line = dict(line)
        self._saved_roi = dict(roi)
        self._saved_line = dict(line)
        self.dirty = False
        self._reset_drag()
        self.message = message or "Stream config loaded"

    def begin_roi_mode(self):
        self.mode = "roi"
        self._reset_drag()
        self.message = "ROI mode: drag corners, drag inside to move, drag empty area to create"

    def begin_line_mode(self):
        self.mode = "line"
        self._reset_drag()
        self.message = "Line mode: drag endpoints, drag line to move, drag empty area to create"

    def clear_mode(self):
        self.mode = "idle"
        self._reset_drag()
        self.message = "Edit mode cleared"

    def cancel(self):
        self.mode = "idle"
        self.roi = dict(self._saved_roi)
        self.line = dict(self._saved_line)
        self.dirty = False
        self._reset_drag()
        self.message = "Changes canceled"

    def save(self, cfg: dict, path: str):
        cfg["roi"] = dict(self.roi)
        cfg["line"] = dict(self.line)
        save_config(path, cfg)
        self._saved_roi = dict(self.roi)
        self._saved_line = dict(self.line)
        self.dirty = False
        self.mode = "idle"
        self._reset_drag()
        self.message = f"Saved to {path}"

    def handle_mouse(self, event, x: int, y: int, _flags, _param):
        x = clamp(x, 0, max(self._frame_w - 1, 0))
        y = clamp(y, 0, max(self._frame_h - 1, 0))

        if self.mode == "roi":
            self._handle_roi_mouse(event, x, y)
        elif self.mode == "line":
            self._handle_line_mouse(event, x, y)

    def draw_overlay(self, frame):
        cv2.putText(
            frame,
            f"EDIT: {self.mode.upper()}",
            (30, 85),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
        )
        cv2.putText(
            frame,
            self.message[:90],
            (30, 115),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
        )

        for hx, hy in self._roi_handles():
            cv2.circle(frame, (hx, hy), 6, (255, 255, 0), -1)

        cv2.circle(frame, (self.line["x1"], self.line["y1"]), 7, (0, 0, 255), -1)
        cv2.circle(frame, (self.line["x2"], self.line["y2"]), 7, (0, 0, 255), -1)

    def _handle_roi_mouse(self, event, x: int, y: int):
        if event == cv2.EVENT_LBUTTONDOWN:
            handle = self._hit_test_roi_handle(x, y)
            if handle is not None:
                self._drag_action = ("roi_handle", handle)
            elif self._point_in_roi(x, y, self.roi):
                self._drag_action = ("roi_move", None)
            else:
                self._drag_action = ("roi_new", None)
                self.roi = {"x": x, "y": y, "w": 0, "h": 0}
            self._drag_start = (x, y)
            self._roi_start = dict(self.roi)
            return

        if event == cv2.EVENT_MOUSEMOVE and self._drag_action and self._drag_start:
            start_x, start_y = self._drag_start
            action, handle = self._drag_action
            if action == "roi_new":
                self.roi = self._normalize_roi(
                    {"x": start_x, "y": start_y, "w": x - start_x, "h": y - start_y}
                )
            elif action == "roi_move" and self._roi_start is not None:
                dx = x - start_x
                dy = y - start_y
                self.roi = self._clamp_roi(
                    {
                        "x": self._roi_start["x"] + dx,
                        "y": self._roi_start["y"] + dy,
                        "w": self._roi_start["w"],
                        "h": self._roi_start["h"],
                    }
                )
            elif action == "roi_handle" and handle and self._roi_start is not None:
                self.roi = self._resize_roi(handle, x, y, self._roi_start)
            self.dirty = True
            return

        if event == cv2.EVENT_LBUTTONUP:
            self.roi = self._clamp_roi(self._normalize_roi(self.roi))
            self._reset_drag()
            self.message = "ROI updated. Press S to save or C to cancel"

    def _handle_line_mouse(self, event, x: int, y: int):
        if event == cv2.EVENT_LBUTTONDOWN:
            handle = self._hit_test_line_handle(x, y)
            if handle is not None:
                self._drag_action = ("line_handle", handle)
            elif self._point_near_line(x, y):
                self._drag_action = ("line_move", None)
            else:
                self._drag_action = ("line_new", None)
                self.line = {"x1": x, "y1": y, "x2": x, "y2": y}
            self._drag_start = (x, y)
            self._line_start = dict(self.line)
            return

        if event == cv2.EVENT_MOUSEMOVE and self._drag_action and self._drag_start:
            start_x, start_y = self._drag_start
            action, handle = self._drag_action
            if action == "line_new" and self._line_start is not None:
                self.line = {
                    "x1": self._line_start["x1"],
                    "y1": self._line_start["y1"],
                    "x2": x,
                    "y2": y,
                }
            elif action == "line_move" and self._line_start is not None:
                dx = x - start_x
                dy = y - start_y
                self.line = self._clamp_line(
                    {
                        "x1": self._line_start["x1"] + dx,
                        "y1": self._line_start["y1"] + dy,
                        "x2": self._line_start["x2"] + dx,
                        "y2": self._line_start["y2"] + dy,
                    }
                )
            elif action == "line_handle" and handle and self._line_start is not None:
                next_line = dict(self._line_start)
                next_line[handle] = x
                next_line["y" + handle[1]] = y
                self.line = self._clamp_line(next_line)
            self.dirty = True
            return

        if event == cv2.EVENT_LBUTTONUP:
            self.line = self._clamp_line(self.line)
            self._reset_drag()
            self.message = "Line updated. Press S to save or C to cancel"

    def _roi_handles(self) -> list[tuple[int, int]]:
        return [
            (self.roi["x"], self.roi["y"]),
            (self.roi["x"] + self.roi["w"], self.roi["y"]),
            (self.roi["x"], self.roi["y"] + self.roi["h"]),
            (self.roi["x"] + self.roi["w"], self.roi["y"] + self.roi["h"]),
        ]

    def _hit_test_roi_handle(self, x: int, y: int) -> str | None:
        labels = ["tl", "tr", "bl", "br"]
        for label, (hx, hy) in zip(labels, self._roi_handles()):
            if abs(x - hx) <= self.HANDLE_RADIUS and abs(y - hy) <= self.HANDLE_RADIUS:
                return label
        return None

    def _hit_test_line_handle(self, x: int, y: int) -> str | None:
        if abs(x - self.line["x1"]) <= self.HANDLE_RADIUS and abs(y - self.line["y1"]) <= self.HANDLE_RADIUS:
            return "x1"
        if abs(x - self.line["x2"]) <= self.HANDLE_RADIUS and abs(y - self.line["y2"]) <= self.HANDLE_RADIUS:
            return "x2"
        return None

    def _point_in_roi(self, x: int, y: int, roi: dict) -> bool:
        return roi["x"] <= x <= roi["x"] + roi["w"] and roi["y"] <= y <= roi["y"] + roi["h"]

    def _point_near_line(self, x: int, y: int) -> bool:
        x1 = self.line["x1"]
        y1 = self.line["y1"]
        x2 = self.line["x2"]
        y2 = self.line["y2"]
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return abs(x - x1) <= self.LINE_HIT_TOLERANCE and abs(y - y1) <= self.LINE_HIT_TOLERANCE
        t = ((x - x1) * dx + (y - y1) * dy) / float(dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        return ((x - proj_x) ** 2 + (y - proj_y) ** 2) ** 0.5 <= self.LINE_HIT_TOLERANCE

    def _normalize_roi(self, roi: dict) -> dict:
        x1 = roi["x"]
        y1 = roi["y"]
        x2 = roi["x"] + roi["w"]
        y2 = roi["y"] + roi["h"]
        left = min(x1, x2)
        top = min(y1, y2)
        right = max(x1, x2)
        bottom = max(y1, y2)
        return {"x": left, "y": top, "w": right - left, "h": bottom - top}

    def _clamp_roi(self, roi: dict) -> dict:
        roi = dict(roi)
        roi["w"] = max(0, roi["w"])
        roi["h"] = max(0, roi["h"])
        roi["x"] = clamp(roi["x"], 0, max(self._frame_w - roi["w"], 0))
        roi["y"] = clamp(roi["y"], 0, max(self._frame_h - roi["h"], 0))
        roi["w"] = min(roi["w"], max(self._frame_w - roi["x"], 0))
        roi["h"] = min(roi["h"], max(self._frame_h - roi["y"], 0))
        return roi

    def _resize_roi(self, handle: str, x: int, y: int, base_roi: dict) -> dict:
        left = base_roi["x"]
        top = base_roi["y"]
        right = base_roi["x"] + base_roi["w"]
        bottom = base_roi["y"] + base_roi["h"]

        if "l" in handle:
            left = x
        else:
            right = x

        if "t" in handle:
            top = y
        else:
            bottom = y

        return self._clamp_roi(
            self._normalize_roi(
                {"x": left, "y": top, "w": right - left, "h": bottom - top}
            )
        )

    def _clamp_line(self, line: dict) -> dict:
        return {
            "x1": clamp(line["x1"], 0, max(self._frame_w - 1, 0)),
            "y1": clamp(line["y1"], 0, max(self._frame_h - 1, 0)),
            "x2": clamp(line["x2"], 0, max(self._frame_w - 1, 0)),
            "y2": clamp(line["y2"], 0, max(self._frame_h - 1, 0)),
        }

    def _reset_drag(self):
        self._drag_action = None
        self._drag_start = None
        self._roi_start = None
        self._line_start = None


class EditorControlPanel:
    def __init__(
        self,
        editor: ConfigEditor,
        stream_store: StreamProfileStore,
        on_save,
        on_reset_stream,
        on_select_stream,
        on_open_stream,
        on_save_stream_profile,
        on_delete_stream_profile,
        on_force_stream_switch,
        on_set_count_direction,
        on_toggle_stream_rotation,
        on_queue_random_stream,
        stream_rotation_enabled: bool = False,
    ):
        self.editor = editor
        self.stream_store = stream_store
        self.on_save = on_save
        self.on_reset_stream = on_reset_stream
        self.on_select_stream = on_select_stream
        self.on_open_stream = on_open_stream
        self.on_save_stream_profile = on_save_stream_profile
        self.on_delete_stream_profile = on_delete_stream_profile
        self.on_force_stream_switch = on_force_stream_switch
        self.on_set_count_direction = on_set_count_direction
        self.on_toggle_stream_rotation = on_toggle_stream_rotation
        self.on_queue_random_stream = on_queue_random_stream
        self.should_close = False
        self._stream_profile_ids: list[str] = []
        self._root = tk.Tk()
        self._root.title("Controles de Configuracao")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self.request_close)

        frame = ttk.Frame(self._root, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Esteira de Streams", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        self._stream_name_var = tk.StringVar()
        self._stream_camera_id_var = tk.StringVar()
        self._stream_url_var = tk.StringVar()
        self._count_direction_var = tk.StringVar(value="any")
        self._stream_rotation_enabled_var = tk.BooleanVar(value=bool(stream_rotation_enabled))
        self._stream_selector = ttk.Combobox(frame, state="readonly", width=48)
        self._stream_selector.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        self._stream_selector.bind("<<ComboboxSelected>>", self._handle_profile_preview)
        ttk.Button(frame, text="Carregar", command=self.load_selected_stream).grid(
            row=1, column=1, sticky="ew", pady=(0, 6)
        )
        self._stream_table = ttk.Treeview(
            frame,
            columns=("active", "name", "camera_id", "url"),
            show="headings",
            height=5,
            selectmode="browse",
        )
        self._stream_table.heading("active", text="")
        self._stream_table.heading("name", text="Stream")
        self._stream_table.heading("camera_id", text="Camera ID")
        self._stream_table.heading("url", text="URL")
        self._stream_table.column("active", width=24, minwidth=24, stretch=False, anchor="center")
        self._stream_table.column("name", width=130, minwidth=90, stretch=False)
        self._stream_table.column("camera_id", width=92, minwidth=80, stretch=False)
        self._stream_table.column("url", width=190, minwidth=120, stretch=True)
        self._stream_table.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._stream_table.bind("<<TreeviewSelect>>", self._handle_profile_table_select)

        ttk.Label(frame, text="Apelido da stream").grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Entry(frame, textvariable=self._stream_name_var).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        ttk.Label(frame, text="Camera ID").grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Entry(frame, textvariable=self._stream_camera_id_var).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        ttk.Label(frame, text="URL da stream").grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Entry(frame, textvariable=self._stream_url_var).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Abrir URL", command=self.open_stream_url).grid(
            row=9, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(frame, text="Salvar na Esteira", command=self.save_stream_profile).grid(
            row=9, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Apagar da Esteira", command=self.delete_stream_profile).grid(
            row=10, column=0, columnspan=2, sticky="ew", pady=(0, 10)
        )
        ttk.Button(frame, text="Forcar Troca", command=self.force_stream_switch).grid(
            row=11, column=0, columnspan=2, sticky="ew", pady=(0, 10)
        )

        ttk.Label(frame, text="Rotacao Randômica", font=("Segoe UI", 11, "bold")).grid(
            row=12, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Checkbutton(
            frame,
            text="Ativar entre rounds",
            variable=self._stream_rotation_enabled_var,
            command=self.toggle_stream_rotation,
        ).grid(
            row=13, column=0, sticky="w", padx=(0, 6), pady=(0, 10)
        )
        ttk.Button(frame, text="Sortear Proxima", command=self.queue_random_stream).grid(
            row=13, column=1, sticky="ew", pady=(0, 10)
        )

        ttk.Label(frame, text="Ajuste de ROI e Linha", font=("Segoe UI", 11, "bold")).grid(
            row=14, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Label(frame, text="Direcao de contagem").grid(row=15, column=0, columnspan=2, sticky="w")
        self._count_direction_selector = ttk.Combobox(
            frame,
            state="readonly",
            values=("any", "up", "down", "left", "right"),
            textvariable=self._count_direction_var,
        )
        self._count_direction_selector.grid(
            row=16, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        self._count_direction_selector.bind("<<ComboboxSelected>>", self._handle_direction_change)

        ttk.Button(frame, text="Editar ROI", command=self.editor.begin_roi_mode).grid(
            row=17, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(frame, text="Editar Linha", command=self.editor.begin_line_mode).grid(
            row=17, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Salvar", command=self.save).grid(
            row=18, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(frame, text="Cancelar", command=self.cancel).grid(
            row=18, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Resetar Stream", command=self.reset_stream).grid(
            row=19, column=0, columnspan=2, sticky="ew"
        )
        ttk.Button(frame, text="Fechar", command=self.request_close).grid(
            row=20, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )

        self._mode_var = tk.StringVar(value=f"Modo: {self.editor.mode}")
        self._message_var = tk.StringVar(value=self.editor.message)
        ttk.Label(frame, textvariable=self._mode_var).grid(
            row=21, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Label(frame, textvariable=self._message_var, wraplength=360).grid(
            row=22, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )

        ttk.Label(frame, text="Atalhos opcionais: R, L, S, C, T, Q").grid(
            row=23, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        self._refresh_stream_profiles()
        self.set_active_stream_profile(self.stream_store.get_selected_profile())

    def refresh(self):
        self._mode_var.set(f"Modo: {self.editor.mode}")
        self._message_var.set(self.editor.message)
        try:
            self._root.update_idletasks()
            self._root.update()
        except tk.TclError:
            self.should_close = True

    def save(self):
        self._commit_count_direction()
        self.on_save()
        self.set_active_stream_profile(self.stream_store.get_selected_profile())

    def cancel(self):
        self.editor.cancel()

    def reset_stream(self):
        self.on_reset_stream()

    def load_selected_stream(self):
        profile_id = self._get_selected_stream_profile_id()
        if not profile_id:
            self.editor.message = "Selecione uma stream salva na esteira."
            return

        try:
            profile = self.on_select_stream(profile_id)
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return

        self.set_active_stream_profile(profile)

    def open_stream_url(self):
        try:
            profile = self.on_open_stream(
                self._stream_url_var.get(),
                self._stream_name_var.get(),
                self._stream_camera_id_var.get(),
            )
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return

        self.set_active_stream_profile(profile)

    def save_stream_profile(self):
        try:
            self._commit_count_direction()
            profile = self.on_save_stream_profile(
                self._stream_name_var.get(),
                self._stream_url_var.get(),
                self._stream_camera_id_var.get(),
            )
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return

        self.set_active_stream_profile(profile)

    def delete_stream_profile(self):
        profile_id = self._get_selected_stream_profile_id()
        if not profile_id:
            self.editor.message = "Selecione uma stream salva na esteira."
            return

        try:
            deleted = self.on_delete_stream_profile(profile_id)
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return

        self._refresh_stream_profiles()
        self.editor.message = f"Stream apagada da esteira: {format_stream_profile_label(deleted)}"

    def force_stream_switch(self):
        try:
            self._commit_count_direction()
            profile = self.on_force_stream_switch(
                self._get_selected_stream_profile_id(),
                self._stream_name_var.get(),
                self._stream_url_var.get(),
                self._stream_camera_id_var.get(),
            )
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return

        self.set_active_stream_profile(profile)

    def toggle_stream_rotation(self):
        try:
            self.on_toggle_stream_rotation(bool(self._stream_rotation_enabled_var.get()))
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)

    def refresh_stream_profiles(self, selected_profile_id: str | None = None):
        self._refresh_stream_profiles(selected_profile_id=selected_profile_id)

    def queue_random_stream(self):
        try:
            profile = self.on_queue_random_stream()
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return

        if profile:
            self._refresh_stream_profiles(selected_profile_id=profile.get("id"))

    def set_active_stream_profile(self, profile: dict):
        self._refresh_stream_profiles(selected_profile_id=profile.get("id"))
        self._stream_name_var.set(str(profile.get("name") or ""))
        self._stream_camera_id_var.set(str(profile.get("camera_id") or ""))
        self._stream_url_var.set(str(profile.get("stream_url") or ""))
        self._count_direction_var.set(count_direction_display_name(str(profile.get("count_direction") or "any")))

    def _refresh_stream_profiles(self, selected_profile_id: str | None = None):
        profiles = self.stream_store.list_profiles()
        self._stream_profile_ids = [str(profile.get("id") or "") for profile in profiles]
        self._stream_selector["values"] = [format_stream_profile_label(profile) for profile in profiles]

        active_id = str(self.stream_store.get_selected_profile().get("id") or "")
        target_id = selected_profile_id or active_id
        for item_id in self._stream_table.get_children():
            self._stream_table.delete(item_id)
        for profile in profiles:
            profile_id = str(profile.get("id") or "")
            self._stream_table.insert(
                "",
                "end",
                iid=profile_id,
                values=format_stream_profile_table_row(profile, active=profile_id == active_id),
            )

        if target_id in self._stream_profile_ids:
            self._stream_selector.current(self._stream_profile_ids.index(target_id))
            self._stream_table.selection_set(target_id)
            self._stream_table.focus(target_id)
            self._stream_table.see(target_id)
        elif self._stream_profile_ids:
            self._stream_selector.current(0)
            self._stream_table.selection_set(self._stream_profile_ids[0])
            self._stream_table.focus(self._stream_profile_ids[0])

    def _handle_profile_preview(self, _event=None):
        index = self._stream_selector.current()
        if index < 0 or index >= len(self._stream_profile_ids):
            return

        profile_id = self._stream_profile_ids[index]
        if profile_id in self._stream_table.get_children():
            self._stream_table.selection_set(profile_id)
            self._stream_table.focus(profile_id)
        for profile in self.stream_store.list_profiles():
            if str(profile.get("id") or "") == profile_id:
                self._stream_name_var.set(str(profile.get("name") or ""))
                self._stream_camera_id_var.set(str(profile.get("camera_id") or ""))
                self._stream_url_var.set(str(profile.get("stream_url") or ""))
                self._count_direction_var.set(count_direction_display_name(str(profile.get("count_direction") or "any")))
                break

    def _handle_profile_table_select(self, _event=None):
        profile_id = self._get_selected_stream_profile_id()
        if not profile_id:
            return
        if profile_id in self._stream_profile_ids:
            self._stream_selector.current(self._stream_profile_ids.index(profile_id))
        for profile in self.stream_store.list_profiles():
            if str(profile.get("id") or "") == profile_id:
                self._stream_name_var.set(str(profile.get("name") or ""))
                self._stream_camera_id_var.set(str(profile.get("camera_id") or ""))
                self._stream_url_var.set(str(profile.get("stream_url") or ""))
                self._count_direction_var.set(count_direction_display_name(str(profile.get("count_direction") or "any")))
                break

    def _handle_direction_change(self, _event=None):
        self._commit_count_direction()

    def _commit_count_direction(self):
        direction = normalize_count_direction(self._count_direction_var.get())
        self._count_direction_var.set(count_direction_display_name(direction))
        self.on_set_count_direction(direction)

    def _get_selected_stream_profile_id(self) -> str:
        table_selection = self._stream_table.selection()
        if table_selection:
            return str(table_selection[0])
        index = self._stream_selector.current()
        if 0 <= index < len(self._stream_profile_ids):
            return self._stream_profile_ids[index]
        return ""

    def request_close(self):
        self.should_close = True

    def close(self):
        try:
            self._root.destroy()
        except tk.TclError:
            pass


# ---------------------------------------------------------------------------
# Stream com reconexão automática
# ---------------------------------------------------------------------------
class StreamCapture:
    MAX_FAILURES = 30
    LIVE_EDGE_DRAIN_SECONDS = 1.25
    LIVE_EDGE_MAX_FRAMES = 60
    LIVE_EDGE_SLOW_READ_MS = 120.0

    def __init__(
        self,
        url: str,
        stats: RuntimeStats | None = None,
        *,
        ffmpeg_options=None,
        buffer_size: int = 1,
        open_timeout_ms: int = 5000,
        read_timeout_ms: int = 5000,
        target_fps: float = 0.0,
    ):
        self.url = url
        self.stats = stats
        self.cap: cv2.VideoCapture | None = None
        self._fail_count = 0
        self.ffmpeg_options = normalize_ffmpeg_capture_options(ffmpeg_options)
        self.buffer_size = max(1, int(buffer_size))
        self.open_timeout_ms = max(0, int(open_timeout_ms))
        self.read_timeout_ms = max(0, int(read_timeout_ms))
        self.target_fps = max(0.0, float(target_fps))
        self._effective_fps = 0.0
        self._reset_requested = False
        self._refresh_latest_requested = False
        self._connect()

    def _connect(self):
        if self.cap is not None:
            self.cap.release()

        if self.ffmpeg_options:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = self.ffmpeg_options

        logger.info("Conectando ao stream: %s", self.url)
        if self.ffmpeg_options:
            logger.info("FFmpeg capture options: %s", self.ffmpeg_options)
        self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)
        except Exception:
            pass
        try:
            if self.open_timeout_ms > 0:
                self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.open_timeout_ms)
        except Exception:
            pass
        try:
            if self.read_timeout_ms > 0:
                self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout_ms)
        except Exception:
            pass
        self._fail_count = 0
        if self.stats is not None:
            self.stats.set_stream_status(self.cap.isOpened(), self._fail_count)
        reported_fps = 0.0
        try:
            reported_fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        except Exception:
            reported_fps = 0.0

        if self.target_fps > 0:
            self._effective_fps = self.target_fps
        elif 1.0 <= reported_fps <= 120.0:
            self._effective_fps = reported_fps
        else:
            self._effective_fps = 15.0

        logger.info(
            "Pacing do stream: fps configurado=%.2f | fps detectado=%.2f | fps efetivo=%.2f",
            self.target_fps,
            reported_fps,
            self._effective_fps,
        )

        if not self.cap.isOpened():
            logger.warning("Falha ao abrir stream na conexão inicial.")

    def read(self):
        if self._refresh_latest_requested:
            self._refresh_latest_requested = False
            self._reset_requested = False
            self._connect()
            return self._read_most_recent_frame()

        if self._reset_requested:
            self._reset_requested = False
            self._connect()

        ret, frame = self.cap.read()
        if not ret:
            self._fail_count += 1
            if self.stats is not None:
                self.stats.set_stream_status(False, self._fail_count)

            if self._fail_count >= self.MAX_FAILURES:
                logger.warning("Stream perdido — reconectando...")
                self._connect()

            return False, None

        self._fail_count = 0
        if self.stats is not None:
            self.stats.set_stream_status(True, self._fail_count)
        return True, frame

    def _read_most_recent_frame(self):
        if self.cap is None:
            return False, None

        deadline = time.perf_counter() + self.LIVE_EDGE_DRAIN_SECONDS
        last_frame = None
        drained_frames = 0

        while drained_frames < self.LIVE_EDGE_MAX_FRAMES and time.perf_counter() < deadline:
            read_started = time.perf_counter()
            ret, frame = self.cap.read()
            read_elapsed_ms = (time.perf_counter() - read_started) * 1000.0

            if not ret:
                break

            last_frame = frame
            drained_frames += 1

            # Reads that stay "fast" usually indicate buffered backlog.
            # Once the read starts blocking, we are likely near the live edge.
            if read_elapsed_ms >= self.LIVE_EDGE_SLOW_READ_MS:
                break

        if last_frame is not None:
            logger.info(
                "Atualizacao para frame mais atual concluida | frames descartados: %s",
                max(0, drained_frames - 1),
            )
            self._fail_count = 0
            if self.stats is not None:
                self.stats.set_stream_status(True, self._fail_count)
            return True, last_frame

        if self.stats is not None:
            self.stats.set_stream_status(False, self._fail_count)
        return False, None

    def request_reset(self):
        logger.info("Reset manual do stream solicitado.")
        self._reset_requested = True

    def request_refresh_latest(self):
        logger.info("Atualizacao manual para o frame mais atual solicitada.")
        self._refresh_latest_requested = True

    def release(self):
        if self.cap:
            self.cap.release()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
LIVE_SEND_INTERVAL = 0.2
CONFIG_POLL_INTERVAL = 10
ROUND_SYNC_INTERVAL = 1
WINDOW_NAME = "Traffic Counter"


def poll_window_key(delay_ms: int = 1) -> int:
    if hasattr(cv2, "pollKey"):
        key = cv2.pollKey()
        return key if key != -1 else -1
    return cv2.waitKey(delay_ms)


def main():
    global backend_client_ref, mjpeg_token_ref, active_stream_ref, active_mjpeg_server_ref, active_control_panel_ref, active_snapshot_writer_ref

    config_path = "config.json"
    cfg = load_config(config_path)
    supabase_sync = SupabaseStreamProfileSync.from_config(cfg)
    if supabase_sync is not None:
        logger.info(
            "Sincronizacao Supabase ativa | table=%s | scope=%s",
            supabase_sync.table,
            supabase_sync.scope,
        )
    bootstrap_stream_profiles_from_supabase(cfg, config_path, supabase_sync)
    stream_store = StreamProfileStore(cfg)
    stream_rotation = cfg["stream_rotation"]
    selected_profile = stream_store.get_selected_profile()
    if stream_rotation.get("enabled") and ensure_stream_rotation_profile_state(
        stream_rotation,
        str(selected_profile.get("id") or ""),
        rng=random,
    ):
        cfg["stream_rotation"] = dict(stream_rotation)
        save_config(config_path, cfg)
    update_stream_rotation_status(
        enabled=bool(stream_rotation.get("enabled")),
        mode=stream_rotation.get("mode", "round_boundary"),
        strategy=stream_rotation.get("strategy", "uniform_excluding_current"),
        pending=False,
        pendingProfileId="",
        roundsOnCurrentStream=int(stream_rotation.get("rounds_on_current_stream", 0) or 0),
        targetRoundsForCurrentStream=int(stream_rotation.get("target_rounds_for_current_stream", 0) or 0),
        currentStreamProfileId=str(stream_rotation.get("current_stream_profile_id") or ""),
        lastCountedRoundId=str(stream_rotation.get("last_counted_round_id") or ""),
        selectedStreamProfileId=str(selected_profile.get("id") or ""),
        activeProfileLabel=format_stream_profile_label(selected_profile),
        lastMessage="",
    )
    initial_camera_id = str(cfg.get("camera_id") or selected_profile.get("camera_id") or "").strip()
    initial_profile_id = str(selected_profile.get("id") or cfg.get("selected_stream_profile_id") or "").strip()
    initial_processed_path = str(cfg.get("processed_stream_path") or f"processed/{initial_camera_id}" if initial_camera_id else "").strip()
    initial_profile_label = format_stream_profile_label(selected_profile) if selected_profile else initial_camera_id
    update_camera_activation_status(
        phase="ready",
        requestedCameraId=initial_camera_id,
        readyCameraId=initial_camera_id,
        requestedStreamProfileId=initial_profile_id,
        readyStreamProfileId=initial_profile_id,
        requestedProcessedStreamPath=initial_processed_path,
        readyProcessedStreamPath=initial_processed_path,
        requestedProfileLabel=initial_profile_label,
        readyProfileLabel=initial_profile_label,
        readyForRounds=True,
    )
    streamer.set_jpeg_quality(int(cfg.get("mjpeg_jpeg_quality", 70)))
    streamer.set_fps_limit(float(cfg.get("mjpeg_fps_limit", 0)))

    os.makedirs(cfg["snapshot_dir"], exist_ok=True)

    model = YOLO(cfg["model"])
    backend = BackendClient(
        cfg["backend_url"],
        cfg["api_key"],
        session_id=cfg.get("session_id", ""),
        count_direction=cfg.get("count_direction", "down_to_up"),
        line_id=cfg.get("line_id", "main-line"),
    )
    round_sync_enabled = bool(str(cfg.get("session_id", "")).strip())
    backend_client_ref = backend
    mjpeg_token_ref = str(cfg.get("mjpeg_token", "")).strip()
    snapshot_writer = AsyncSnapshotWriter(
        queue_size=int(cfg.get("snapshot_queue_size", 32)),
        jpeg_quality=int(cfg.get("snapshot_jpeg_quality", 85)),
    )
    active_snapshot_writer_ref = snapshot_writer
    mjpeg_server = run_mjpeg_server(
        host=cfg.get("mjpeg_host", "0.0.0.0"),
        port=int(cfg.get("mjpeg_port", 8090)),
    )
    active_mjpeg_server_ref = mjpeg_server
    try:
        current_pipeline_cfg = build_pipeline_config(cfg)
        pipeline_runtime.start(current_pipeline_cfg)
    except Exception as exc:
        logger.warning("Pipeline inicial nao iniciada: %s", exc)
        current_pipeline_cfg = dict(cfg)
    active_stream_ref = None

    class_names = build_class_names(cfg["allowed_classes"])

    last_positions: dict[int, tuple[int, int]] = {}
    last_seen: dict[int, int] = {}
    track_hits: dict[int, int] = {}
    counted_ids: set[int] = set()

    total = 0
    frame_count = 0
    last_raw_seq = 0
    last_live_send = 0.0
    last_config_poll = 0.0
    last_round_sync = 0.0
    last_track_results = None

    roi = cfg["roi"]
    line = cfg["line"]
    count_direction = cfg["count_direction"]
    min_hits_to_count = int(cfg.get("min_hits_to_count", 4))
    max_track_history_age = int(cfg.get("max_track_history_age", 300))
    min_bbox_area = int(cfg.get("min_bbox_area", 100))
    imgsz = int(cfg.get("imgsz", 416))
    inference_frame_stride = int(cfg.get("inference_frame_stride", 1))
    browser_stream_max_width = int(cfg.get("browser_stream_max_width", 960))
    operator_preview_max_width = int(cfg.get("operator_preview_max_width", 1280))
    operator_preview_fps_limit = float(cfg.get("operator_preview_fps_limit", 12))
    editor = None
    control_panel = None
    pending_stream_profile = None
    pending_camera_activation = None
    pending_rotation_profile = None
    last_rotation_round_id = ""
    rotation_boundary_consumed = False
    pending_stream_refresh_started_at = None
    youtube_retry_after = 0.0
    current_round_id = str(cfg.get("round_id", "")).strip()
    last_visual_detections: list[dict] = []
    last_operator_preview = None
    last_operator_preview_at = 0.0

    original_model_track = model.track

    def track_with_stride(*args, **kwargs):
        nonlocal last_track_results

        if (
            inference_frame_stride > 1
            and not should_process_frame(frame_count, inference_frame_stride)
            and last_track_results is not None
        ):
            return last_track_results

        last_track_results = original_model_track(*args, **kwargs)
        return last_track_results

    model.track = track_with_stride

    def reset_tracking_state():
        nonlocal total

        total = 0
        last_positions.clear()
        last_seen.clear()
        track_hits.clear()
        counted_ids.clear()

    def publish_rotation_status(message: str = ""):
        selected = stream_store.get_selected_profile()
        update_stream_rotation_status(
            enabled=bool(stream_rotation.get("enabled")),
            mode=stream_rotation.get("mode", "round_boundary"),
            strategy=stream_rotation.get("strategy", "uniform_excluding_current"),
            pending=isinstance(pending_rotation_profile, dict),
            pendingProfileId=str((pending_rotation_profile or {}).get("id") or ""),
            roundsOnCurrentStream=int(stream_rotation.get("rounds_on_current_stream", 0) or 0),
            targetRoundsForCurrentStream=int(stream_rotation.get("target_rounds_for_current_stream", 0) or 0),
            currentStreamProfileId=str(stream_rotation.get("current_stream_profile_id") or ""),
            lastCountedRoundId=str(stream_rotation.get("last_counted_round_id") or ""),
            selectedStreamProfileId=str(selected.get("id") or ""),
            activeProfileLabel=format_stream_profile_label(selected),
            lastMessage=message,
        )

    def set_rotation_enabled(enabled: bool):
        stream_rotation["enabled"] = bool(enabled)
        if enabled:
            ensure_stream_rotation_profile_state(
                stream_rotation,
                str(cfg.get("selected_stream_profile_id") or ""),
                rng=random,
            )
        cfg["stream_rotation"] = dict(stream_rotation)
        save_config(config_path, cfg)
        publish_rotation_status(
            "Rotacao randômica ativada" if enabled else "Rotacao randômica desativada"
        )
        if enabled:
            publish_rotation_status(format_stream_rotation_progress(stream_rotation))
        if editor is not None:
            editor.message = get_stream_rotation_status()["lastMessage"]

    def queue_random_stream_profile(*, reason: str = "manual") -> dict:
        nonlocal pending_rotation_profile

        profile = select_random_stream_profile(
            stream_store.list_profiles(),
            str(cfg.get("selected_stream_profile_id") or ""),
            rng=random,
        )
        if profile is None:
            message = "Rotacao requer ao menos dois perfis com camera_id e URL."
            publish_rotation_status(message)
            raise ValueError(message)

        pending_rotation_profile = dict(profile)
        message = (
            f"Proxima stream sorteada ({reason}): "
            f"{format_stream_profile_label(pending_rotation_profile)}"
        )
        publish_rotation_status(message)
        if editor is not None:
            editor.message = message
        return pending_rotation_profile

    def maybe_schedule_stream_rotation(backend_round: dict | None):
        nonlocal pending_rotation_profile, last_rotation_round_id, rotation_boundary_consumed

        if pending_rotation_profile is None and not stream_rotation.get("enabled"):
            publish_rotation_status()
            return

        round_id = get_round_id(backend_round)
        if not is_round_safe_for_stream_rotation(backend_round):
            rotation_boundary_consumed = False

        if stream_rotation.get("enabled"):
            if ensure_stream_rotation_profile_state(
                stream_rotation,
                str(cfg.get("selected_stream_profile_id") or ""),
                rng=random,
            ):
                cfg["stream_rotation"] = dict(stream_rotation)
                save_config(config_path, cfg)

            if count_settled_round_for_stream_rotation(stream_rotation, backend_round):
                cfg["stream_rotation"] = dict(stream_rotation)
                save_config(config_path, cfg)

        if (
            pending_rotation_profile is None
            and stream_rotation.get("enabled")
            and is_round_safe_for_stream_rotation(backend_round)
            and round_id
            and not rotation_boundary_consumed
            and stream_rotation_target_reached(stream_rotation)
        ):
            try:
                queue_random_stream_profile(reason="auto")
                publish_rotation_status(
                    "Alvo de rounds atingido; "
                    f"proxima stream sorteada: {format_stream_profile_label(pending_rotation_profile)}"
                )
            except ValueError:
                last_rotation_round_id = round_id
                rotation_boundary_consumed = True
                return

        if pending_rotation_profile is None:
            publish_rotation_status(
                format_stream_rotation_progress(stream_rotation)
                if stream_rotation.get("enabled")
                else ""
            )
            return

        if not should_apply_pending_stream_rotation(pending_rotation_profile, backend_round):
            status = get_round_status(backend_round) or "indisponivel"
            publish_rotation_status(f"Rotacao pendente aguardando janela segura ({status}).")
            return

        current_camera_id = str(cfg.get("camera_id") or "").strip()
        allowed, reason = backend.ensure_camera_change_allowed(
            current_camera_id,
            operation_name="rotacao de stream profile",
            allow_settling=True,
        )
        if not allowed:
            publish_rotation_status(f"Rotacao pendente bloqueada pelo backend: {reason}")
            return

        profile = dict(pending_rotation_profile)
        profile["_activation_allow_settling"] = True
        pending_rotation_profile = None
        last_rotation_round_id = round_id or last_rotation_round_id
        rotation_boundary_consumed = True
        queue_stream_profile(
            profile,
            message=f"Rotacao aplicada em janela segura: {format_stream_profile_label(profile)}",
        )
        publish_rotation_status("Rotacao aplicada em janela segura.")

    def poll_round_state_if_needed():
        nonlocal last_round_sync, current_round_id, total

        should_poll_round = (
            round_sync_enabled
            or bool(stream_rotation.get("enabled"))
            or pending_rotation_profile is not None
        )
        now_ts = time.time()
        if not should_poll_round or now_ts - last_round_sync < ROUND_SYNC_INTERVAL:
            return

        last_round_sync = now_ts
        backend_round = backend.fetch_current_round(cfg.get("camera_id", ""))
        if round_sync_enabled:
            next_round_id, next_total, round_changed = resolve_round_sync(
                current_round_id,
                backend_round,
                total,
            )
            if round_changed:
                logger.info(
                    "Mudanca de round detectada (%s -> %s). Resetando stream local.",
                    current_round_id or "<none>",
                    next_round_id,
                )
                current_round_id = next_round_id
                reset_tracking_state()
                total = next_total
                request_stream_reset()
            else:
                current_round_id = next_round_id

        maybe_schedule_stream_rotation(backend_round)

    def save_editor_state():
        nonlocal roi, line

        if editor is None:
            return

        stream_store.save_selected_profile(
            roi=editor.roi,
            line=editor.line,
            count_direction=count_direction,
        )
        editor.save(cfg, config_path)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        roi = dict(editor.roi)
        line = dict(editor.line)
        if control_panel is not None:
            control_panel.set_active_stream_profile(stream_store.get_selected_profile())

        editor.message = f"Calibracao salva para {cfg['camera_id']} (round ativo permitido)"

    def set_count_direction(direction: str):
        nonlocal count_direction

        count_direction = normalize_count_direction(direction)
        cfg["count_direction"] = count_direction

    def request_stream_reset():
        queue_pipeline_refresh()
        if editor is not None:
            editor.message = "Recriando ingestao da source..."

    def queue_stream_profile(profile: dict, *, message: str):
        nonlocal pending_stream_profile, roi, line, count_direction

        pending_stream_profile = dict(profile)
        roi = dict(profile["roi"])
        line = dict(profile["line"])
        count_direction = profile["count_direction"]

        if editor is not None:
            editor.load_values(roi, line, message=message)
        if control_panel is not None:
            control_panel.set_active_stream_profile(profile)
        publish_rotation_status(message)

    def queue_saved_profile_for_next_window(profile: dict, *, message: str):
        nonlocal pending_rotation_profile

        pending_rotation_profile = dict(profile)
        pending_rotation_profile["_activation_allow_settling"] = True
        publish_rotation_status(message)
        if editor is not None:
            editor.message = message
        if control_panel is not None:
            control_panel.refresh_stream_profiles(selected_profile_id=profile.get("id"))

    def is_selected_stream_target(stream_url: str, camera_id: str) -> bool:
        selected = stream_store.get_selected_profile()
        return (
            str(selected.get("stream_url") or "").strip() == str(stream_url or "").strip()
            and str(selected.get("camera_id") or "").strip() == str(camera_id or "").strip()
        )

    def select_stream_profile(profile_id: str) -> dict:
        profile = stream_store.select_profile(profile_id)
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        queued_profile = dict(profile)
        queued_profile["_activation_auto_switch_round"] = True
        queue_stream_profile(
            queued_profile,
            message=(
                "Stream pronta para trocar; round sera alternado automaticamente: "
                f"{format_stream_profile_label(profile)}"
            ),
        )
        return profile

    def force_stream_switch(
        profile_id: str,
        stream_name: str,
        stream_url: str,
        camera_id: str,
    ) -> dict:
        nonlocal pending_rotation_profile

        target_url = str(stream_url or "").strip()
        target_camera_id = str(camera_id or "").strip()
        if profile_id and (not target_url or not target_camera_id):
            for existing_profile in stream_store.list_profiles():
                if str(existing_profile.get("id") or "") == str(profile_id or ""):
                    target_url = target_url or str(existing_profile.get("stream_url") or "").strip()
                    target_camera_id = target_camera_id or str(existing_profile.get("camera_id") or "").strip()
                    stream_name = stream_name or str(existing_profile.get("name") or "").strip()
                    break

        current_camera_id = str(cfg.get("camera_id") or "").strip()
        profile, _created = stream_store.save_profile_entry(
            name=stream_name,
            camera_id=target_camera_id or cfg.get("camera_id", ""),
            stream_url=target_url or cfg.get("stream_url", ""),
        )
        profile = stream_store.select_profile(profile["id"])
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)

        target_camera_id = str(profile.get("camera_id") or "").strip()
        reason = (
            "Vision worker forced camera switch "
            f"from {current_camera_id or 'unknown'} to {target_camera_id or 'unknown'} "
            f"profile={profile.get('id', '')}"
        )
        voided_current = backend.void_current_round(current_camera_id, reason) if current_camera_id else False
        voided_target = False
        if target_camera_id and target_camera_id != current_camera_id:
            voided_target = backend.void_current_round(target_camera_id, reason)

        pending_rotation_profile = None
        forced_profile = dict(profile)
        forced_profile["_activation_skip_notify"] = True
        queue_stream_profile(
            forced_profile,
            message=(
                "Troca forcada enviada ao vision: "
                f"{format_stream_profile_label(profile)} | "
                f"round atual resetado={voided_current}; destino resetado={voided_target}"
            ),
        )
        return profile

    def open_stream_url(stream_url: str, stream_name: str, camera_id: str) -> dict:
        unlocked, reason = backend.ensure_camera_unlocked(cfg.get("camera_id", ""), "alterar stream")
        if not unlocked:
            target_url = stream_url or cfg.get("stream_url", "")
            target_camera_id = camera_id or cfg.get("camera_id", "")
            if is_selected_stream_target(target_url, target_camera_id):
                message = (
                    "Configuracao da stream ativa bloqueada ate o fechamento oficial do round. "
                    f"Detalhe: {reason}"
                )
                if editor is not None:
                    editor.message = message
                raise RuntimeError(message)

            profile, created = stream_store.save_profile_entry(
                name=stream_name,
                camera_id=target_camera_id,
                stream_url=target_url,
            )
            save_config(config_path, cfg)
            sync_stream_profiles_to_supabase(cfg, supabase_sync)
            action = "salva" if created else "atualizada"
            queue_saved_profile_for_next_window(
                profile,
                message=(
                    f"Stream {action} na esteira e pendente para a proxima janela segura: "
                    f"{format_stream_profile_label(profile)}"
                ),
            )
            return profile

        profile, created = stream_store.apply_stream_url(
            stream_url,
            name=stream_name,
            camera_id=camera_id,
        )
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        action = "adicionada" if created else "reaberta"
        queue_stream_profile(
            profile,
            message=f"Stream {action} na esteira: {format_stream_profile_label(profile)}",
        )
        return profile

    def save_stream_profile(stream_name: str, stream_url: str, camera_id: str) -> dict:
        unlocked, reason = backend.ensure_camera_unlocked(cfg.get("camera_id", ""), "salvar stream profile")
        if not unlocked:
            target_url = stream_url or cfg.get("stream_url", "")
            target_camera_id = camera_id or cfg.get("camera_id", "")
            if is_selected_stream_target(target_url, target_camera_id):
                message = (
                    "Configuracao da stream ativa bloqueada ate o fechamento oficial do round. "
                    f"Detalhe: {reason}"
                )
                if editor is not None:
                    editor.message = message
                raise RuntimeError(message)

            profile, created = stream_store.save_profile_entry(
                name=stream_name,
                camera_id=target_camera_id,
                stream_url=target_url,
            )
            save_config(config_path, cfg)
            sync_stream_profiles_to_supabase(cfg, supabase_sync)
            action = "salva" if created else "atualizada"
            queue_saved_profile_for_next_window(
                profile,
                message=(
                    f"Configuracao {action} na esteira e pendente para a proxima janela segura: "
                    f"{format_stream_profile_label(profile)}"
                ),
            )
            return profile

        target_url = stream_url or cfg.get("stream_url", "")
        profile = stream_store.save_selected_profile(
            name=stream_name,
            camera_id=camera_id or cfg.get("camera_id", ""),
            stream_url=target_url,
            roi=editor.roi if editor is not None else roi,
            line=editor.line if editor is not None else line,
            count_direction=count_direction,
        )
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        saved_backend = backend.save_camera_config(
            camera_id=profile["camera_id"],
            roi=profile["roi"],
            line={
                "x1": profile["line"]["x1"],
                "y1": profile["line"]["y1"],
                "x2": profile["line"]["x2"],
                "y2": profile["line"]["y2"],
            },
            count_direction=profile["count_direction"],
        )
        backend_suffix = " + backend" if saved_backend else " (backend pendente)"
        queue_stream_profile(
            profile,
            message=(
                f"Configuracao salva na esteira{backend_suffix}: "
                f"{format_stream_profile_label(profile)}"
            ),
        )
        return profile

    def delete_stream_profile(profile_id: str) -> dict:
        deleted = stream_store.delete_profile(profile_id)
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        if control_panel is not None:
            control_panel.set_active_stream_profile(stream_store.get_selected_profile())
        if editor is not None:
            editor.message = f"Stream apagada da esteira: {format_stream_profile_label(deleted)}"
        return deleted

    if round_sync_enabled:
        backend_round = backend.fetch_current_round(cfg.get("camera_id", ""))
        current_round_id, total, round_changed = resolve_round_sync(
            current_round_id,
            backend_round,
            total,
        )
        if round_changed:
            reset_tracking_state()

    if cfg.get("show_window", True):
        editor = ConfigEditor(roi, line)
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        try:
            cv2.startWindowThread()
        except Exception:
            pass
        cv2.setMouseCallback(WINDOW_NAME, lambda event, x, y, flags, param: editor.handle_mouse(event, x, y, flags, param))
        control_panel = EditorControlPanel(
            editor,
            stream_store,
            save_editor_state,
            request_stream_reset,
            select_stream_profile,
            open_stream_url,
            save_stream_profile,
            delete_stream_profile,
            force_stream_switch,
            set_count_direction,
            set_rotation_enabled,
            lambda: queue_random_stream_profile(reason="manual"),
            stream_rotation_enabled=bool(stream_rotation.get("enabled")),
        )
        active_control_panel_ref = control_panel

    try:
        model.fuse()
    except Exception:
        pass

    logger.info(
        "Iniciando contagem... | tracker: %s | conf: %s | imgsz: %s | stride: %s | jpeg: %s | browserMaxWidth: %s | operatorMaxWidth: %s | operatorFps: %s",
        cfg["tracker"],
        cfg["conf"],
        imgsz,
        inference_frame_stride,
        streamer.jpeg_quality,
        browser_stream_max_width,
        operator_preview_max_width,
        operator_preview_fps_limit,
    )

    fps_frame_count = 0
    fps_start_ts = time.time()

    while True:
        next_pipeline_start, should_stop_pipeline, should_refresh_pipeline = consume_pipeline_commands()

        if should_stop_pipeline:
            pipeline_runtime.stop()
            streamer.clear()
            last_raw_seq = 0
            if editor is not None:
                editor.message = "Pipeline parada pelo orquestrador"

        if should_refresh_pipeline:
            active_pipeline_cfg = pipeline_runtime.get_config() or current_pipeline_cfg
            refresh_source_url = str(active_pipeline_cfg.get("stream_url") or cfg.get("stream_url") or "").strip()
            refresh_camera_id = str(active_pipeline_cfg.get("camera_id") or cfg.get("camera_id") or "").strip()
            refresh_raw_path = str(active_pipeline_cfg.get("raw_stream_path") or "").strip()
            refresh_processed_path = str(active_pipeline_cfg.get("processed_stream_path") or "").strip()
            recreate_raw_path = bool(active_pipeline_cfg.get("reset_stream_recreate_raw_path", True))
            refresh_started_at = time.perf_counter()

            logger.info(
                "Refresh upstream solicitado | source=%s | raw_path=%s | recreate_raw=%s",
                refresh_source_url or "<none>",
                refresh_raw_path or "<none>",
                recreate_raw_path,
            )

            pipeline_runtime.stop()
            streamer.clear()
            last_raw_seq = 0
            reset_tracking_state()
            last_track_results = None
            last_visual_detections = []
            last_operator_preview = None
            last_operator_preview_at = 0.0
            frame_count = 0
            fps_frame_count = 0
            fps_start_ts = time.time()

            if editor is not None:
                editor.message = "Recriando ingestao da source..."

            refresh_ready = True
            if recreate_raw_path:
                remove_ok = remove_mediamtx_source_path(cfg, refresh_raw_path)
                if editor is not None:
                    editor.message = "Reconectando captura..."
                logger.info(
                    "Refresh upstream MediaMTX | raw_path=%s | remove_ok=%s",
                    refresh_raw_path or "<none>",
                    remove_ok,
                )

            if refresh_ready:
                try:
                    current_pipeline_cfg = build_pipeline_config(
                        cfg,
                        source_url=refresh_source_url or cfg.get("stream_url"),
                        camera_id=refresh_camera_id or cfg.get("camera_id"),
                        raw_stream_path=refresh_raw_path or None,
                        processed_stream_path=refresh_processed_path or None,
                    )
                    pipeline_runtime.start(current_pipeline_cfg)
                    pending_stream_refresh_started_at = time.time()
                    elapsed_ms = (time.perf_counter() - refresh_started_at) * 1000.0
                    logger.info(
                        "Refresh upstream concluido | source=%s | raw_path=%s | duracao=%.1f ms",
                        refresh_source_url or "<none>",
                        refresh_raw_path or "<none>",
                        elapsed_ms,
                    )
                    if editor is not None:
                        editor.message = "Stream reposicionada no ponto mais atual disponivel"
                except Exception as exc:
                    refresh_ready = False
                    logger.warning("Refresh upstream falhou ao resolver/iniciar source: %s", exc)
                    if editor is not None:
                        editor.message = f"Falha ao resolver/reconectar source: {exc}"
            else:
                elapsed_ms = (time.perf_counter() - refresh_started_at) * 1000.0
                logger.warning(
                    "Refresh upstream falhou | source=%s | raw_path=%s | duracao=%.1f ms",
                    refresh_source_url or "<none>",
                    refresh_raw_path or "<none>",
                    elapsed_ms,
                )
                if editor is not None:
                    editor.message = "Falha ao recriar ingestao da source"

        if next_pipeline_start is not None:
            if next_pipeline_start.source_url:
                cfg["stream_url"] = next_pipeline_start.source_url
            if next_pipeline_start.camera_id:
                cfg["camera_id"] = next_pipeline_start.camera_id
            if next_pipeline_start.direction:
                cfg["count_direction"] = normalize_count_direction(next_pipeline_start.direction)
                count_direction = cfg["count_direction"]
            if isinstance(next_pipeline_start.count_line, dict):
                line = {
                    "x1": int(next_pipeline_start.count_line.get("x1", line["x1"])),
                    "y1": int(next_pipeline_start.count_line.get("y1", line["y1"])),
                    "x2": int(next_pipeline_start.count_line.get("x2", line["x2"])),
                    "y2": int(next_pipeline_start.count_line.get("y2", line["y2"])),
                }
                cfg["line"] = dict(line)
                if editor is not None:
                    editor.line = dict(line)

            try:
                current_pipeline_cfg = build_pipeline_config(
                    cfg,
                    source_url=next_pipeline_start.source_url or cfg.get("stream_url"),
                    camera_id=next_pipeline_start.camera_id or cfg.get("camera_id"),
                    raw_stream_path=next_pipeline_start.raw_stream_path or None,
                    processed_stream_path=next_pipeline_start.processed_stream_path or None,
                )
                pipeline_runtime.start(current_pipeline_cfg)
                reset_tracking_state()
                last_track_results = None
                last_visual_detections = []
                last_operator_preview = None
                last_operator_preview_at = 0.0
                frame_count = 0
                last_raw_seq = 0
                fps_frame_count = 0
                fps_start_ts = time.time()
                if editor is not None:
                    editor.message = f"Pipeline ativa em {current_pipeline_cfg['processed_stream_path']}"
            except Exception as exc:
                logger.warning("Falha ao iniciar pipeline solicitada: %s", exc)
                if editor is not None:
                    editor.message = f"Falha ao resolver/iniciar stream: {exc}"

        if pending_stream_profile is not None:
            profile = pending_stream_profile
            pending_stream_profile = None
            reset_tracking_state()
            if round_sync_enabled:
                backend_round = backend.fetch_current_round(profile.get("camera_id", ""))
                if backend_round:
                    backend_round_id = str(backend_round.get("roundId", "")).strip()
                    if backend_round_id:
                        current_round_id = backend_round_id
                    total = int(backend_round.get("currentCount", 0) or 0)

            cfg["stream_url"] = profile["stream_url"]
            cfg["camera_id"] = profile["camera_id"]
            cfg["selected_stream_profile_id"] = str(profile.get("id") or "")
            cfg["roi"] = dict(profile["roi"])
            cfg["line"] = dict(profile["line"])
            cfg["count_direction"] = profile["count_direction"]
            roi = dict(profile["roi"])
            line = dict(profile["line"])
            count_direction = profile["count_direction"]
            try:
                current_pipeline_cfg = build_pipeline_config(cfg)
                pipeline_runtime.start(current_pipeline_cfg)
                requested_camera_id = str(profile.get("camera_id") or "").strip()
                requested_profile_id = str(profile.get("id") or "").strip()
                requested_processed_path = str(current_pipeline_cfg.get("processed_stream_path") or "").strip()
                requested_profile_label = format_stream_profile_label(profile)
                pending_camera_activation = {
                    "phase": "waiting_stream",
                    "requestedCameraId": requested_camera_id,
                    "requestedStreamProfileId": requested_profile_id,
                    "requestedProcessedStreamPath": requested_processed_path,
                    "requestedProfileLabel": requested_profile_label,
                    "autoSwitchRound": bool(profile.get("_activation_auto_switch_round")),
                    "requestNotified": False,
                    "readyNotified": False,
                }
                update_camera_activation_status(
                    phase="waiting_stream",
                    requestedCameraId=requested_camera_id,
                    requestedStreamProfileId=requested_profile_id,
                    requestedProcessedStreamPath=requested_processed_path,
                    requestedProfileLabel=requested_profile_label,
                    readyForRounds=False,
                )
                if ensure_stream_rotation_profile_state(stream_rotation, str(profile.get("id") or ""), rng=random):
                    cfg["stream_rotation"] = dict(stream_rotation)
                    save_config(config_path, cfg)
                last_track_results = None
                last_visual_detections = []
                last_operator_preview = None
                last_operator_preview_at = 0.0
                frame_count = 0
                last_raw_seq = 0
                fps_frame_count = 0
                fps_start_ts = time.time()
                logger.info(
                    "Perfil de stream aplicado: %s | url=%s",
                    format_stream_profile_label(profile),
                    cfg["stream_url"],
                )
                if not bool(profile.get("_activation_skip_notify")):
                    backend.notify_stream_profile_activated(
                        cfg.get("camera_id", ""),
                        profile.get("id", ""),
                        allow_settling=bool(profile.get("_activation_allow_settling")),
                        auto_switch_round=bool(profile.get("_activation_auto_switch_round")),
                        phase="requested",
                    )
                    if isinstance(pending_camera_activation, dict):
                        pending_camera_activation["requestNotified"] = True
                publish_rotation_status(f"Perfil ativo: {format_stream_profile_label(profile)}")
            except Exception as exc:
                logger.warning("Falha ao aplicar perfil de stream: %s", exc)
                if editor is not None:
                    editor.message = f"Falha ao resolver/iniciar perfil: {exc}"

        poll_round_state_if_needed()

        if not pipeline_runtime.is_running():
            time.sleep(0.05)
            continue

        last_raw_seq, frame, captured_at = pipeline_runtime.wait_for_raw_frame(last_raw_seq, timeout=0.5)
        if frame is None or captured_at is None:
            if frame_count == 0:
                logger.warning("Nenhum frame recebido ainda do stream...")
            active_pipeline_cfg = pipeline_runtime.get_config() or current_pipeline_cfg
            active_source_url = str(active_pipeline_cfg.get("stream_url") or cfg.get("stream_url") or "").strip()
            if is_youtube_url(active_source_url) and time.time() >= youtube_retry_after:
                youtube_retry_after = time.time() + 30.0
                logger.info("Stream YouTube sem frames; solicitando nova resolucao da URL.")
                queue_pipeline_refresh()
            continue

        frame_count += 1
        youtube_retry_after = 0.0

        if frame_count == 1 and pending_stream_refresh_started_at is not None:
            logger.info(
                "Primeiro frame recebido apos refresh upstream em %.1f ms",
                (time.time() - pending_stream_refresh_started_at) * 1000.0,
            )
            pending_stream_refresh_started_at = None

        if frame_count == 1:
            h0, w0 = frame.shape[:2]
            logger.info("Resolução do stream: %dx%d", w0, h0)
            logger.info("ROI: %s | Linha: %s | Direção: %s", roi, line, count_direction)

        if isinstance(pending_camera_activation, dict):
            activation_requested_camera = str(pending_camera_activation.get("requestedCameraId") or "").strip()
            activation_requested_profile = str(pending_camera_activation.get("requestedStreamProfileId") or "").strip()
            activation_requested_path = str(pending_camera_activation.get("requestedProcessedStreamPath") or "").strip()
            activation_requested_label = str(pending_camera_activation.get("requestedProfileLabel") or activation_requested_camera).strip()
            current_camera_id = str(cfg.get("camera_id") or "").strip()
            current_profile_id = str(cfg.get("selected_stream_profile_id") or "").strip()
            runtime_snapshot = runtime_stats.snapshot()
            stream_ready = (
                activation_requested_camera
                and activation_requested_camera == current_camera_id
                and activation_requested_profile == current_profile_id
                and bool(runtime_snapshot.get("streamConnected"))
                and bool(runtime_snapshot.get("publisherHealthy"))
            )
            if stream_ready:
                if not bool(pending_camera_activation.get("readyNotified")):
                    backend.notify_stream_profile_activated(
                        activation_requested_camera,
                        activation_requested_profile,
                        allow_settling=True,
                        auto_switch_round=bool(pending_camera_activation.get("autoSwitchRound")),
                        phase="ready",
                    )
                    pending_camera_activation["readyNotified"] = True
                update_camera_activation_status(
                    phase="ready",
                    requestedCameraId=activation_requested_camera,
                    readyCameraId=activation_requested_camera,
                    requestedStreamProfileId=activation_requested_profile,
                    readyStreamProfileId=activation_requested_profile,
                    requestedProcessedStreamPath=activation_requested_path,
                    readyProcessedStreamPath=activation_requested_path,
                    requestedProfileLabel=activation_requested_label,
                    readyProfileLabel=activation_requested_label,
                    readyForRounds=True,
                )
                pending_camera_activation = None

        now_ts = time.time()
        if now_ts - last_config_poll >= CONFIG_POLL_INTERVAL:
            last_config_poll = now_ts
            admin_cfg = backend.fetch_camera_config(cfg["camera_id"])
            if admin_cfg and (editor is None or (editor.mode == "idle" and not editor.dirty)):
                if admin_cfg.get("roi"):
                    roi = admin_cfg["roi"]

                if admin_cfg.get("countLine"):
                    line = {
                        "x1": admin_cfg["countLine"]["x1"],
                        "y1": admin_cfg["countLine"]["y1"],
                        "x2": admin_cfg["countLine"]["x2"],
                        "y2": admin_cfg["countLine"]["y2"],
                    }

                if admin_cfg.get("countDirection"):
                    count_direction = normalize_count_direction(admin_cfg["countDirection"])

                stream_store.save_selected_profile(
                    roi=roi,
                    line=line,
                    count_direction=count_direction,
                )
                sync_stream_profiles_to_supabase(cfg, supabase_sync)

                logger.info(
                    "Config atualizada pelo admin: line=%s, direction=%s",
                    line,
                    count_direction,
                )
                if editor is not None:
                    editor.sync_external_values(roi, line)
                if control_panel is not None:
                    control_panel.set_active_stream_profile(stream_store.get_selected_profile())

        inference_is_fresh = should_process_frame(frame_count, inference_frame_stride)
        inference_start = time.perf_counter()
        try:
            results = model.track(
                frame,
                persist=True,
                tracker=cfg["tracker"],
                conf=cfg["conf"],
                classes=list(cfg["allowed_classes"].values()),
                imgsz=imgsz,
                verbose=False,
            )
        except Exception as exc:
            logger.warning("Falha na inferência YOLO (frame %d ignorado): %s", frame_count, exc)
            continue

        runtime_stats.record_inference_ms((time.perf_counter() - inference_start) * 1000)

        h, w = frame.shape[:2]
        detections_list = []
        boxes = None

        if editor is not None:
            editor.set_frame_size(w, h)
            roi = dict(editor.roi)
            line = dict(editor.line)

        boxes = results[0].boxes

        # FPS periódico
        fps_frame_count += 1
        if fps_frame_count >= 100:
            elapsed = time.time() - fps_start_ts
            snapshot = runtime_stats.snapshot(backend.get_health_snapshot())
            logger.info("FPS médio: %.1f | Total contado: %d", fps_frame_count / elapsed if elapsed > 0 else 0, total)
            logger.info(
                "FPS inst: %.1f | inferencia media: %.1f ms | JPEG medio: %.1f ms | pipeline media: %.1f ms | MJPEG clientes: %d | live descartados: %d",
                snapshot["fpsInstant"],
                snapshot["avgInferenceMs"],
                snapshot["avgJpegEncodeMs"],
                snapshot["avgPipelineMs"],
                snapshot["mjpegClients"],
                snapshot["backend"].get("liveDropped", 0),
            )
            fps_frame_count = 0
            fps_start_ts = time.time()

        if logger.isEnabledFor(logging.DEBUG) and frame_count % 30 == 0:
            n_boxes = len(boxes) if boxes is not None else 0
            logger.debug("[frame %d] boxes=%s (%d) | ids=%s | total=%d",
                frame_count,
                boxes is not None,
                n_boxes,
                boxes.id if boxes is not None else None,
                total,
            )

        if boxes is not None and boxes.id is not None:
            xyxy = boxes.xyxy.cpu().numpy().astype(int)
            cls_ids = boxes.cls.cpu().numpy().astype(int)
            track_ids = boxes.id.cpu().numpy().astype(int)
            confs = boxes.conf.cpu().numpy()

            for i in range(len(xyxy)):
                x1, y1, x2, y2 = xyxy[i]
                track_id = int(track_ids[i])
                cls_id = int(cls_ids[i])
                conf = float(confs[i])

                if bbox_area(x1, y1, x2, y2) < min_bbox_area:
                    continue

                vehicle_name = class_names.get(cls_id, str(cls_id))
                if not is_countable_vehicle(vehicle_name):
                    continue
                cx, cy = anchor_point(x1, y1, x2, y2)

                if inference_is_fresh:
                    track_hits[track_id] = track_hits.get(track_id, 0) + 1

                is_inside = inside_roi(cx, cy, roi)
                is_counted = track_id in counted_ids
                did_cross = False

                if is_inside and inference_is_fresh:
                    last_seen[track_id] = frame_count

                    prev = last_positions.get(track_id)
                    if should_count_track(
                        prev_position=prev,
                        curr_position=(cx, cy),
                        line=line,
                        direction=count_direction,
                        hits=track_hits.get(track_id, 0),
                        min_hits_to_count=min_hits_to_count,
                        already_counted=track_id in counted_ids,
                    ):
                        counted_ids.add(track_id)
                        total += 1
                        is_counted = True
                        did_cross = True

                        if cfg.get("save_snapshots", True):
                            sy1 = clamp(y1, 0, h)
                            sy2 = clamp(y2, 0, h)
                            sx1 = clamp(x1, 0, w)
                            sx2 = clamp(x2, 0, w)
                            crop = frame[sy1:sy2, sx1:sx2]

                            if crop.size > 0:
                                filename = (
                                    f"{track_id}_{int(time.time() * 1000)}.jpg"
                                )
                                path = os.path.join(
                                    cfg["snapshot_dir"],
                                    filename,
                                )
                                try:
                                    if not snapshot_writer.enqueue(path, crop):
                                        path = ""
                                except Exception as exc:
                                    logger.warning("Falha ao salvar snapshot %s: %s", path, exc)
                                    path = ""
                            else:
                                path = ""
                        else:
                            path = ""

                        backend.send_count_event(
                            {
                                "cameraId": cfg["camera_id"],
                                "roundId": current_round_id,
                                "streamProfileId": cfg.get("selected_stream_profile_id", ""),
                                "trackId": str(track_id),
                                "vehicleType": vehicle_name,
                                "direction": count_direction,
                                "lineId": "main-line",
                                "confidence": round(conf, 4),
                                "frameNumber": frame_count,
                                "crossedAt": now(),
                                "snapshotUrl": path,
                                "source": "vision_worker_round_count",
                                "countBefore": total - 1,
                                "countAfter": total,
                                "totalCount": total,
                            }
                        )

                        logger.info(
                            "Count: %d (%s #%d)",
                            total,
                            vehicle_name,
                            track_id,
                        )

                    last_positions[track_id] = (cx, cy)

                detections_list.append(
                    {
                        "trackId": str(track_id),
                        "vehicleType": vehicle_name,
                        "bbox": {
                            "x": int(x1),
                            "y": int(y1),
                            "w": int(x2 - x1),
                            "h": int(y2 - y1),
                        },
                        "center": {"x": cx, "y": cy},
                        "confidence": round(conf, 2),
                        "insideRoi": is_inside,
                        "crossedLine": did_cross,
                        "counted": is_counted,
                    }
                )

        if inference_is_fresh:
            last_visual_detections = list(detections_list)
        else:
            detections_list = list(last_visual_detections)

        now_ts = time.time()
        if now_ts - last_live_send >= LIVE_SEND_INTERVAL:
            last_live_send = now_ts
            backend.send_live_detections(
                {
                    "cameraId": cfg["camera_id"],
                    "roundId": current_round_id,
                    "frameId": frame_count,
                    "frameWidth": w,
                    "frameHeight": h,
                    "totalCount": total,
                    "timestamp": now_ts,
                    "roi": roi,
                    "countLine": {
                        "x1": line["x1"],
                        "y1": line["y1"],
                        "x2": line["x2"],
                        "y2": line["y2"],
                    },
                    "detections": detections_list,
                }
            )

        if frame_count % max_track_history_age == 0:
            stale = [
                tid
                for tid, last in last_seen.items()
                if frame_count - last > max_track_history_age
            ]

            for tid in stale:
                last_positions.pop(tid, None)
                last_seen.pop(tid, None)
                track_hits.pop(tid, None)
                counted_ids.discard(tid)

        browser_stream = annotate_frame(
            frame,
            roi,
            line,
            detections_list,
            total,
            show_roi=False,
            show_labels=False,
            show_centers=False,
            show_total=False,
        )
        browser_stream = resize_frame_max_width(browser_stream, browser_stream_max_width)

        operator_stream = browser_stream
        if cfg.get("show_window", True):
            preview_interval = 1.0 / max(1.0, operator_preview_fps_limit)
            if last_operator_preview is None or (time.time() - last_operator_preview_at) >= preview_interval:
                operator_stream = annotate_frame(frame, roi, line, detections_list, total)
                operator_stream = resize_frame_max_width(operator_stream, operator_preview_max_width)
                if editor is not None:
                    editor.draw_overlay(operator_stream)
                last_operator_preview = operator_stream
                last_operator_preview_at = time.time()
            else:
                operator_stream = last_operator_preview

        runtime_stats.record_processed_frame(total)
        pipeline_runtime.push_annotated_frame(browser_stream)
        runtime_stats.record_pipeline_ms((time.time() - captured_at) * 1000)

        if cfg.get("show_window", True):
            if control_panel is not None:
                control_panel.refresh()
                if control_panel.should_close:
                    break

            cv2.imshow(WINDOW_NAME, operator_stream)
            key = poll_window_key(1)
            if key == -1:
                continue
            key &= 0xFF
            if key == ord("r") and editor is not None:
                editor.begin_roi_mode()
            elif key == ord("l") and editor is not None:
                editor.begin_line_mode()
            elif key == ord("s") and editor is not None:
                save_editor_state()
            elif key == ord("c") and editor is not None:
                editor.cancel()
                roi = dict(editor.roi)
                line = dict(editor.line)
            elif key == ord("t"):
                request_stream_reset()
            elif key == 27 and editor is not None:
                editor.clear_mode()
            elif key == ord("q"):
                break
            continue

    cleanup_runtime()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Encerrando por Ctrl+C.")
        cleanup_runtime()
