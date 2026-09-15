import hmac
from worker_defaults import (DEFAULT_ROI, DEFAULT_LINE, DEFAULT_STREAM_ROTATION, DEFAULT_STREAM_SCHEDULE, DEFAULT_SECONDARY_VERIFICATION_ENABLED, DEFAULT_SECONDARY_VERIFICATION_BAND_PX, SECONDARY_VERIFICATION_MIN_BAND_FRAMES, SECONDARY_VERIFICATION_MIN_PROGRESS_PX, STREAM_ROTATION_SAFE_STATUSES, STREAM_ROTATION_DEFER_STATUSES)
from runtime_stats import (RuntimeStats)
from stream_capture import (normalize_ffmpeg_capture_options, StreamCapture)
from video_publisher import (RtspFramePublisher)
from stream_schedule import (normalize_schedule_timezone, normalize_outside_window_behavior, normalize_schedule_time_text, schedule_time_to_minutes, make_stream_schedule_rule_id, normalize_allowed_profile_ids, expand_schedule_rule_windows, schedule_windows_overlap, validate_stream_schedule_rules, build_stream_schedule_rule, normalize_stream_schedule_config, schedule_rule_is_active, format_stream_schedule_window, resolve_stream_schedule_state, is_profile_allowed_by_schedule, choose_schedule_enforcement_profile, format_stream_schedule_rule_row)
from worker_config import (normalize_roi_config, normalize_line_config, normalize_count_direction, normalize_secondary_verification_enabled, normalize_secondary_verification_band_px, normalize_stream_rotation_config, get_round_status, get_round_id, is_round_safe_for_stream_rotation, should_defer_stream_rotation, select_random_stream_profile, should_apply_pending_stream_rotation, choose_stream_rotation_target, ensure_stream_rotation_profile_state, count_settled_round_for_stream_rotation, stream_rotation_target_reached, format_stream_rotation_progress, shorten_text, guess_stream_profile_name, format_stream_profile_label, format_stream_profile_table_row, make_stream_profile_id, build_stream_profile, sync_config_with_selected_profile, normalize_config, load_config, save_config, bootstrap_stream_profiles_from_supabase, sync_stream_profiles_to_supabase, get_selected_stream_profile, StreamProfileStore, StreamScheduleStore, is_blob_url, validate_stream_url)
from count_geometry import (should_process_frame, inside_roi, crossed_horizontal_segment, crossed_vertical_segment, count_line_is_horizontal, line_geometry_metrics, point_inside_line_band, distance_point_to_segment, segment_orientation, point_on_segment, segments_intersect, segment_distance, bbox_distance_to_line_segment, bbox_touches_line_band, movement_delta_for_direction, movement_matches_direction, should_count_track_fallback, should_count_track, count_direction_display_name, anchor_point, clamp, build_class_names, is_countable_vehicle, bbox_area)
from frame_overlay import (annotate_frame)
from calibration_editor import (ConfigEditor)

import json
import logging
import math
import numpy as np
import os
import queue
import random
import requests
import socket
import subprocess
import sys
import threading
import time
import atexit
import uuid
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import cv2
from flask import Flask, Response, jsonify, request
from ultralytics import YOLO
from waitress import create_server

from backend_client import BackendClient
from supabase_sync import SupabaseStreamProfileSync

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
LOG_FILE = os.path.join(LOG_DIR, "vision-worker.log")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

SINGLE_INSTANCE_HOST = "127.0.0.1"
SINGLE_INSTANCE_PORT = 38759
single_instance_socket = None


def acquire_single_instance_lock() -> bool:
    global single_instance_socket
    if single_instance_socket is not None:
        return True

    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lock_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        lock_socket.bind((SINGLE_INSTANCE_HOST, SINGLE_INSTANCE_PORT))
        lock_socket.listen(1)
    except OSError:
        try:
            lock_socket.close()
        except Exception:
            pass
        return False

    single_instance_socket = lock_socket
    return True


def release_single_instance_lock():
    global single_instance_socket
    if single_instance_socket is None:
        return
    try:
        single_instance_socket.close()
    except Exception:
        pass
    finally:
        single_instance_socket = None


runtime_stats = RuntimeStats()
backend_client_ref: BackendClient | None = None
mjpeg_token_ref: str = ""
active_stream_ref = None
active_mjpeg_server_ref = None
active_control_panel_ref = None
active_snapshot_writer_ref = None
stream_source_status_lock = threading.Lock()
stream_source_status_ref = {
    "sourceKind": "",
    "sourceUrlResolved": False,
    "lastResolveError": "",
    "captureDirectSourceUrl": "",
    "captureSourceUrl": "",
}
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
stream_schedule_status_lock = threading.Lock()
stream_schedule_status_ref = {
    "timezone": "America/Sao_Paulo",
    "activeRuleId": "",
    "activeRuleIds": [],
    "activeRuleName": "",
    "activeWindow": "",
    "restricted": False,
    "eligibleProfileIds": [],
    "pendingEnforcement": False,
    "lastMessage": "",
}
camera_activation_status_lock = threading.Lock()
camera_activation_status_ref = {
    "phase": "ready",
    "activationSessionId": "",
    "lastRenderableActivationSessionId": "",
    "activationRequestedAt": None,
    "firstCaptureAt": None,
    "firstProcessedAt": None,
    "firstRenderableFrameAt": None,
    "firstPublishedAt": None,
    "requestedCameraId": "",
    "readyCameraId": "",
    "requestedStreamProfileId": "",
    "readyStreamProfileId": "",
    "requestedProcessedStreamPath": "",
    "readyProcessedStreamPath": "",
    "requestedProfileLabel": "",
    "readyProfileLabel": "",
    "readyForRounds": True,
    "frontendAckRequired": True,
    "frontendAckPhase": "ready",
    "frontendAckNonce": "",
}
RECENT_RUNTIME_CAMERA_IDS_LIMIT = 4
recent_runtime_camera_ids_lock = threading.Lock()
recent_runtime_camera_ids_ref: list[str] = []

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


class PipelineRuntime:
    DEFAULT_STALL_TIMEOUT_SECONDS = 15.0
    DEFAULT_STALL_RESET_COOLDOWN_SECONDS = 10.0

    def __init__(self, stats: RuntimeStats, mjpeg_streamer: AnnotatedFrameStreamer):
        self.stats = stats
        self.mjpeg_streamer = mjpeg_streamer
        self.raw_frames = LatestFrameSlot()
        self.annotated_frames = LatestFrameSlot()
        self._lock = threading.Lock()
        self._capture_thread = None
        self._publish_thread = None
        self._watchdog_thread = None
        self._capture_stop = None
        self._publish_stop = None
        self._watchdog_stop = None
        self._stream = None
        self._publisher = None
        self._config = None
        self._running = False
        self._stall_timeout_seconds = self.DEFAULT_STALL_TIMEOUT_SECONDS
        self._stall_reset_cooldown_seconds = self.DEFAULT_STALL_RESET_COOLDOWN_SECONDS

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def get_config(self) -> dict | None:
        with self._lock:
            return dict(self._config or {}) if self._config else None

    def get_active_capture_url(self) -> str:
        with self._lock:
            stream = self._stream
        if stream is None:
            return ""
        return str(getattr(stream, "url", "") or "").strip()

    def start(self, config: dict):
        self.stop()

        capture_source_url = str(config.get("capture_source_url") or config.get("stream_url") or "").strip()
        capture_fallback_source_url = str(config.get("capture_fallback_source_url") or "").strip()
        if not capture_source_url:
            raise ValueError("Nenhuma URL de captura configurada para a pipeline.")

        stream = StreamCapture(
            capture_source_url,
            stats=self.stats,
            fallback_url=capture_fallback_source_url,
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
        watchdog_stop = threading.Event()

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
        watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            args=(stream, capture_thread, watchdog_stop),
            daemon=True,
            name="capture-watchdog",
        )

        with self._lock:
            self._stream = stream
            self._publisher = publisher
            self._capture_stop = capture_stop
            self._publish_stop = publish_stop
            self._watchdog_stop = watchdog_stop
            self._capture_thread = capture_thread
            self._publish_thread = publish_thread
            self._watchdog_thread = watchdog_thread
            self._config = dict(config)
            self._running = True
            self._stall_timeout_seconds = max(
                5.0,
                float(config.get("stream_stall_timeout_seconds", self.DEFAULT_STALL_TIMEOUT_SECONDS)),
            )
            self._stall_reset_cooldown_seconds = max(
                3.0,
                float(
                    config.get(
                        "stream_stall_reset_cooldown_seconds",
                        self.DEFAULT_STALL_RESET_COOLDOWN_SECONDS,
                    )
                ),
            )

        self.stats.reset_pipeline_readiness()
        self.raw_frames.clear()
        self.annotated_frames.clear()
        capture_thread.start()
        publish_thread.start()
        watchdog_thread.start()

    def stop(self):
        with self._lock:
            stream = self._stream
            publisher = self._publisher
            capture_stop = self._capture_stop
            publish_stop = self._publish_stop
            watchdog_stop = self._watchdog_stop
            capture_thread = self._capture_thread
            publish_thread = self._publish_thread
            watchdog_thread = self._watchdog_thread
            self._stream = None
            self._publisher = None
            self._capture_stop = None
            self._publish_stop = None
            self._watchdog_stop = None
            self._capture_thread = None
            self._publish_thread = None
            self._watchdog_thread = None
            self._config = None
            self._running = False

        if capture_stop is not None:
            capture_stop.set()
        if publish_stop is not None:
            publish_stop.set()
        if watchdog_stop is not None:
            watchdog_stop.set()

        if capture_thread is not None and capture_thread.is_alive():
            capture_thread.join(timeout=2)
        if publish_thread is not None and publish_thread.is_alive():
            publish_thread.join(timeout=2)
        if watchdog_thread is not None and watchdog_thread.is_alive():
            watchdog_thread.join(timeout=2)

        if stream is not None:
            stream.release()
        if publisher is not None:
            publisher.stop()

        self.stats.reset_pipeline_readiness()
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
            try:
                ret, frame = stream.read()
            except Exception as exc:
                logger.warning("Falha inesperada na captura; resetando stream: %s", exc)
                stream.request_reset()
                time.sleep(0.1)
                continue
            if not ret:
                time.sleep(0.005)
                continue

            captured_at = time.time()
            self.stats.record_capture(captured_at)
            self.raw_frames.update(frame, captured_at)

    def _watchdog_loop(
        self,
        stream: "StreamCapture",
        capture_thread: threading.Thread,
        stop_event: threading.Event,
    ):
        last_reset_at = 0.0
        while not stop_event.wait(0.5):
            if not capture_thread.is_alive():
                logger.warning("Thread de captura encerrou inesperadamente; aguardando restart da pipeline.")
                return

            diagnostics = stream.get_stall_diagnostics()
            read_duration_seconds = float(diagnostics.get("readDurationSeconds") or 0.0)
            if read_duration_seconds < self._stall_timeout_seconds:
                continue

            now_ts = time.time()
            if now_ts - last_reset_at < self._stall_reset_cooldown_seconds:
                continue

            if stream.force_interrupt_stalled_read(
                reason=(
                    "watchdog de captura sem novos frames "
                    f"por {read_duration_seconds:.1f}s"
                )
            ):
                last_reset_at = now_ts

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


def update_stream_schedule_status(**values):
    with stream_schedule_status_lock:
        stream_schedule_status_ref.update(values)


def get_stream_schedule_status() -> dict:
    with stream_schedule_status_lock:
        status = dict(stream_schedule_status_ref)
    status["activeRuleIds"] = list(status.get("activeRuleIds") or [])
    status["eligibleProfileIds"] = list(status.get("eligibleProfileIds") or [])
    return status


def update_camera_activation_status(**values):
    with camera_activation_status_lock:
        camera_activation_status_ref.update(values)


def mark_camera_activation_observation(
    activation_session_id: str,
    *,
    camera_id: str = "",
    stream_profile_id: str = "",
    captured_at: float | None = None,
    processed_at: float | None = None,
    renderable_at: float | None = None,
    published_at: float | None = None,
):
    normalized_session_id = str(activation_session_id or "").strip()
    if not normalized_session_id:
        return

    normalized_camera_id = str(camera_id or "").strip()
    normalized_profile_id = str(stream_profile_id or "").strip()

    with camera_activation_status_lock:
        if str(camera_activation_status_ref.get("activationSessionId") or "").strip() != normalized_session_id:
            return

        requested_camera_id = str(camera_activation_status_ref.get("requestedCameraId") or "").strip()
        requested_profile_id = str(camera_activation_status_ref.get("requestedStreamProfileId") or "").strip()
        if normalized_camera_id and requested_camera_id and normalized_camera_id != requested_camera_id:
            return
        if normalized_profile_id and requested_profile_id and normalized_profile_id != requested_profile_id:
            return

        if captured_at is not None and not camera_activation_status_ref.get("firstCaptureAt"):
            camera_activation_status_ref["firstCaptureAt"] = float(captured_at)
        if processed_at is not None and not camera_activation_status_ref.get("firstProcessedAt"):
            camera_activation_status_ref["firstProcessedAt"] = float(processed_at)
        if renderable_at is not None and not camera_activation_status_ref.get("firstRenderableFrameAt"):
            camera_activation_status_ref["firstRenderableFrameAt"] = float(renderable_at)
            camera_activation_status_ref["lastRenderableActivationSessionId"] = normalized_session_id
        if published_at is not None and not camera_activation_status_ref.get("firstPublishedAt"):
            camera_activation_status_ref["firstPublishedAt"] = float(published_at)


def get_camera_activation_status() -> dict:
    with camera_activation_status_lock:
        return dict(camera_activation_status_ref)


def remember_recent_runtime_camera_id(camera_id: str):
    normalized_camera_id = str(camera_id or "").strip()
    if not normalized_camera_id:
        return
    with recent_runtime_camera_ids_lock:
        if normalized_camera_id in recent_runtime_camera_ids_ref:
            recent_runtime_camera_ids_ref.remove(normalized_camera_id)
        recent_runtime_camera_ids_ref.insert(0, normalized_camera_id)
        del recent_runtime_camera_ids_ref[RECENT_RUNTIME_CAMERA_IDS_LIMIT:]


def get_recent_runtime_camera_ids() -> list[str]:
    with recent_runtime_camera_ids_lock:
        return list(recent_runtime_camera_ids_ref)


def is_mjpeg_request_authorized() -> bool:
    if not mjpeg_token_ref:
        return True

    header_token = request.headers.get("X-API-Key", "")
    query_token = request.args.get("token", "")
    return header_token == mjpeg_token_ref or query_token == mjpeg_token_ref


def create_mjpeg_app() -> Flask:
    app = Flask(__name__)

    @app.before_request
    def authorize_control():
        if request.path.startswith("/pipeline/") and request.method == "POST":
            expected = backend_client_ref.api_key if backend_client_ref else ""
            provided = request.headers.get("X-API-Key", "")
            if not expected or expected == "CHANGE_ME" or not hmac.compare_digest(expected, provided):
                return jsonify({"message": "Invalid or missing worker key."}), 401
        return None

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
        source_status = get_stream_source_status()
        payload["captureDirectSourceUrl"] = (
            source_status.get("captureDirectSourceUrl")
            or active_config.get("capture_direct_source_url", "")
        )
        payload["activeCaptureUrl"] = (
            pipeline_runtime.get_active_capture_url()
            or payload["captureSourceUrl"]
            or payload["captureDirectSourceUrl"]
        )
        payload["sourceKind"] = (
            source_status.get("sourceKind")
            or classify_source_kind(payload["sourceUrl"])
        )
        payload["sourceUrlResolved"] = bool(source_status.get("sourceUrlResolved", False))
        payload["lastResolveError"] = str(source_status.get("lastResolveError") or "")
        payload["processedStreamPath"] = activation.get("readyProcessedStreamPath") or active_config.get("processed_stream_path", "")
        payload["selectedStreamProfileId"] = (
            active_config.get("selected_stream_profile_id", "")
            or activation.get("readyStreamProfileId")
            or activation.get("requestedStreamProfileId")
            or get_stream_rotation_status().get("selectedStreamProfileId", "")
        )
        payload["streamProfileCameraIds"] = eligible_camera_ids
        payload["recentRuntimeCameraIds"] = get_recent_runtime_camera_ids()
        payload["frontendAckRequired"] = bool(activation.get("frontendAckRequired", True))
        payload["frontendAckPhase"] = str(activation.get("frontendAckPhase") or "")
        payload["frontendAckNonce"] = str(activation.get("frontendAckNonce") or "")
        payload["activationSessionId"] = str(activation.get("activationSessionId") or "")
        payload["streamRotation"] = get_stream_rotation_status()
        payload["streamSchedule"] = get_stream_schedule_status()
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
    global active_stream_ref, active_mjpeg_server_ref, active_control_panel_ref, active_snapshot_writer_ref, backend_client_ref

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

    if backend_client_ref is not None:
        backend_client_ref.close()
        backend_client_ref = None

    cv2.destroyAllWindows()
    release_single_instance_lock()


atexit.register(cleanup_runtime)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


@dataclass(frozen=True)
class StreamUrlResolution:
    original_url: str
    capture_url: str
    resolved: bool = False


def is_youtube_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    host = parsed.netloc.lower()
    return host.endswith("youtube.com") or host.endswith("youtu.be") or host.endswith("youtube-nocookie.com")


def classify_source_kind(stream_url: str) -> str:
    normalized = str(stream_url or "").strip()
    if not normalized:
        return "unknown"
    return "youtube" if is_youtube_url(normalized) else "direct"


def update_stream_source_status(
    *,
    source_url: str = "",
    source_kind: str = "",
    source_url_resolved: bool = False,
    capture_direct_source_url: str = "",
    capture_source_url: str = "",
    last_resolve_error: str = "",
):
    with stream_source_status_lock:
        normalized_source_kind = str(source_kind or classify_source_kind(source_url)).strip() or "unknown"
        stream_source_status_ref["sourceKind"] = normalized_source_kind
        stream_source_status_ref["sourceUrlResolved"] = bool(source_url_resolved)
        stream_source_status_ref["captureDirectSourceUrl"] = str(capture_direct_source_url or "").strip()
        stream_source_status_ref["captureSourceUrl"] = str(capture_source_url or "").strip()
        stream_source_status_ref["lastResolveError"] = str(last_resolve_error or "").strip()


def get_stream_source_status() -> dict:
    with stream_source_status_lock:
        return dict(stream_source_status_ref)


def build_youtube_resolve_command(
    stream_url: str,
    *,
    cookies_from_browser: str = "",
    cookies_file: str = "",
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-warnings",
        "--no-playlist",
        "-f",
        "best[protocol^=m3u8]/best",
        "-g",
    ]
    browser_name = str(cookies_from_browser or "").strip()
    cookies_path = str(cookies_file or "").strip()
    if browser_name:
        command.extend(["--cookies-from-browser", browser_name])
    elif cookies_path:
        command.extend(["--cookies", cookies_path])
    command.append(stream_url)
    return command


def resolve_youtube_stream_url(
    stream_url: str,
    *,
    timeout_seconds: int = 20,
    cookies_from_browser: str = "",
    cookies_file: str = "",
) -> str:
    command = build_youtube_resolve_command(
        stream_url,
        cookies_from_browser=cookies_from_browser,
        cookies_file=cookies_file,
    )
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
    capture_url = resolve_youtube_stream_url(
        original_url,
        timeout_seconds=timeout_seconds,
        cookies_from_browser=str((cfg or {}).get("youtube_cookies_from_browser") or "").strip(),
        cookies_file=str((cfg or {}).get("youtube_cookies_file") or "").strip(),
    )
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


def can_reach_mediamtx_api(api_base: str) -> bool:
    normalized_api_base = str(api_base or "").strip().rstrip("/")
    if not normalized_api_base:
        return False
    try:
        response = requests.get(
            f"{normalized_api_base}/v3/paths/list",
            timeout=2,
        )
        return bool(response.ok)
    except Exception:
        return False


def ensure_local_mediamtx_running(cfg: dict) -> bool:
    api_base = str(cfg.get("mediamtx_api_url") or "").strip().rstrip("/")
    if not api_base:
        return False
    if can_reach_mediamtx_api(api_base):
        return True

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    mediamtx_dir = os.path.join(repo_root, "tools", "mediamtx")
    mediamtx_exe = os.path.join(mediamtx_dir, "mediamtx.exe")
    mediamtx_config = os.path.join(mediamtx_dir, "mediamtx.yml")
    if not os.path.exists(mediamtx_exe) or not os.path.exists(mediamtx_config):
        return False

    logger.warning("MediaMTX API indisponivel; tentando subir relay local automaticamente.")
    creationflags = 0
    creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        subprocess.Popen(
            [mediamtx_exe, mediamtx_config],
            cwd=mediamtx_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception as exc:
        logger.warning("Falha ao iniciar MediaMTX local automaticamente: %s", exc)
        return False

    deadline = time.time() + 8.0
    while time.time() < deadline:
        if can_reach_mediamtx_api(api_base):
            logger.info("MediaMTX local iniciado automaticamente.")
            return True
        time.sleep(0.4)

    logger.warning("MediaMTX local nao respondeu no prazo apos inicializacao automatica.")
    return False


def ensure_mediamtx_source_path(cfg: dict, path_name: str, source_url: str) -> bool:
    api_base = str(cfg.get("mediamtx_api_url") or "").strip().rstrip("/")
    if not api_base or not path_name or not source_url:
        return False

    if not can_reach_mediamtx_api(api_base) and not ensure_local_mediamtx_running(cfg):
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
    source_kind = classify_source_kind(original_source_url)
    try:
        resolved_source = resolve_stream_source_url(original_source_url, cfg)
    except Exception as exc:
        update_stream_source_status(
            source_url=original_source_url,
            source_kind=source_kind,
            source_url_resolved=False,
            capture_direct_source_url="",
            capture_source_url="",
            last_resolve_error=str(exc),
        )
        raise
    raw_path = str(raw_stream_path or f"raw/{normalized_camera_id}").strip()
    processed_path = str(processed_stream_path or f"processed/{normalized_camera_id}").strip()
    rtsp_base = str(cfg.get("mediamtx_rtsp_url") or "rtsp://localhost:8554").strip().rstrip("/")

    capture_direct_source_url = resolved_source.capture_url
    capture_source_url = capture_direct_source_url
    capture_fallback_source_url = ""
    if capture_direct_source_url and ensure_mediamtx_source_path(cfg, raw_path, capture_direct_source_url):
        capture_source_url = f"{rtsp_base}/{raw_path}"
        capture_fallback_source_url = capture_direct_source_url

    pipeline_cfg["camera_id"] = normalized_camera_id
    pipeline_cfg["raw_stream_path"] = raw_path
    pipeline_cfg["processed_stream_path"] = processed_path
    pipeline_cfg["stream_url"] = resolved_source.original_url
    pipeline_cfg["capture_source_url"] = capture_source_url
    pipeline_cfg["capture_fallback_source_url"] = capture_fallback_source_url
    pipeline_cfg["capture_direct_source_url"] = capture_direct_source_url
    pipeline_cfg["source_url_resolved"] = resolved_source.resolved
    pipeline_cfg["source_kind"] = source_kind
    pipeline_cfg["publisher_rtsp_url"] = f"{rtsp_base}/{processed_path}"
    pipeline_cfg.setdefault("publisher_fps", 10)
    pipeline_cfg.setdefault("publisher_ffmpeg_bin", "ffmpeg")
    update_stream_source_status(
        source_url=resolved_source.original_url,
        source_kind=source_kind,
        source_url_resolved=resolved_source.resolved,
        capture_direct_source_url=capture_direct_source_url,
        capture_source_url=capture_source_url,
        last_resolve_error="",
    )
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
        schedule_store: StreamScheduleStore,
        on_save_stream_schedule_rule,
        on_delete_stream_schedule_rule,
        on_toggle_stream_schedule_rule,
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
        self.schedule_store = schedule_store
        self.on_save_stream_schedule_rule = on_save_stream_schedule_rule
        self.on_delete_stream_schedule_rule = on_delete_stream_schedule_rule
        self.on_toggle_stream_schedule_rule = on_toggle_stream_schedule_rule
        self.should_close = False
        self._stream_profile_ids: list[str] = []
        self._schedule_rule_ids: list[str] = []
        self._schedule_profile_ids: list[str] = []
        self._schedule_profile_vars: dict[str, tk.BooleanVar] = {}
        self._selected_schedule_rule_id = ""
        self._updating_stream_selection = False
        self._updating_schedule_selection = False
        self._root = tk.Tk()
        self._root.title("Controles de Configuracao")
        self._root.resizable(True, True)
        self._root.geometry("980x860")
        self._root.minsize(860, 720)
        self._root.protocol("WM_DELETE_WINDOW", self.request_close)
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(0, weight=1)

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
        self._count_direction_var = tk.StringVar(value=count_direction_display_name("any"))
        self._secondary_verification_enabled_var = tk.BooleanVar(
            value=bool(DEFAULT_SECONDARY_VERIFICATION_ENABLED)
        )
        self._secondary_verification_band_var = tk.IntVar(
            value=int(DEFAULT_SECONDARY_VERIFICATION_BAND_PX)
        )
        self._stream_rotation_enabled_var = tk.BooleanVar(value=bool(stream_rotation_enabled))
        schedule = self.schedule_store.get_schedule()
        self._schedule_name_var = tk.StringVar()
        self._schedule_start_var = tk.StringVar(value="00:00")
        self._schedule_end_var = tk.StringVar(value="01:00")
        self._schedule_enabled_var = tk.BooleanVar(value=True)
        self._schedule_timezone_var = tk.StringVar(
            value=f"Timezone: {schedule.get('timezone', DEFAULT_STREAM_SCHEDULE['timezone'])}"
        )
        self._schedule_status_var = tk.StringVar(value="")
        self._rotation_status_var = tk.StringVar(value="")
        self._stream_summary_var = tk.StringVar(value="")
        self._schedule_summary_var = tk.StringVar(value="")
        self._schedule_validation_var = tk.StringVar(value="")
        self._active_stream_var = tk.StringVar(value="-")
        self._next_stream_var = tk.StringVar(value="-")
        self._active_schedule_var = tk.StringVar(value="-")
        self._rotation_state_var = tk.StringVar(value="-")
        self._safe_window_var = tk.StringVar(value="-")
        self._schedule_name_var.trace_add("write", lambda *_: self._update_schedule_form_state())
        self._schedule_start_var.trace_add("write", lambda *_: self._update_schedule_form_state())
        self._schedule_end_var.trace_add("write", lambda *_: self._update_schedule_form_state())
        self._schedule_enabled_var.trace_add("write", lambda *_: self._update_schedule_form_state())
        status_frame = ttk.LabelFrame(frame, text="Estado Operacional")
        status_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        status_frame.columnconfigure(0, weight=1)
        status_frame.columnconfigure(1, weight=1)
        ttk.Label(status_frame, text="Stream ativa").grid(row=0, column=0, sticky="w")
        ttk.Label(status_frame, textvariable=self._active_stream_var, wraplength=360).grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=(0, 4)
        )
        ttk.Label(status_frame, text="Proxima stream").grid(row=0, column=1, sticky="w")
        ttk.Label(status_frame, textvariable=self._next_stream_var, wraplength=360).grid(
            row=1, column=1, sticky="w", pady=(0, 4)
        )
        ttk.Label(status_frame, text="Agenda atual").grid(row=2, column=0, sticky="w")
        ttk.Label(status_frame, textvariable=self._active_schedule_var, wraplength=360).grid(
            row=3, column=0, sticky="w", padx=(0, 12), pady=(0, 4)
        )
        ttk.Label(status_frame, text="Rotacao").grid(row=2, column=1, sticky="w")
        ttk.Label(status_frame, textvariable=self._rotation_state_var, wraplength=360).grid(
            row=3, column=1, sticky="w", pady=(0, 4)
        )
        ttk.Label(status_frame, text="Janela segura").grid(row=4, column=0, sticky="w")
        ttk.Label(status_frame, textvariable=self._safe_window_var, wraplength=360).grid(
            row=5, column=0, columnspan=2, sticky="w"
        )

        ttk.Label(frame, text="Ir para preset salvo").grid(row=1, column=0, sticky="w")
        self._stream_selector = ttk.Combobox(frame, state="readonly", width=48)
        self._stream_selector.grid(row=2, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        self._stream_selector.bind("<<ComboboxSelected>>", self._handle_profile_preview)
        ttk.Button(frame, text="Carregar", command=self.load_selected_stream).grid(
            row=2, column=1, sticky="ew", pady=(0, 6)
        )
        self._stream_table = ttk.Treeview(
            frame,
            columns=("status", "name", "camera_id", "url"),
            show="headings",
            height=5,
            selectmode="browse",
        )
        self._stream_table.heading("status", text="Estado")
        self._stream_table.heading("name", text="Stream")
        self._stream_table.heading("camera_id", text="Camera ID")
        self._stream_table.heading("url", text="URL")
        self._stream_table.column("status", width=150, minwidth=120, stretch=False, anchor="center")
        self._stream_table.column("name", width=130, minwidth=90, stretch=False)
        self._stream_table.column("camera_id", width=92, minwidth=80, stretch=False)
        self._stream_table.column("url", width=190, minwidth=120, stretch=True)
        self._stream_table.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._stream_table.bind("<<TreeviewSelect>>", self._handle_profile_table_select)

        ttk.Label(frame, text="Apelido da stream").grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Entry(frame, textvariable=self._stream_name_var).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        ttk.Label(frame, text="Camera ID").grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Entry(frame, textvariable=self._stream_camera_id_var).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        ttk.Label(frame, text="URL da stream").grid(row=8, column=0, columnspan=2, sticky="w")
        ttk.Entry(frame, textvariable=self._stream_url_var).grid(
            row=9, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Abrir URL na visualizacao", command=self.open_stream_url).grid(
            row=10, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(frame, text="Salvar preset na esteira", command=self.save_stream_profile).grid(
            row=10, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Label(frame, textvariable=self._stream_summary_var, wraplength=360).grid(
            row=11, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Button(frame, text="Trocar na proxima janela segura", command=self.force_stream_switch).grid(
            row=12, column=0, sticky="ew", padx=(0, 6), pady=(0, 10)
        )
        ttk.Button(frame, text="Apagar preset da esteira", command=self.delete_stream_profile).grid(
            row=12, column=1, sticky="ew", pady=(0, 10)
        )

        ttk.Label(frame, text="Rotacao Randômica", font=("Segoe UI", 11, "bold")).grid(
            row=13, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Checkbutton(
            frame,
            text="Ativar entre rounds",
            variable=self._stream_rotation_enabled_var,
            command=self.toggle_stream_rotation,
        ).grid(
            row=14, column=0, sticky="w", padx=(0, 6), pady=(0, 10)
        )
        ttk.Button(frame, text="Sortear proxima", command=self.queue_random_stream).grid(
            row=14, column=1, sticky="ew", pady=(0, 10)
        )
        ttk.Label(frame, textvariable=self._rotation_status_var, wraplength=360).grid(
            row=15, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        ttk.Label(frame, text="Agenda por Hora", font=("Segoe UI", 11, "bold")).grid(
            row=16, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Label(frame, textvariable=self._schedule_timezone_var).grid(
            row=17, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        self._schedule_table = ttk.Treeview(
            frame,
            columns=("active", "name", "window", "profiles"),
            show="headings",
            height=4,
            selectmode="browse",
        )
        self._schedule_table.heading("active", text="Estado")
        self._schedule_table.heading("name", text="Agenda")
        self._schedule_table.heading("window", text="Faixa")
        self._schedule_table.heading("profiles", text="Streams")
        self._schedule_table.column("active", width=78, minwidth=68, stretch=False, anchor="center")
        self._schedule_table.column("name", width=120, minwidth=90, stretch=False)
        self._schedule_table.column("window", width=90, minwidth=80, stretch=False)
        self._schedule_table.column("profiles", width=200, minwidth=120, stretch=True)
        self._schedule_table.grid(row=18, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self._schedule_table.bind("<<TreeviewSelect>>", self._handle_schedule_rule_select)
        ttk.Label(frame, textvariable=self._schedule_summary_var, wraplength=360).grid(
            row=19, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )

        ttk.Label(frame, text="Nome da agenda").grid(row=20, column=0, columnspan=2, sticky="w")
        ttk.Entry(frame, textvariable=self._schedule_name_var).grid(
            row=21, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        ttk.Label(frame, text="Inicio (HH:MM)").grid(row=22, column=0, sticky="w")
        ttk.Label(frame, text="Fim (HH:MM)").grid(row=22, column=1, sticky="w")
        ttk.Entry(frame, textvariable=self._schedule_start_var).grid(
            row=23, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Entry(frame, textvariable=self._schedule_end_var).grid(
            row=23, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Checkbutton(
            frame,
            text="Regra ativa",
            variable=self._schedule_enabled_var,
        ).grid(row=24, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(frame, text="Streams permitidas").grid(row=25, column=0, columnspan=2, sticky="w")
        self._schedule_profiles_frame = ttk.Frame(frame)
        self._schedule_profiles_frame.grid(row=26, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(frame, textvariable=self._schedule_validation_var, wraplength=360).grid(
            row=27, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        ttk.Button(frame, text="Nova Regra", command=self.new_schedule_rule).grid(
            row=28, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(frame, text="Salvar Regra", command=self.save_schedule_rule).grid(
            row=28, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Alternar Ativa", command=self.toggle_schedule_rule).grid(
            row=29, column=0, sticky="ew", padx=(0, 6), pady=(0, 10)
        )
        ttk.Button(frame, text="Apagar Regra", command=self.delete_schedule_rule).grid(
            row=29, column=1, sticky="ew", pady=(0, 10)
        )
        ttk.Label(frame, textvariable=self._schedule_status_var, wraplength=360).grid(
            row=30, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        ttk.Label(frame, text="Ajuste de ROI e Linha", font=("Segoe UI", 11, "bold")).grid(
            row=31, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Label(frame, text="Direcao de contagem").grid(row=32, column=0, columnspan=2, sticky="w")
        self._count_direction_selector = ttk.Combobox(
            frame,
            state="readonly",
            values=(
                "Qualquer direcao",
                "Cima para baixo",
                "Baixo para cima",
                "Esquerda para direita",
                "Direita para esquerda",
            ),
            textvariable=self._count_direction_var,
        )
        self._count_direction_selector.grid(
            row=33, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        self._count_direction_selector.bind("<<ComboboxSelected>>", self._handle_direction_change)

        ttk.Button(frame, text="Editar ROI", command=self.editor.begin_roi_mode).grid(
            row=34, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(frame, text="Editar Linha", command=self.editor.begin_line_mode).grid(
            row=34, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Salvar calibracao", command=self.save).grid(
            row=35, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(frame, text="Cancelar", command=self.cancel).grid(
            row=35, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Resetar Stream", command=self.reset_stream).grid(
            row=36, column=0, columnspan=2, sticky="ew"
        )
        ttk.Button(frame, text="Fechar painel", command=self.request_close).grid(
            row=37, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )

        self._mode_var = tk.StringVar(value=f"Modo: {self.editor.mode}")
        self._message_var = tk.StringVar(value=self.editor.message)
        ttk.Label(frame, textvariable=self._mode_var).grid(
            row=38, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Label(frame, textvariable=self._message_var, wraplength=360).grid(
            row=39, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )

        ttk.Label(frame, text="Atalhos opcionais: R, L, S, C, T, Q").grid(
            row=40, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        self._refresh_stream_profiles()
        self._refresh_schedule_profiles()
        self._refresh_schedule_rules()
        self.set_active_stream_profile(self.stream_store.get_selected_profile())

    def refresh(self):
        self._mode_var.set(f"Modo: {self.editor.mode}")
        self._message_var.set(self.editor.message)
        schedule_status = get_stream_schedule_status()
        rotation_status = get_stream_rotation_status()
        activation_status = get_camera_activation_status()
        self._refresh_schedule_rules(selected_rule_id=self._get_selected_schedule_rule_id())
        self._schedule_status_var.set(self._build_schedule_status_text(schedule_status))
        self._rotation_status_var.set(str(rotation_status.get("lastMessage") or "").strip())
        self._active_stream_var.set(
            str(activation_status.get("readyProfileLabel") or rotation_status.get("activeProfileLabel") or "-")
        )
        self._next_stream_var.set(self._build_next_stream_status(schedule_status, rotation_status))
        self._active_schedule_var.set(self._build_active_schedule_status(schedule_status))
        self._rotation_state_var.set(self._build_rotation_state(rotation_status))
        self._safe_window_var.set(self._build_safe_window_status(schedule_status, rotation_status, activation_status))
        self._update_schedule_validation()
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
            secondary_enabled, secondary_band_px = self._get_secondary_verification_settings()
            profile = self.on_save_stream_profile(
                self._stream_name_var.get(),
                self._stream_url_var.get(),
                self._stream_camera_id_var.get(),
                secondary_enabled,
                secondary_band_px,
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
        self._handle_profile_table_select()
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
        self._populate_stream_form(profile)

    def new_schedule_rule(self):
        self._selected_schedule_rule_id = ""
        self._schedule_name_var.set("")
        self._schedule_start_var.set("00:00")
        self._schedule_end_var.set("01:00")
        self._schedule_enabled_var.set(True)
        self._set_schedule_allowed_profile_ids([])
        self._refresh_schedule_rules()
        self._update_schedule_summary()
        self._update_schedule_validation()

    def save_schedule_rule(self):
        try:
            rule = self.on_save_stream_schedule_rule(
                self._selected_schedule_rule_id,
                self._schedule_name_var.get(),
                self._schedule_start_var.get(),
                self._schedule_end_var.get(),
                self._get_selected_schedule_profile_ids(),
                bool(self._schedule_enabled_var.get()),
            )
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return

        self._selected_schedule_rule_id = str(rule.get("id") or "")
        self._refresh_schedule_rules(selected_rule_id=self._selected_schedule_rule_id)
        self._set_schedule_form(rule)
        self.editor.message = "Agenda por hora salva."

    def delete_schedule_rule(self):
        rule_id = self._get_selected_schedule_rule_id()
        if not rule_id:
            self.editor.message = "Selecione uma agenda por hora."
            return

        try:
            deleted = self.on_delete_stream_schedule_rule(rule_id)
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return

        self.new_schedule_rule()
        self.editor.message = f"Agenda removida: {str(deleted.get('name') or '').strip() or rule_id}"

    def toggle_schedule_rule(self):
        rule_id = self._get_selected_schedule_rule_id()
        if not rule_id:
            self.editor.message = "Selecione uma agenda por hora."
            return

        try:
            rule = self.on_toggle_stream_schedule_rule(rule_id)
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return

        self._selected_schedule_rule_id = str(rule.get("id") or "")
        self._refresh_schedule_rules(selected_rule_id=self._selected_schedule_rule_id)
        self._set_schedule_form(rule)
        self.editor.message = (
            "Agenda ativada." if rule.get("enabled") else "Agenda desativada."
        )

    def _refresh_stream_profiles(self, selected_profile_id: str | None = None):
        profiles = self.stream_store.list_profiles()
        self._stream_profile_ids = [str(profile.get("id") or "") for profile in profiles]
        self._stream_selector["values"] = [format_stream_profile_label(profile) for profile in profiles]

        active_id = str(self.stream_store.get_selected_profile().get("id") or "")
        target_id = selected_profile_id or active_id
        schedule_status = get_stream_schedule_status()
        rotation_status = get_stream_rotation_status()
        eligible_ids = {
            str(profile_id or "").strip()
            for profile_id in schedule_status.get("eligibleProfileIds", [])
            if str(profile_id or "").strip()
        }
        pending_id = str(rotation_status.get("pendingProfileId") or "").strip()
        self._updating_stream_selection = True
        try:
            for item_id in self._stream_table.get_children():
                self._stream_table.delete(item_id)
            for profile in profiles:
                profile_id = str(profile.get("id") or "")
                status_badges = []
                if profile_id == active_id:
                    status_badges.append("Ativa")
                if profile_id == pending_id:
                    status_badges.append("Pendente")
                if profile_id in eligible_ids:
                    status_badges.append("Em agenda")
                if profile_id == target_id and profile_id != active_id:
                    status_badges.append("Selecionada")
                _, name, camera_id, stream_url = format_stream_profile_table_row(profile, active=profile_id == active_id)
                self._stream_table.insert(
                    "",
                    "end",
                    iid=profile_id,
                    values=(
                        " | ".join(status_badges) if status_badges else "-",
                        name,
                        camera_id,
                        stream_url,
                    ),
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
        finally:
            self._updating_stream_selection = False

        self._refresh_schedule_profiles()
        self._refresh_schedule_rules()
        self._update_stream_summary()

    def _refresh_schedule_profiles(self):
        profiles = self.stream_store.list_profiles()
        current_ids = self._get_selected_schedule_profile_ids()
        self._schedule_profile_ids = [str(profile.get("id") or "") for profile in profiles]
        for child in self._schedule_profiles_frame.winfo_children():
            child.destroy()
        self._schedule_profile_vars = {}
        for profile in profiles:
            profile_id = str(profile.get("id") or "").strip()
            if not profile_id:
                continue
            var = tk.BooleanVar(value=False)
            self._schedule_profile_vars[profile_id] = var
            ttk.Checkbutton(
                self._schedule_profiles_frame,
                text=format_stream_profile_label(profile),
                variable=var,
                command=self._update_schedule_form_state,
            ).pack(anchor="w")
        self._set_schedule_allowed_profile_ids(current_ids)
        self._update_schedule_summary()

    def _refresh_schedule_rules(self, selected_rule_id: str | None = None):
        rules = self.schedule_store.list_rules()
        profiles_by_id = {
            str(profile.get("id") or "").strip(): format_stream_profile_label(profile)
            for profile in self.stream_store.list_profiles()
            if str(profile.get("id") or "").strip()
        }
        schedule_status = get_stream_schedule_status()
        active_rule_ids = {
            str(rule_id or "").strip()
            for rule_id in schedule_status.get("activeRuleIds", [])
            if str(rule_id or "").strip()
        }
        fallback_active_rule_id = str(schedule_status.get("activeRuleId") or "")
        if fallback_active_rule_id:
            active_rule_ids.add(fallback_active_rule_id)
        self._schedule_rule_ids = [str(rule.get("id") or "") for rule in rules]
        target_rule_id = selected_rule_id or self._selected_schedule_rule_id
        self._updating_schedule_selection = True
        try:
            for item_id in self._schedule_table.get_children():
                self._schedule_table.delete(item_id)
            for rule in rules:
                rule_id = str(rule.get("id") or "")
                self._schedule_table.insert(
                    "",
                    "end",
                    iid=rule_id,
                    values=format_stream_schedule_rule_row(
                        profiles_by_id,
                        rule,
                        active=rule_id in active_rule_ids,
                    ),
                )

            if target_rule_id in self._schedule_rule_ids:
                self._schedule_table.selection_set(target_rule_id)
                self._schedule_table.focus(target_rule_id)
                self._schedule_table.see(target_rule_id)
            elif self._schedule_rule_ids:
                self._schedule_table.selection_set(self._schedule_rule_ids[0])
                self._schedule_table.focus(self._schedule_rule_ids[0])
        finally:
            self._updating_schedule_selection = False
        self._update_schedule_summary()

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
                self._populate_stream_form(profile)
                break

    def _handle_profile_table_select(self, _event=None):
        if self._updating_stream_selection:
            return
        profile_id = self._get_selected_stream_profile_id()
        if not profile_id:
            return
        if profile_id in self._stream_profile_ids:
            self._stream_selector.current(self._stream_profile_ids.index(profile_id))
        for profile in self.stream_store.list_profiles():
            if str(profile.get("id") or "") == profile_id:
                self._populate_stream_form(profile)
                break

    def _handle_schedule_rule_select(self, _event=None):
        if self._updating_schedule_selection:
            return
        rule_id = self._get_selected_schedule_rule_id()
        if not rule_id:
            return
        for rule in self.schedule_store.list_rules():
            if str(rule.get("id") or "").strip() == rule_id:
                self._selected_schedule_rule_id = rule_id
                self._set_schedule_form(rule)
                break
        self._update_schedule_summary()
        self._update_schedule_validation()

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

    def _get_selected_schedule_rule_id(self) -> str:
        selection = self._schedule_table.selection()
        if selection:
            return str(selection[0])
        return str(self._selected_schedule_rule_id or "")

    def _get_selected_schedule_profile_ids(self) -> list[str]:
        return [
            profile_id
            for profile_id in self._schedule_profile_ids
            if self._schedule_profile_vars.get(profile_id) is not None
            and bool(self._schedule_profile_vars[profile_id].get())
        ]

    def _set_schedule_allowed_profile_ids(self, allowed_profile_ids: list[str]):
        allowed_set = {str(profile_id or "").strip() for profile_id in allowed_profile_ids if str(profile_id or "").strip()}
        for profile_id in self._schedule_profile_ids:
            var = self._schedule_profile_vars.get(profile_id)
            if var is not None:
                var.set(profile_id in allowed_set)

    def _set_schedule_form(self, rule: dict):
        self._selected_schedule_rule_id = str(rule.get("id") or "")
        self._schedule_name_var.set(str(rule.get("name") or ""))
        self._schedule_start_var.set(str(rule.get("start_time") or "00:00"))
        self._schedule_end_var.set(str(rule.get("end_time") or "01:00"))
        self._schedule_enabled_var.set(bool(rule.get("enabled", True)))
        self._set_schedule_allowed_profile_ids(rule.get("allowed_profile_ids", []))
        self._update_schedule_summary()
        self._update_schedule_validation()

    def _populate_stream_form(self, profile: dict):
        self._stream_name_var.set(str(profile.get("name") or ""))
        self._stream_camera_id_var.set(str(profile.get("camera_id") or ""))
        self._stream_url_var.set(str(profile.get("stream_url") or ""))
        self._count_direction_var.set(count_direction_display_name(str(profile.get("count_direction") or "any")))
        self._update_stream_summary()

    def _update_stream_summary(self):
        profile_id = self._get_selected_stream_profile_id()
        if not profile_id:
            self._stream_summary_var.set("Selecione uma stream para editar, carregar ou agendar a troca.")
            return
        for profile in self.stream_store.list_profiles():
            if str(profile.get("id") or "") == profile_id:
                self._stream_summary_var.set(
                    " | ".join(
                        [
                            f"Selecionada: {format_stream_profile_label(profile)}",
                            f"Direcao: {count_direction_display_name(str(profile.get('count_direction') or 'any'))}",
                            f"URL: {shorten_text(str(profile.get('stream_url') or ''), max_len=88)}",
                        ]
                    )
                )
                return

    def _update_schedule_form_state(self):
        self._update_schedule_summary()
        self._update_schedule_validation()

    def _update_schedule_summary(self):
        labels_by_id = {
            str(profile.get("id") or "").strip(): format_stream_profile_label(profile)
            for profile in self.stream_store.list_profiles()
        }
        selected_labels = [
            labels_by_id.get(profile_id, profile_id)
            for profile_id in self._get_selected_schedule_profile_ids()
        ]
        selected_summary = ", ".join(selected_labels[:3]) if selected_labels else "nenhuma stream"
        if len(selected_labels) > 3:
            selected_summary += f" +{len(selected_labels) - 3}"
        name = self._schedule_name_var.get().strip() or (self._selected_schedule_rule_id or "Nova regra")
        self._schedule_summary_var.set(
            f"{name} | {self._schedule_start_var.get().strip() or '--:--'}-{self._schedule_end_var.get().strip() or '--:--'} | {selected_summary}"
        )

    def _update_schedule_validation(self):
        try:
            candidate_rule_id = self._selected_schedule_rule_id or "__draft__"
            candidate_rule = {
                "id": candidate_rule_id,
                "name": self._schedule_name_var.get(),
                "enabled": bool(self._schedule_enabled_var.get()),
                "start_time": self._schedule_start_var.get(),
                "end_time": self._schedule_end_var.get(),
                "allowed_profile_ids": self._get_selected_schedule_profile_ids(),
            }
            rules = []
            replaced = False
            for rule in self.schedule_store.list_rules():
                if str(rule.get("id") or "").strip() == candidate_rule_id:
                    rules.append(candidate_rule)
                    replaced = True
                else:
                    rules.append(rule)
            if not replaced:
                rules.append(candidate_rule)
            validate_stream_schedule_rules(rules, set(self._schedule_profile_ids))
        except ValueError as exc:
            self._schedule_validation_var.set(str(exc))
            return
        if not self._get_selected_schedule_profile_ids():
            self._schedule_validation_var.set("Selecione pelo menos uma stream permitida.")
            return
        self._schedule_validation_var.set("Regra valida para salvar.")

    def _build_schedule_status_text(self, schedule_status: dict) -> str:
        active_rule_name = str(schedule_status.get("activeRuleName") or "").strip()
        active_window = str(schedule_status.get("activeWindow") or "").strip()
        status_parts = []
        if active_rule_name or active_window:
            status_parts.append(active_rule_name or active_window)
        elif schedule_status.get("outsideWindowRestricted"):
            status_parts.append("Fora da agenda configurada")
        elif schedule_status.get("restricted"):
            status_parts.append("Agenda ativa")
        else:
            status_parts.append("Sem restricao por horario")
        if schedule_status.get("pendingEnforcement"):
            status_parts.append("troca pendente")
        if schedule_status.get("lastMessage"):
            status_parts.append(str(schedule_status["lastMessage"]))
        return " | ".join(part for part in status_parts if part)

    def _build_active_schedule_status(self, schedule_status: dict) -> str:
        active_rule_name = str(schedule_status.get("activeRuleName") or "").strip()
        active_window = str(schedule_status.get("activeWindow") or "").strip()
        if active_rule_name or active_window:
            details = active_rule_name or "Agenda ativa"
            if active_window:
                details = f"{details} | {active_window}"
            return details
        if schedule_status.get("outsideWindowRestricted"):
            return "Fora da agenda configurada"
        return "Sem restricao por horario"

    def _build_rotation_state(self, rotation_status: dict) -> str:
        if rotation_status.get("pending"):
            return str(rotation_status.get("lastMessage") or "Troca pendente para a proxima janela segura.")
        if rotation_status.get("enabled"):
            return str(rotation_status.get("lastMessage") or "Rotacao ativa entre rounds.")
        return "Rotacao desativada"

    def _build_next_stream_status(self, schedule_status: dict, rotation_status: dict) -> str:
        pending_profile_id = str(rotation_status.get("pendingProfileId") or "").strip()
        if pending_profile_id:
            for profile in self.stream_store.list_profiles():
                if str(profile.get("id") or "").strip() == pending_profile_id:
                    return f"Pendente: {format_stream_profile_label(profile)}"
        if schedule_status.get("pendingEnforcement"):
            return str(schedule_status.get("lastMessage") or "Agenda aguardando janela segura.")
        return "Nenhuma troca pendente"

    def _build_safe_window_status(self, schedule_status: dict, rotation_status: dict, activation_status: dict) -> str:
        if not activation_status.get("readyForRounds", True):
            return "Nao pronta para rounds: aguardando ativacao da stream."
        if schedule_status.get("pendingEnforcement"):
            return str(schedule_status.get("lastMessage") or "Agenda aguardando janela segura.")
        if rotation_status.get("pending"):
            return str(rotation_status.get("lastMessage") or "Rotacao aguardando janela segura.")
        return "Livre para operar na stream atual."

    def _build_source_runtime_status(self, activation_status: dict) -> str:
        active_config = pipeline_runtime.get_config() or {}
        source_status = get_stream_source_status()
        source_url = str(active_config.get("stream_url") or "").strip()
        capture_source_url = str(active_config.get("capture_source_url") or "").strip()
        capture_direct_source_url = str(
            source_status.get("captureDirectSourceUrl")
            or active_config.get("capture_direct_source_url")
            or ""
        ).strip()
        active_capture_url = str(
            pipeline_runtime.get_active_capture_url()
            or capture_source_url
            or capture_direct_source_url
        ).strip()
        source_kind = str(
            source_status.get("sourceKind")
            or active_config.get("source_kind")
            or classify_source_kind(source_url)
        ).strip() or "unknown"
        last_resolve_error = str(source_status.get("lastResolveError") or "").strip()
        resolved = bool(source_status.get("sourceUrlResolved", False))
        profile_label = str(
            activation_status.get("readyProfileLabel")
            or activation_status.get("requestedProfileLabel")
            or ""
        ).strip()

        parts = []
        if profile_label:
            parts.append(profile_label)
        parts.append(f"Tipo: {source_kind}")
        if source_url:
            parts.append(f"Origem: {shorten_text(source_url, max_len=96)}")
        if source_kind == "youtube":
            parts.append("Resolucao: ok via yt-dlp" if resolved else "Resolucao: pendente")
        if active_capture_url:
            parts.append(f"Captura: {shorten_text(active_capture_url, max_len=96)}")
        elif capture_direct_source_url:
            parts.append(f"Captura direta: {shorten_text(capture_direct_source_url, max_len=96)}")
        if last_resolve_error:
            parts.append(f"Erro: {shorten_text(last_resolve_error, max_len=140)}")
        return " | ".join(parts) if parts else "Sem source ativa no momento."

    def request_close(self):
        self.should_close = True

    def close(self):
        try:
            self._root.destroy()
        except tk.TclError:
            pass


class CompactEditorControlPanel:
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
        schedule_store: StreamScheduleStore,
        on_save_stream_schedule_rule,
        on_delete_stream_schedule_rule,
        on_toggle_stream_schedule_rule,
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
        self.schedule_store = schedule_store
        self.on_save_stream_schedule_rule = on_save_stream_schedule_rule
        self.on_delete_stream_schedule_rule = on_delete_stream_schedule_rule
        self.on_toggle_stream_schedule_rule = on_toggle_stream_schedule_rule
        self.should_close = False
        self._stream_profile_ids: list[str] = []
        self._schedule_camera_ids: list[str] = []
        self._camera_rule_ids: list[str] = []
        self._selected_schedule_camera_id = ""
        self._selected_schedule_rule_id = ""
        self._updating_stream_selection = False
        self._updating_schedule_camera = False
        self._updating_schedule_rule = False
        self._selected_rule_is_legacy = False

        self._root = tk.Tk()
        self._root.title("Controles de Configuracao")
        self._root.resizable(True, True)
        self._root.geometry("1040x760")
        self._root.minsize(920, 680)
        self._root.protocol("WM_DELETE_WINDOW", self.request_close)
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(0, weight=1)

        self._stream_name_var = tk.StringVar()
        self._stream_camera_id_var = tk.StringVar()
        self._stream_url_var = tk.StringVar()
        self._count_direction_var = tk.StringVar(value=count_direction_display_name("any"))
        self._secondary_verification_enabled_var = tk.BooleanVar(
            value=bool(DEFAULT_SECONDARY_VERIFICATION_ENABLED)
        )
        self._secondary_verification_band_var = tk.IntVar(
            value=int(DEFAULT_SECONDARY_VERIFICATION_BAND_PX)
        )
        self._stream_rotation_enabled_var = tk.BooleanVar(value=bool(stream_rotation_enabled))

        schedule = self.schedule_store.get_schedule()
        self._schedule_name_var = tk.StringVar()
        self._schedule_start_var = tk.StringVar(value="09:00")
        self._schedule_end_var = tk.StringVar(value="19:00")
        self._schedule_enabled_var = tk.BooleanVar(value=True)
        self._schedule_timezone_var = tk.StringVar(
            value=f"Timezone: {schedule.get('timezone', DEFAULT_STREAM_SCHEDULE['timezone'])}"
        )
        self._mode_var = tk.StringVar(value=f"Modo: {self.editor.mode}")
        self._message_var = tk.StringVar(value=self.editor.message)
        self._stream_summary_var = tk.StringVar(value="")
        self._schedule_summary_var = tk.StringVar(value="")
        self._schedule_validation_var = tk.StringVar(value="")
        self._schedule_status_var = tk.StringVar(value="")
        self._schedule_legacy_var = tk.StringVar(value="")
        self._rotation_status_var = tk.StringVar(value="")
        self._active_stream_var = tk.StringVar(value="-")
        self._next_stream_var = tk.StringVar(value="-")
        self._active_schedule_var = tk.StringVar(value="-")
        self._rotation_state_var = tk.StringVar(value="-")
        self._safe_window_var = tk.StringVar(value="-")
        self._source_runtime_var = tk.StringVar(value="-")
        self._schedule_form_dirty = False
        self._programmatic_schedule_form_update = False

        self._schedule_name_var.trace_add("write", lambda *_: self._handle_schedule_form_change())
        self._schedule_start_var.trace_add("write", lambda *_: self._handle_schedule_form_change())
        self._schedule_end_var.trace_add("write", lambda *_: self._handle_schedule_form_change())
        self._schedule_enabled_var.trace_add("write", lambda *_: self._handle_schedule_form_change())

        root_frame = ttk.Frame(self._root, padding=10)
        root_frame.grid(row=0, column=0, sticky="nsew")
        root_frame.columnconfigure(0, weight=1)
        root_frame.rowconfigure(0, weight=1)

        self._notebook = ttk.Notebook(root_frame)
        self._notebook.grid(row=0, column=0, sticky="nsew")

        self._tab_streams = ttk.Frame(self._notebook, padding=10)
        self._tab_agenda = ttk.Frame(self._notebook, padding=10)
        self._tab_calibracao = ttk.Frame(self._notebook, padding=10)
        self._tab_estado = ttk.Frame(self._notebook, padding=10)
        self._notebook.add(self._tab_streams, text="Streams")
        self._notebook.add(self._tab_agenda, text="Agenda")
        self._notebook.add(self._tab_calibracao, text="Calibracao")
        self._notebook.add(self._tab_estado, text="Estado")

        self._build_state_tab()
        self._build_streams_tab()
        self._build_agenda_tab()
        self._build_calibracao_tab()
        self._build_footer(root_frame)

        self._refresh_stream_profiles()
        self._refresh_schedule_cameras()
        self._refresh_schedule_rules()
        self.set_active_stream_profile(self.stream_store.get_selected_profile())

    def _build_state_tab(self):
        self._tab_estado.columnconfigure(0, weight=1)
        state_frame = ttk.LabelFrame(self._tab_estado, text="Estado Operacional")
        state_frame.grid(row=0, column=0, sticky="nsew")
        state_frame.columnconfigure(0, weight=1)
        state_frame.columnconfigure(1, weight=1)

        ttk.Label(state_frame, text="Stream ativa").grid(row=0, column=0, sticky="w")
        ttk.Label(state_frame, textvariable=self._active_stream_var, wraplength=420).grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=(0, 8)
        )
        ttk.Label(state_frame, text="Proxima stream").grid(row=0, column=1, sticky="w")
        ttk.Label(state_frame, textvariable=self._next_stream_var, wraplength=420).grid(
            row=1, column=1, sticky="w", pady=(0, 8)
        )
        ttk.Label(state_frame, text="Agenda atual").grid(row=2, column=0, sticky="w")
        ttk.Label(state_frame, textvariable=self._active_schedule_var, wraplength=420).grid(
            row=3, column=0, sticky="w", padx=(0, 12), pady=(0, 8)
        )
        ttk.Label(state_frame, text="Rotacao").grid(row=2, column=1, sticky="w")
        ttk.Label(state_frame, textvariable=self._rotation_state_var, wraplength=420).grid(
            row=3, column=1, sticky="w", pady=(0, 8)
        )
        ttk.Label(state_frame, text="Janela segura").grid(row=4, column=0, sticky="w")
        ttk.Label(state_frame, textvariable=self._safe_window_var, wraplength=420).grid(
            row=5, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(state_frame, text="Source runtime").grid(row=6, column=0, sticky="w", pady=(8, 0))
        ttk.Label(state_frame, textvariable=self._source_runtime_var, wraplength=860).grid(
            row=7, column=0, columnspan=2, sticky="w"
        )

    def _build_streams_tab(self):
        self._tab_streams.columnconfigure(0, weight=5)
        self._tab_streams.columnconfigure(1, weight=4)
        self._tab_streams.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(self._tab_streams, text="Esteira de Streams")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.columnconfigure(1, weight=0)
        left.rowconfigure(1, weight=1)

        ttk.Label(left, text="Ir para preset salvo").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self._stream_selector = ttk.Combobox(left, state="readonly")
        self._stream_selector.grid(row=0, column=0, sticky="ew", padx=(0, 110))
        self._stream_selector.bind("<<ComboboxSelected>>", self._handle_profile_preview)
        ttk.Button(left, text="Carregar", command=self.load_selected_stream).grid(
            row=0, column=1, sticky="e"
        )

        self._stream_table = ttk.Treeview(
            left,
            columns=("status", "name", "camera_id"),
            show="headings",
            height=12,
            selectmode="browse",
        )
        self._stream_table.heading("status", text="Estado")
        self._stream_table.heading("name", text="Stream")
        self._stream_table.heading("camera_id", text="Camera")
        self._stream_table.column("status", width=170, minwidth=120, stretch=False, anchor="center")
        self._stream_table.column("name", width=180, minwidth=120, stretch=True)
        self._stream_table.column("camera_id", width=120, minwidth=100, stretch=False)
        self._stream_table.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 8))
        self._stream_table.bind("<<TreeviewSelect>>", self._handle_profile_table_select)

        ttk.Label(left, textvariable=self._stream_summary_var, wraplength=460).grid(
            row=2, column=0, columnspan=2, sticky="w"
        )

        right = ttk.LabelFrame(self._tab_streams, text="Preset Selecionado")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.columnconfigure(1, weight=1)

        ttk.Label(right, text="Apelido").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Entry(right, textvariable=self._stream_name_var).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        ttk.Label(right, text="Camera ID").grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Entry(right, textvariable=self._stream_camera_id_var).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        ttk.Label(right, text="URL da stream").grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Entry(right, textvariable=self._stream_url_var).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(0, 8)
        )
        ttk.Button(right, text="Abrir URL na visualizacao", command=self.open_stream_url).grid(
            row=6, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(right, text="Salvar preset", command=self.save_stream_profile).grid(
            row=6, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(right, text="Trocar na proxima janela segura", command=self.force_stream_switch).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        ttk.Button(right, text="Apagar preset", command=self.delete_stream_profile).grid(
            row=8, column=0, columnspan=2, sticky="ew"
        )

    def _build_agenda_tab(self):
        self._tab_agenda.columnconfigure(0, weight=4)
        self._tab_agenda.columnconfigure(1, weight=5)
        self._tab_agenda.rowconfigure(1, weight=1)

        header = ttk.LabelFrame(self._tab_agenda, text="Resumo da Agenda")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, textvariable=self._schedule_timezone_var).grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self._schedule_status_var, wraplength=860).grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )

        left = ttk.LabelFrame(self._tab_agenda, text="Cameras da Esteira")
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self._schedule_camera_table = ttk.Treeview(
            left,
            columns=("status", "camera_id", "summary"),
            show="headings",
            height=14,
            selectmode="browse",
        )
        self._schedule_camera_table.heading("status", text="Estado")
        self._schedule_camera_table.heading("camera_id", text="Camera")
        self._schedule_camera_table.heading("summary", text="Horarios")
        self._schedule_camera_table.column("status", width=120, minwidth=100, stretch=False, anchor="center")
        self._schedule_camera_table.column("camera_id", width=130, minwidth=110, stretch=False)
        self._schedule_camera_table.column("summary", width=280, minwidth=180, stretch=True)
        self._schedule_camera_table.grid(row=0, column=0, sticky="nsew")
        self._schedule_camera_table.bind("<<TreeviewSelect>>", self._handle_schedule_camera_select)

        right = ttk.Frame(self._tab_agenda)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        selected_camera_frame = ttk.LabelFrame(right, text="Horarios da Camera Selecionada")
        selected_camera_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        selected_camera_frame.columnconfigure(0, weight=1)
        ttk.Label(selected_camera_frame, textvariable=self._schedule_summary_var, wraplength=500).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(selected_camera_frame, textvariable=self._schedule_legacy_var, wraplength=500).grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )

        rules_frame = ttk.LabelFrame(right, text="Faixas da Camera")
        rules_frame.grid(row=1, column=0, sticky="nsew")
        rules_frame.columnconfigure(0, weight=1)
        rules_frame.rowconfigure(0, weight=1)
        self._camera_rule_table = ttk.Treeview(
            rules_frame,
            columns=("status", "window", "name"),
            show="headings",
            height=8,
            selectmode="browse",
        )
        self._camera_rule_table.heading("status", text="Estado")
        self._camera_rule_table.heading("window", text="Faixa")
        self._camera_rule_table.heading("name", text="Descricao")
        self._camera_rule_table.column("status", width=130, minwidth=100, stretch=False, anchor="center")
        self._camera_rule_table.column("window", width=120, minwidth=100, stretch=False)
        self._camera_rule_table.column("name", width=260, minwidth=160, stretch=True)
        self._camera_rule_table.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self._camera_rule_table.bind("<<TreeviewSelect>>", self._handle_schedule_rule_select)

        editor_frame = ttk.LabelFrame(rules_frame, text="Editar Faixa")
        editor_frame.grid(row=1, column=0, sticky="ew")
        editor_frame.columnconfigure(0, weight=1)
        editor_frame.columnconfigure(1, weight=1)
        ttk.Label(editor_frame, text="Descricao").grid(row=0, column=0, columnspan=2, sticky="w")
        self._schedule_name_entry = ttk.Entry(editor_frame, textvariable=self._schedule_name_var)
        self._schedule_name_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(editor_frame, text="Inicio (HH:MM)").grid(row=2, column=0, sticky="w")
        ttk.Label(editor_frame, text="Fim (HH:MM)").grid(row=2, column=1, sticky="w")
        self._schedule_start_entry = ttk.Entry(editor_frame, textvariable=self._schedule_start_var)
        self._schedule_start_entry.grid(row=3, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        self._schedule_end_entry = ttk.Entry(editor_frame, textvariable=self._schedule_end_var)
        self._schedule_end_entry.grid(row=3, column=1, sticky="ew", pady=(0, 6))
        ttk.Checkbutton(editor_frame, text="Faixa ativa", variable=self._schedule_enabled_var).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        ttk.Label(editor_frame, textvariable=self._schedule_validation_var, wraplength=500).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        ttk.Button(editor_frame, text="Nova faixa para camera", command=self.new_schedule_rule).grid(
            row=6, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        self._schedule_save_button = ttk.Button(editor_frame, text="Salvar faixa", command=self.save_schedule_rule)
        self._schedule_save_button.grid(row=6, column=1, sticky="ew", pady=(0, 6))
        ttk.Button(editor_frame, text="Ativar/Desativar", command=self.toggle_schedule_rule).grid(
            row=7, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(editor_frame, text="Apagar faixa", command=self.delete_schedule_rule).grid(
            row=7, column=1, sticky="ew"
        )

    def _build_calibracao_tab(self):
        self._tab_calibracao.columnconfigure(0, weight=1)
        frame = ttk.LabelFrame(self._tab_calibracao, text="Ajuste de ROI e Linha")
        frame.grid(row=0, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Direcao de contagem").grid(row=0, column=0, columnspan=2, sticky="w")
        self._count_direction_selector = ttk.Combobox(
            frame,
            state="readonly",
            values=(
                "Qualquer direcao",
                "Cima para baixo",
                "Baixo para cima",
                "Esquerda para direita",
                "Direita para esquerda",
            ),
            textvariable=self._count_direction_var,
        )
        self._count_direction_selector.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._count_direction_selector.bind("<<ComboboxSelected>>", self._handle_direction_change)
        ttk.Checkbutton(
            frame,
            text="Ativar dupla verificacao da markline",
            variable=self._secondary_verification_enabled_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(frame, text="Faixa secundaria (px)").grid(row=3, column=0, sticky="w")
        self._secondary_verification_band_spinbox = ttk.Spinbox(
            frame,
            from_=4,
            to=120,
            textvariable=self._secondary_verification_band_var,
            increment=1,
            width=10,
            command=self._normalize_secondary_verification_band_value,
        )
        self._secondary_verification_band_spinbox.grid(row=3, column=1, sticky="ew", pady=(0, 8))
        ttk.Button(frame, text="Editar ROI", command=self.editor.begin_roi_mode).grid(
            row=4, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(frame, text="Editar Linha", command=self.editor.begin_line_mode).grid(
            row=4, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Salvar calibracao", command=self.save).grid(
            row=5, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(frame, text="Cancelar", command=self.cancel).grid(
            row=5, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Resetar Stream", command=self.reset_stream).grid(
            row=6, column=0, columnspan=2, sticky="ew"
        )

    def _build_footer(self, root_frame: ttk.Frame):
        footer = ttk.Frame(root_frame)
        footer.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        footer.columnconfigure(0, weight=1)
        footer.columnconfigure(1, weight=0)
        ttk.Label(footer, textvariable=self._mode_var).grid(row=0, column=0, sticky="w")
        ttk.Label(footer, textvariable=self._message_var, wraplength=760).grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )
        ttk.Button(footer, text="Fechar painel", command=self.request_close).grid(
            row=0, column=1, rowspan=2, sticky="e"
        )

    def refresh(self):
        self._mode_var.set(f"Modo: {self.editor.mode}")
        self._message_var.set(self.editor.message)
        self._update_state_summary()
        if self._should_pause_schedule_refresh():
            self._update_schedule_editor_summary()
        else:
            self._refresh_schedule_cameras()
            self._refresh_schedule_rules()
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
            self.editor.message = "Selecione uma stream salva."
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
            self.editor.message = "Selecione uma stream salva."
            return
        try:
            deleted = self.on_delete_stream_profile(profile_id)
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return
        self._refresh_stream_profiles()
        self._handle_profile_table_select()
        self.editor.message = f"Stream apagada: {format_stream_profile_label(deleted)}"

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
        self._refresh_schedule_cameras()

    def queue_random_stream(self):
        try:
            profile = self.on_queue_random_stream()
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return
        if profile:
            self._refresh_stream_profiles(selected_profile_id=profile.get("id"))
            self._update_state_summary()

    def set_active_stream_profile(self, profile: dict):
        self._refresh_stream_profiles(selected_profile_id=profile.get("id"))
        self._populate_stream_form(profile)
        selected_camera_id = str(profile.get("id") or "")
        if selected_camera_id:
            self._selected_schedule_camera_id = selected_camera_id
            self._refresh_schedule_cameras(selected_camera_id=selected_camera_id)
            self._refresh_schedule_rules()
        self._update_state_summary()

    def new_schedule_rule(self):
        if not self._selected_schedule_camera_id:
            self.editor.message = "Selecione uma camera na aba Agenda."
            return
        self._selected_schedule_rule_id = ""
        self._selected_rule_is_legacy = False
        self._set_schedule_form_values("", "09:00", "19:00", True)
        self._schedule_legacy_var.set("")
        self._update_schedule_editor_summary()

    def save_schedule_rule(self):
        camera_id = self._selected_schedule_camera_id
        if not camera_id:
            self.editor.message = "Selecione uma camera na aba Agenda."
            return
        if self._selected_rule_is_legacy:
            self.editor.message = "Regra compartilhada legado: crie uma nova faixa por camera e depois remova a antiga."
            return
        profile = self.stream_store.get_selected_profile()
        for item in self.stream_store.list_profiles():
            if str(item.get("id") or "") == camera_id:
                profile = item
                break
        schedule_name, start_time, end_time, enabled = self._read_schedule_form_values()
        rule_name = schedule_name or (
            f"Horario {str(profile.get('camera_id') or camera_id)} "
            f"{start_time}-{end_time}"
        )
        try:
            rule = self.on_save_stream_schedule_rule(
                self._selected_schedule_rule_id,
                rule_name,
                start_time,
                end_time,
                [camera_id],
                enabled,
            )
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return
        self._selected_schedule_rule_id = str(rule.get("id") or "")
        self._refresh_schedule_cameras(selected_camera_id=camera_id)
        self._refresh_schedule_rules(selected_rule_id=self._selected_schedule_rule_id)
        self._populate_schedule_form(rule, force=True)
        self.editor.message = f"Horario salvo para {str(profile.get('camera_id') or camera_id)}."

    def delete_schedule_rule(self):
        rule_id = self._get_selected_schedule_rule_id()
        if not rule_id:
            self.editor.message = "Selecione uma faixa para apagar."
            return
        try:
            deleted = self.on_delete_stream_schedule_rule(rule_id)
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return
        self.new_schedule_rule()
        self._refresh_schedule_cameras(selected_camera_id=self._selected_schedule_camera_id)
        self._refresh_schedule_rules()
        self.editor.message = f"Faixa removida: {str(deleted.get('name') or '').strip() or rule_id}"

    def toggle_schedule_rule(self):
        rule_id = self._get_selected_schedule_rule_id()
        if not rule_id:
            self.editor.message = "Selecione uma faixa para ativar ou desativar."
            return
        try:
            rule = self.on_toggle_stream_schedule_rule(rule_id)
        except (ValueError, RuntimeError) as exc:
            self.editor.message = str(exc)
            return
        self._selected_schedule_rule_id = str(rule.get("id") or "")
        self._refresh_schedule_cameras(selected_camera_id=self._selected_schedule_camera_id)
        self._refresh_schedule_rules(selected_rule_id=self._selected_schedule_rule_id)
        self._populate_schedule_form(rule)
        self.editor.message = "Faixa ativada." if rule.get("enabled") else "Faixa desativada."

    def _refresh_stream_profiles(self, selected_profile_id: str | None = None):
        profiles = self.stream_store.list_profiles()
        self._stream_profile_ids = [str(profile.get("id") or "") for profile in profiles]
        self._stream_selector["values"] = [format_stream_profile_label(profile) for profile in profiles]
        active_id = str(self.stream_store.get_selected_profile().get("id") or "")
        target_id = selected_profile_id or active_id
        schedule_status = get_stream_schedule_status()
        rotation_status = get_stream_rotation_status()
        eligible_ids = {
            str(profile_id or "").strip()
            for profile_id in schedule_status.get("eligibleProfileIds", [])
            if str(profile_id or "").strip()
        }
        pending_id = str(rotation_status.get("pendingProfileId") or "").strip()
        self._updating_stream_selection = True
        try:
            for item_id in self._stream_table.get_children():
                self._stream_table.delete(item_id)
            for profile in profiles:
                profile_id = str(profile.get("id") or "")
                status_badges = []
                if profile_id == active_id:
                    status_badges.append("Ativa")
                if profile_id == pending_id:
                    status_badges.append("Pendente")
                if profile_id in eligible_ids:
                    status_badges.append("Em agenda")
                _, name, camera_id, _stream_url = format_stream_profile_table_row(profile, active=profile_id == active_id)
                self._stream_table.insert(
                    "",
                    "end",
                    iid=profile_id,
                    values=(" | ".join(status_badges) if status_badges else "-", name, camera_id),
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
        finally:
            self._updating_stream_selection = False
        self._update_stream_summary()

    def _refresh_schedule_cameras(self, selected_camera_id: str | None = None):
        profiles = self.stream_store.list_profiles()
        self._schedule_camera_ids = [str(profile.get("id") or "") for profile in profiles]
        target_camera_id = selected_camera_id or self._selected_schedule_camera_id or (
            self._schedule_camera_ids[0] if self._schedule_camera_ids else ""
        )
        self._updating_schedule_camera = True
        try:
            for item_id in self._schedule_camera_table.get_children():
                self._schedule_camera_table.delete(item_id)
            for profile in profiles:
                profile_id = str(profile.get("id") or "")
                self._schedule_camera_table.insert(
                    "",
                    "end",
                    iid=profile_id,
                    values=(
                        self._build_camera_schedule_status(profile),
                        str(profile.get("camera_id") or profile_id),
                        self._build_camera_schedule_summary(profile),
                    ),
                )
            if target_camera_id in self._schedule_camera_ids:
                self._selected_schedule_camera_id = target_camera_id
                self._schedule_camera_table.selection_set(target_camera_id)
                self._schedule_camera_table.focus(target_camera_id)
                self._schedule_camera_table.see(target_camera_id)
        finally:
            self._updating_schedule_camera = False
        self._update_schedule_editor_summary()

    def _refresh_schedule_rules(self, selected_rule_id: str | None = None):
        profile_id = self._selected_schedule_camera_id
        rules = self._get_schedule_rules_for_camera(profile_id)
        schedule_status = get_stream_schedule_status()
        active_rule_ids = {
            str(rule_id or "").strip()
            for rule_id in schedule_status.get("activeRuleIds", [])
            if str(rule_id or "").strip()
        }
        target_rule_id = selected_rule_id or self._selected_schedule_rule_id
        self._camera_rule_ids = [str(rule.get("id") or "") for rule in rules]
        self._updating_schedule_rule = True
        try:
            for item_id in self._camera_rule_table.get_children():
                self._camera_rule_table.delete(item_id)
            for rule in rules:
                rule_id = str(rule.get("id") or "")
                status = "Ativa agora" if rule_id in active_rule_ids else ("Ligada" if bool(rule.get("enabled", True)) else "Pausada")
                if len(normalize_allowed_profile_ids(rule.get("allowed_profile_ids"))) > 1:
                    status = f"{status} | Legado"
                self._camera_rule_table.insert(
                    "",
                    "end",
                    iid=rule_id,
                    values=(
                        status,
                        format_stream_schedule_window(rule),
                        str(rule.get("name") or "").strip(),
                    ),
                )
            if target_rule_id in self._camera_rule_ids:
                self._selected_schedule_rule_id = target_rule_id
                self._camera_rule_table.selection_set(target_rule_id)
                self._camera_rule_table.focus(target_rule_id)
                self._camera_rule_table.see(target_rule_id)
            elif self._camera_rule_ids:
                first_rule_id = self._camera_rule_ids[0]
                self._selected_schedule_rule_id = first_rule_id
                self._camera_rule_table.selection_set(first_rule_id)
                self._camera_rule_table.focus(first_rule_id)
                self._camera_rule_table.see(first_rule_id)
        finally:
            self._updating_schedule_rule = False
        selected_rule = self._get_selected_rule()
        if selected_rule is not None:
            self._populate_schedule_form(selected_rule)
        else:
            self.new_schedule_rule()

    def _handle_profile_preview(self, _event=None):
        if self._updating_stream_selection:
            return
        index = self._stream_selector.current()
        if index < 0 or index >= len(self._stream_profile_ids):
            return
        profile_id = self._stream_profile_ids[index]
        self._stream_table.selection_set(profile_id)
        self._stream_table.focus(profile_id)
        self._handle_profile_table_select()

    def _handle_profile_table_select(self, _event=None):
        if self._updating_stream_selection:
            return
        profile_id = self._get_selected_stream_profile_id()
        if not profile_id:
            return
        if profile_id in self._stream_profile_ids:
            self._stream_selector.current(self._stream_profile_ids.index(profile_id))
        for profile in self.stream_store.list_profiles():
            if str(profile.get("id") or "") == profile_id:
                self._populate_stream_form(profile)
                self._selected_schedule_camera_id = profile_id
                self._refresh_schedule_cameras(selected_camera_id=profile_id)
                self._refresh_schedule_rules()
                break

    def _handle_schedule_camera_select(self, _event=None):
        if self._updating_schedule_camera:
            return
        selection = self._schedule_camera_table.selection()
        if not selection:
            return
        self._selected_schedule_camera_id = str(selection[0])
        self._selected_schedule_rule_id = ""
        self._refresh_schedule_rules()

    def _handle_schedule_rule_select(self, _event=None):
        if self._updating_schedule_rule:
            return
        rule = self._get_selected_rule()
        if rule is None:
            return
        self._selected_schedule_rule_id = str(rule.get("id") or "")
        self._populate_schedule_form(rule, force=True)

    def _handle_direction_change(self, _event=None):
        self._commit_count_direction()

    def _commit_count_direction(self):
        direction = normalize_count_direction(self._count_direction_var.get())
        self._count_direction_var.set(count_direction_display_name(direction))
        self.on_set_count_direction(direction)

    def _get_selected_stream_profile_id(self) -> str:
        selection = self._stream_table.selection()
        if selection:
            return str(selection[0])
        index = self._stream_selector.current()
        if 0 <= index < len(self._stream_profile_ids):
            return self._stream_profile_ids[index]
        return ""

    def _get_selected_schedule_rule_id(self) -> str:
        selection = self._camera_rule_table.selection()
        if selection:
            return str(selection[0])
        return str(self._selected_schedule_rule_id or "")

    def _get_selected_rule(self) -> dict | None:
        target_rule_id = self._get_selected_schedule_rule_id()
        for rule in self._get_schedule_rules_for_camera(self._selected_schedule_camera_id):
            if str(rule.get("id") or "") == target_rule_id:
                return dict(rule)
        return None

    def _get_schedule_rules_for_camera(self, profile_id: str) -> list[dict]:
        if not profile_id:
            return []
        rules = []
        for rule in self.schedule_store.list_rules():
            allowed_ids = normalize_allowed_profile_ids(rule.get("allowed_profile_ids"))
            if profile_id in allowed_ids:
                rules.append(dict(rule))
        rules.sort(key=lambda item: (schedule_time_to_minutes(item.get("start_time")), str(item.get("id") or "")))
        return rules

    def _populate_stream_form(self, profile: dict):
        self._stream_name_var.set(str(profile.get("name") or ""))
        self._stream_camera_id_var.set(str(profile.get("camera_id") or ""))
        self._stream_url_var.set(str(profile.get("stream_url") or ""))
        self._count_direction_var.set(count_direction_display_name(str(profile.get("count_direction") or "any")))
        self._secondary_verification_enabled_var.set(
            bool(profile.get("secondary_verification_enabled", DEFAULT_SECONDARY_VERIFICATION_ENABLED))
        )
        self._secondary_verification_band_var.set(
            int(profile.get("secondary_verification_band_px", DEFAULT_SECONDARY_VERIFICATION_BAND_PX) or DEFAULT_SECONDARY_VERIFICATION_BAND_PX)
        )
        self._normalize_secondary_verification_band_value()
        self._update_stream_summary()

    def _normalize_secondary_verification_band_value(self):
        self._secondary_verification_band_var.set(
            normalize_secondary_verification_band_px(
                self._secondary_verification_band_var.get(),
                fallback=DEFAULT_SECONDARY_VERIFICATION_BAND_PX,
            )
        )

    def _get_secondary_verification_settings(self) -> tuple[bool, int]:
        self._normalize_secondary_verification_band_value()
        return (
            bool(self._secondary_verification_enabled_var.get()),
            int(self._secondary_verification_band_var.get()),
        )

    def _handle_schedule_form_change(self):
        if not self._programmatic_schedule_form_update:
            self._schedule_form_dirty = True
        self._update_schedule_editor_summary()

    def _is_editing_schedule_form(self) -> bool:
        focused_widget = self._root.focus_get()
        return focused_widget in {
            getattr(self, "_schedule_name_entry", None),
            getattr(self, "_schedule_start_entry", None),
            getattr(self, "_schedule_end_entry", None),
        }

    def _should_pause_schedule_refresh(self) -> bool:
        return self._schedule_form_dirty or self._is_editing_schedule_form()

    def _set_schedule_form_values(self, name: str, start_time: str, end_time: str, enabled: bool):
        self._programmatic_schedule_form_update = True
        try:
            self._schedule_name_var.set(name)
            self._schedule_start_var.set(start_time)
            self._schedule_end_var.set(end_time)
            self._schedule_enabled_var.set(enabled)
        finally:
            self._programmatic_schedule_form_update = False
        self._schedule_form_dirty = False

    def _read_schedule_form_values(self) -> tuple[str, str, str, bool]:
        name = self._schedule_name_entry.get().strip()
        start_time = self._schedule_start_entry.get().strip()
        end_time = self._schedule_end_entry.get().strip()
        enabled = bool(self._schedule_enabled_var.get())
        self._programmatic_schedule_form_update = True
        try:
            self._schedule_name_var.set(name)
            self._schedule_start_var.set(start_time)
            self._schedule_end_var.set(end_time)
        finally:
            self._programmatic_schedule_form_update = False
        self._schedule_form_dirty = False
        return name, start_time, end_time, enabled

    def _populate_schedule_form(self, rule: dict, force: bool = False):
        allowed_ids = normalize_allowed_profile_ids(rule.get("allowed_profile_ids"))
        is_legacy = len(allowed_ids) > 1
        if self._schedule_form_dirty and not force:
            current_rule_id = str(self._selected_schedule_rule_id or "")
            incoming_rule_id = str(rule.get("id") or "")
            if current_rule_id and incoming_rule_id == current_rule_id:
                return
        self._selected_rule_is_legacy = is_legacy
        self._set_schedule_form_values(
            str(rule.get("name") or ""),
            str(rule.get("start_time") or "09:00"),
            str(rule.get("end_time") or "19:00"),
            bool(rule.get("enabled", True)),
        )
        if self._selected_rule_is_legacy:
            self._schedule_legacy_var.set("Regra legado compartilhada entre cameras. Edite criando uma nova faixa por camera.")
            self._schedule_save_button.state(["disabled"])
        else:
            self._schedule_legacy_var.set("")
            self._schedule_save_button.state(["!disabled"])
        self._update_schedule_editor_summary()

    def _update_stream_summary(self):
        profile_id = self._get_selected_stream_profile_id()
        if not profile_id:
            self._stream_summary_var.set("Selecione um preset para carregar, editar ou trocar.")
            return
        for profile in self.stream_store.list_profiles():
            if str(profile.get("id") or "") == profile_id:
                self._stream_summary_var.set(
                    " | ".join(
                        [
                            f"{format_stream_profile_label(profile)}",
                            f"Direcao: {count_direction_display_name(str(profile.get('count_direction') or 'any'))}",
                            (
                                "Dupla verificacao: "
                                + (
                                    f"ligada ({int(profile.get('secondary_verification_band_px', DEFAULT_SECONDARY_VERIFICATION_BAND_PX) or DEFAULT_SECONDARY_VERIFICATION_BAND_PX)} px)"
                                    if bool(profile.get("secondary_verification_enabled", DEFAULT_SECONDARY_VERIFICATION_ENABLED))
                                    else "desligada"
                                )
                            ),
                            shorten_text(str(profile.get("stream_url") or ""), max_len=78),
                        ]
                    )
                )
                return

    def _update_schedule_editor_summary(self):
        profile = None
        for item in self.stream_store.list_profiles():
            if str(item.get("id") or "") == self._selected_schedule_camera_id:
                profile = item
                break
        if profile is None:
            self._schedule_summary_var.set("Selecione uma camera na lista para editar horarios.")
        else:
            camera_label = str(profile.get("camera_id") or profile.get("name") or self._selected_schedule_camera_id)
            self._schedule_summary_var.set(
                f"Camera: {camera_label} | Faixa: {self._schedule_start_var.get().strip() or '--:--'}-{self._schedule_end_var.get().strip() or '--:--'}"
            )
        self._update_schedule_validation()

    def _update_schedule_validation(self):
        camera_id = self._selected_schedule_camera_id
        if not camera_id:
            self._schedule_validation_var.set("Selecione uma camera para criar ou editar a faixa.")
            return
        if self._selected_rule_is_legacy:
            self._schedule_validation_var.set("Regra legado compartilhada: leia, ative/desative ou apague; para editar, crie nova faixa por camera.")
            return
        try:
            candidate_rule_id = self._selected_schedule_rule_id or "__draft__"
            candidate_rule = {
                "id": candidate_rule_id,
                "name": self._schedule_name_var.get(),
                "enabled": bool(self._schedule_enabled_var.get()),
                "start_time": self._schedule_start_var.get(),
                "end_time": self._schedule_end_var.get(),
                "allowed_profile_ids": [camera_id],
            }
            rules = []
            replaced = False
            for rule in self.schedule_store.list_rules():
                if str(rule.get("id") or "").strip() == candidate_rule_id:
                    rules.append(candidate_rule)
                    replaced = True
                else:
                    rules.append(rule)
            if not replaced:
                rules.append(candidate_rule)
            validate_stream_schedule_rules(rules, set(self._schedule_camera_ids))
        except ValueError as exc:
            self._schedule_validation_var.set(str(exc))
            return
        self._schedule_validation_var.set("Faixa valida para salvar.")

    def _build_camera_schedule_summary(self, profile: dict) -> str:
        profile_id = str(profile.get("id") or "")
        rules = self._get_schedule_rules_for_camera(profile_id)
        if not rules:
            return "Sem horario"
        windows = []
        for rule in rules:
            window = format_stream_schedule_window(rule)
            if not window:
                continue
            suffix = " legado" if len(normalize_allowed_profile_ids(rule.get("allowed_profile_ids"))) > 1 else ""
            windows.append(f"{window}{suffix}")
        return ", ".join(windows[:3]) + (f" +{len(windows) - 3}" if len(windows) > 3 else "")

    def _build_camera_schedule_status(self, profile: dict) -> str:
        profile_id = str(profile.get("id") or "")
        rules = self._get_schedule_rules_for_camera(profile_id)
        schedule_status = get_stream_schedule_status()
        eligible_ids = {
            str(item or "").strip()
            for item in schedule_status.get("eligibleProfileIds", [])
            if str(item or "").strip()
        }
        if profile_id in eligible_ids and rules:
            return "Ativa agora"
        if rules:
            return "Fora do horario"
        return "Sem horario"

    def _build_source_runtime_status(self, activation_status: dict) -> str:
        active_config = pipeline_runtime.get_config() or {}
        source_status = get_stream_source_status()
        source_url = str(active_config.get("stream_url") or "").strip()
        capture_source_url = str(active_config.get("capture_source_url") or "").strip()
        capture_direct_source_url = str(
            source_status.get("captureDirectSourceUrl")
            or active_config.get("capture_direct_source_url")
            or ""
        ).strip()
        active_capture_url = str(
            pipeline_runtime.get_active_capture_url()
            or capture_source_url
            or capture_direct_source_url
        ).strip()
        source_kind = str(
            source_status.get("sourceKind")
            or active_config.get("source_kind")
            or classify_source_kind(source_url)
        ).strip() or "unknown"
        last_resolve_error = str(source_status.get("lastResolveError") or "").strip()
        resolved = bool(source_status.get("sourceUrlResolved", False))
        profile_label = str(
            activation_status.get("readyProfileLabel")
            or activation_status.get("requestedProfileLabel")
            or ""
        ).strip()

        parts = []
        if profile_label:
            parts.append(profile_label)
        parts.append(f"Tipo: {source_kind}")
        if source_url:
            parts.append(f"Origem: {shorten_text(source_url, max_len=96)}")
        if source_kind == "youtube":
            parts.append("Resolucao: ok via yt-dlp" if resolved else "Resolucao: pendente")
        if active_capture_url:
            parts.append(f"Captura: {shorten_text(active_capture_url, max_len=96)}")
        elif capture_direct_source_url:
            parts.append(f"Captura direta: {shorten_text(capture_direct_source_url, max_len=96)}")
        if last_resolve_error:
            parts.append(f"Erro: {shorten_text(last_resolve_error, max_len=140)}")
        return " | ".join(parts) if parts else "Sem source ativa no momento."

    def _update_state_summary(self):
        schedule_status = get_stream_schedule_status()
        rotation_status = get_stream_rotation_status()
        activation_status = get_camera_activation_status()
        self._schedule_status_var.set(self._build_schedule_status_text(schedule_status))
        self._rotation_status_var.set(str(rotation_status.get("lastMessage") or "").strip())
        self._active_stream_var.set(
            str(activation_status.get("readyProfileLabel") or rotation_status.get("activeProfileLabel") or "-")
        )
        self._next_stream_var.set(self._build_next_stream_status(schedule_status, rotation_status))
        self._active_schedule_var.set(self._build_active_schedule_status(schedule_status))
        self._rotation_state_var.set(self._build_rotation_state(rotation_status))
        self._safe_window_var.set(self._build_safe_window_status(schedule_status, rotation_status, activation_status))
        self._source_runtime_var.set(self._build_source_runtime_status(activation_status))

    def _build_schedule_status_text(self, schedule_status: dict) -> str:
        active_rule_name = str(schedule_status.get("activeRuleName") or "").strip()
        active_window = str(schedule_status.get("activeWindow") or "").strip()
        status_parts = []
        if active_rule_name or active_window:
            status_parts.append(active_rule_name or active_window)
        elif schedule_status.get("outsideWindowRestricted"):
            status_parts.append("Fora da agenda configurada")
        elif schedule_status.get("restricted"):
            status_parts.append("Agenda ativa")
        else:
            status_parts.append("Sem restricao por horario")
        if schedule_status.get("pendingEnforcement"):
            status_parts.append("troca pendente")
        if schedule_status.get("lastMessage"):
            status_parts.append(str(schedule_status["lastMessage"]))
        return " | ".join(part for part in status_parts if part)

    def _build_active_schedule_status(self, schedule_status: dict) -> str:
        active_rule_name = str(schedule_status.get("activeRuleName") or "").strip()
        active_window = str(schedule_status.get("activeWindow") or "").strip()
        if active_rule_name or active_window:
            details = active_rule_name or "Agenda ativa"
            if active_window:
                details = f"{details} | {active_window}"
            return details
        if schedule_status.get("outsideWindowRestricted"):
            return "Fora da agenda configurada"
        return "Sem restricao por horario"

    def _build_rotation_state(self, rotation_status: dict) -> str:
        if rotation_status.get("pending"):
            return str(rotation_status.get("lastMessage") or "Troca pendente para a proxima janela segura.")
        if rotation_status.get("enabled"):
            return str(rotation_status.get("lastMessage") or "Rotacao ativa entre rounds.")
        return "Rotacao desativada"

    def _build_next_stream_status(self, schedule_status: dict, rotation_status: dict) -> str:
        pending_profile_id = str(rotation_status.get("pendingProfileId") or "").strip()
        if pending_profile_id:
            for profile in self.stream_store.list_profiles():
                if str(profile.get("id") or "").strip() == pending_profile_id:
                    return f"Pendente: {format_stream_profile_label(profile)}"
        if schedule_status.get("pendingEnforcement"):
            return str(schedule_status.get("lastMessage") or "Agenda aguardando janela segura.")
        return "Nenhuma troca pendente"

    def _build_safe_window_status(self, schedule_status: dict, rotation_status: dict, activation_status: dict) -> str:
        if not activation_status.get("readyForRounds", True):
            return "Nao pronta para rounds: aguardando ativacao da stream."
        if schedule_status.get("pendingEnforcement"):
            return str(schedule_status.get("lastMessage") or "Agenda aguardando janela segura.")
        if rotation_status.get("pending"):
            return str(rotation_status.get("lastMessage") or "Rotacao aguardando janela segura.")
        return "Livre para operar na stream atual."

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
    schedule_store = StreamScheduleStore(cfg)
    stream_rotation = cfg["stream_rotation"]
    stream_schedule = cfg["stream_schedule"]
    selected_profile = stream_store.get_selected_profile()
    initial_schedule_state = resolve_stream_schedule_state(stream_schedule, stream_store.list_profiles())
    startup_blocked_by_schedule = bool(initial_schedule_state.get("outsideWindowRestricted"))
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
    update_stream_schedule_status(
        timezone=initial_schedule_state.get("timezone", DEFAULT_STREAM_SCHEDULE["timezone"]),
        activeRuleId=str((initial_schedule_state.get("activeRule") or {}).get("id") or ""),
        activeRuleIds=list(initial_schedule_state.get("activeRuleIds", [])),
        activeRuleName=str(initial_schedule_state.get("activeRuleName") or ""),
        activeWindow=initial_schedule_state.get("activeWindow", ""),
        outsideWindowBehavior=str(initial_schedule_state.get("outsideWindowBehavior") or DEFAULT_STREAM_SCHEDULE["outside_window_behavior"]),
        outsideWindowRestricted=bool(initial_schedule_state.get("outsideWindowRestricted")),
        restricted=bool(initial_schedule_state.get("isRestricted")),
        eligibleProfileIds=list(initial_schedule_state.get("eligibleProfileIds", [])),
        pendingEnforcement=False,
        lastMessage="",
    )
    initial_camera_id = str(cfg.get("camera_id") or selected_profile.get("camera_id") or "").strip()
    initial_profile_id = str(selected_profile.get("id") or cfg.get("selected_stream_profile_id") or "").strip()
    initial_processed_path = str(cfg.get("processed_stream_path") or f"processed/{initial_camera_id}" if initial_camera_id else "").strip()
    initial_profile_label = format_stream_profile_label(selected_profile) if selected_profile else initial_camera_id
    initial_activation_session_id = uuid.uuid4().hex if initial_camera_id and initial_profile_id and not startup_blocked_by_schedule else ""
    initial_activation_requested_at = time.time() if initial_activation_session_id else None
    update_camera_activation_status(
        phase="outside_schedule" if startup_blocked_by_schedule else "waiting_stream",
        activationSessionId=initial_activation_session_id,
        lastRenderableActivationSessionId="",
        activationRequestedAt=initial_activation_requested_at,
        firstCaptureAt=None,
        firstProcessedAt=None,
        firstRenderableFrameAt=None,
        firstPublishedAt=None,
        requestedCameraId=initial_camera_id,
        readyCameraId="",
        requestedStreamProfileId=initial_profile_id,
        readyStreamProfileId="",
        requestedProcessedStreamPath=initial_processed_path,
        readyProcessedStreamPath="",
        requestedProfileLabel=initial_profile_label,
        readyProfileLabel="",
        readyForRounds=False,
        frontendAckRequired=True,
        frontendAckPhase="requested",
        frontendAckNonce="",
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
    if startup_blocked_by_schedule:
        current_pipeline_cfg = dict(cfg)
        logger.info("Pipeline inicial pausada: fora da agenda configurada para a camera/perfil selecionado.")
    else:
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
    fallback_states: dict[int, dict] = {}
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
    secondary_verification_enabled = normalize_secondary_verification_enabled(
        cfg.get("secondary_verification_enabled", DEFAULT_SECONDARY_VERIFICATION_ENABLED)
    )
    secondary_verification_band_px = normalize_secondary_verification_band_px(
        cfg.get("secondary_verification_band_px", DEFAULT_SECONDARY_VERIFICATION_BAND_PX)
    )
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
    pending_camera_activation = (
        {
            "phase": "waiting_stream",
            "activationSessionId": initial_activation_session_id,
            "requestedCameraId": initial_camera_id,
            "requestedStreamProfileId": initial_profile_id,
            "requestedProcessedStreamPath": initial_processed_path,
            "requestedProfileLabel": initial_profile_label,
            "activationStartedAt": initial_activation_requested_at,
            "autoSwitchRound": False,
            "requestNotified": False,
            "readyNotified": False,
        }
        if initial_camera_id and initial_profile_id and not startup_blocked_by_schedule
        else None
    )
    pending_rotation_profile = None
    pending_schedule_profile = None
    last_rotation_round_id = ""
    rotation_boundary_consumed = False
    pending_stream_refresh_started_at = None
    youtube_retry_after = 0.0
    current_round_id = str(cfg.get("round_id", "")).strip()
    last_visual_detections: list[dict] = []
    last_operator_preview = None
    last_operator_preview_at = 0.0

    if isinstance(pending_camera_activation, dict) and not bool(pending_camera_activation.get("requestNotified")):
        if backend.notify_stream_profile_activated(
            initial_camera_id,
            initial_profile_id,
            allow_settling=True,
            auto_switch_round=False,
            phase="requested",
            activation_session_id=str(pending_camera_activation.get("activationSessionId") or ""),
            configuration=cfg,
        ):
            pending_camera_activation["requestNotified"] = True

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
        fallback_states.clear()
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

    def resolve_schedule_state() -> dict:
        return resolve_stream_schedule_state(stream_schedule, stream_store.list_profiles())

    def publish_schedule_status(message: str = ""):
        schedule_state = resolve_schedule_state()
        update_stream_schedule_status(
            timezone=schedule_state.get("timezone", DEFAULT_STREAM_SCHEDULE["timezone"]),
            activeRuleId=str((schedule_state.get("activeRule") or {}).get("id") or ""),
            activeRuleIds=list(schedule_state.get("activeRuleIds", [])),
            activeRuleName=str(schedule_state.get("activeRuleName") or ""),
            activeWindow=schedule_state.get("activeWindow", ""),
            restricted=bool(schedule_state.get("isRestricted")),
            eligibleProfileIds=list(schedule_state.get("eligibleProfileIds", [])),
            pendingEnforcement=isinstance(pending_schedule_profile, dict),
            lastMessage=message,
        )

    def ensure_profile_allowed_for_schedule(profile: dict, *, action_name: str):
        schedule_state = resolve_schedule_state()
        if is_profile_allowed_by_schedule(profile, schedule_state):
            return

        active_rule = schedule_state.get("activeRule") or {}
        window_label = schedule_state.get("activeWindow") or "fora da agenda atual"
        raise ValueError(
            f"Nao e possivel {action_name}: a stream esta fora da faixa horaria ativa "
            f"'{str(active_rule.get('name') or window_label)}' ({window_label})."
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

        schedule_state = resolve_schedule_state()
        profile = select_random_stream_profile(
            schedule_state.get("eligibleProfiles", []),
            str(cfg.get("selected_stream_profile_id") or ""),
            rng=random,
        )
        if profile is None:
            message = "Rotacao requer ao menos dois perfis elegiveis com camera_id e URL."
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

    def maybe_enforce_stream_schedule(backend_round: dict | None):
        nonlocal pending_schedule_profile, pending_rotation_profile

        schedule_state = resolve_schedule_state()
        selected_profile = stream_store.get_selected_profile()

        if (
            isinstance(pending_rotation_profile, dict)
            and not is_profile_allowed_by_schedule(pending_rotation_profile, schedule_state)
        ):
            pending_rotation_profile = None
            publish_rotation_status("Rotacao pendente cancelada pela agenda por hora.")

        target_profile = None
        if schedule_state.get("isRestricted") and not is_profile_allowed_by_schedule(selected_profile, schedule_state):
            target_profile = choose_schedule_enforcement_profile(
                selected_profile,
                schedule_state.get("eligibleProfiles", []),
            )

        if schedule_state.get("outsideWindowRestricted") and target_profile is None:
            if pending_schedule_profile is not None:
                pending_schedule_profile = None
            if pipeline_runtime.is_running():
                queue_pipeline_stop()
            update_camera_activation_status(
                phase="outside_schedule",
                activationSessionId="",
                activationRequestedAt=None,
                firstCaptureAt=None,
                firstProcessedAt=None,
                firstRenderableFrameAt=None,
                firstPublishedAt=None,
                readyCameraId="",
                readyStreamProfileId="",
                readyProcessedStreamPath="",
                readyProfileLabel="",
                readyForRounds=False,
                frontendAckRequired=True,
                frontendAckPhase="requested",
                frontendAckNonce="",
            )
            publish_schedule_status("Fora da agenda configurada; pipeline pausada ate a proxima faixa ativa.")
            return

        if target_profile is None:
            if pending_schedule_profile is not None:
                pending_schedule_profile = None
                publish_schedule_status("Agenda por hora liberada ou ja atendida.")
            else:
                publish_schedule_status("")
            return

        if (
            pending_schedule_profile is None
            or str(pending_schedule_profile.get("id") or "").strip() != str(target_profile.get("id") or "").strip()
        ):
            pending_schedule_profile = dict(target_profile)
            pending_schedule_profile["_activation_allow_settling"] = True

        if not should_apply_pending_stream_rotation(pending_schedule_profile, backend_round):
            status = get_round_status(backend_round) or "indisponivel"
            publish_schedule_status(
                "Agenda por hora exige troca; aguardando janela segura "
                f"({status}): {format_stream_profile_label(target_profile)}"
            )
            return

        current_camera_id = str(cfg.get("camera_id") or "").strip()
        allowed, reason = backend.ensure_camera_change_allowed(
            current_camera_id,
            operation_name="agenda por hora",
            allow_settling=True,
        )
        if not allowed:
            publish_schedule_status(f"Agenda por hora bloqueada pelo backend: {reason}")
            return

        profile = dict(pending_schedule_profile)
        pending_schedule_profile = None
        queue_stream_profile(
            profile,
            message=f"Agenda por hora aplicada em janela segura: {format_stream_profile_label(profile)}",
        )
        publish_schedule_status("Agenda por hora aplicada em janela segura.")

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

        if pending_schedule_profile is not None:
            publish_rotation_status("Rotacao aguardando agenda por hora.")
            return

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
            or bool(stream_schedule.get("rules"))
            or pending_schedule_profile is not None
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

        maybe_enforce_stream_schedule(backend_round)
        maybe_schedule_stream_rotation(backend_round)

    def save_editor_state():
        nonlocal roi, line, secondary_verification_enabled, secondary_verification_band_px

        if editor is None:
            return

        allowed, reason = backend.ensure_camera_change_allowed(cfg.get("camera_id", ""), "salvar calibracao")
        if not allowed:
            editor.message = reason
            return
        next_secondary_enabled = secondary_verification_enabled
        next_secondary_band_px = secondary_verification_band_px
        if control_panel is not None:
            next_secondary_enabled, next_secondary_band_px = control_panel._get_secondary_verification_settings()

        proposal = dict(stream_store.get_selected_profile())
        proposal.update(roi=dict(editor.roi), line=dict(editor.line), count_direction=count_direction,
                        secondary_verification_enabled=next_secondary_enabled,
                        secondary_verification_band_px=next_secondary_band_px)
        if not backend.register_operational_configuration(proposal):
            editor.message = "Alteracao bloqueada: aguarde o encerramento da rodada e a conexao com o backend."
            return
        stream_store.save_selected_profile(
            roi=editor.roi,
            line=editor.line,
            count_direction=count_direction,
            secondary_verification_enabled=next_secondary_enabled,
            secondary_verification_band_px=next_secondary_band_px,
        )
        editor.save(cfg, config_path)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        roi = dict(editor.roi)
        line = dict(editor.line)
        secondary_verification_enabled = next_secondary_enabled
        secondary_verification_band_px = next_secondary_band_px
        if control_panel is not None:
            control_panel.set_active_stream_profile(stream_store.get_selected_profile())

        queue_stream_profile(proposal, message="Calibracao salva; aguardando ativacao da camera.")

    def set_count_direction(direction: str):
        nonlocal count_direction

        proposal = dict(stream_store.get_selected_profile())
        proposal["count_direction"] = normalize_count_direction(direction)
        queue_stream_profile(proposal, message="Direcao atualizada; aguardando ativacao.")

    def request_stream_reset():
        queue_pipeline_refresh()
        if editor is not None:
            editor.message = "Recriando ingestao da source..."

    def queue_stream_profile(profile: dict, *, message: str):
        nonlocal pending_stream_profile, roi, line, count_direction
        nonlocal secondary_verification_enabled, secondary_verification_band_px

        allowed, reason = backend.ensure_camera_change_allowed(
            cfg.get("camera_id", ""), "alterar configuracao", allow_settling=bool(profile.get("_activation_allow_settling")))
        if not allowed:
            raise ValueError(reason)
        if not backend.register_operational_configuration(profile, allow_settling=bool(profile.get("_activation_allow_settling"))):
            raise ValueError("Configuracao recusada pelo backend; perfil nao aplicado.")
        pending_stream_profile = dict(profile)
        roi = dict(profile["roi"])
        line = dict(profile["line"])
        count_direction = profile["count_direction"]
        secondary_verification_enabled = normalize_secondary_verification_enabled(
            profile.get("secondary_verification_enabled", DEFAULT_SECONDARY_VERIFICATION_ENABLED)
        )
        secondary_verification_band_px = normalize_secondary_verification_band_px(
            profile.get("secondary_verification_band_px", DEFAULT_SECONDARY_VERIFICATION_BAND_PX)
        )

        if editor is not None:
            editor.load_values(roi, line, message=message)
        if control_panel is not None:
            control_panel.set_active_stream_profile(profile)
        publish_rotation_status(message)
        publish_schedule_status(message)

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
        profile = next(
            (
                dict(item)
                for item in stream_store.list_profiles()
                if str(item.get("id") or "").strip() == str(profile_id or "").strip()
            ),
            None,
        )
        if profile is None:
            raise ValueError("Stream selecionada nao encontrada.")
        allowed, reason = backend.ensure_camera_change_allowed(cfg.get("camera_id", ""), "carregar stream")
        if not allowed:
            raise ValueError(reason)
        ensure_profile_allowed_for_schedule(profile, action_name="carregar a stream")
        queue_stream_profile(profile, message=f"Stream validada: {format_stream_profile_label(profile)}")
        profile = stream_store.select_profile(profile_id)
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        return profile

    def force_stream_switch(
        profile_id: str,
        stream_name: str,
        stream_url: str,
        camera_id: str,
    ) -> dict:
        nonlocal pending_rotation_profile

        allowed, reason = backend.ensure_camera_change_allowed(cfg.get("camera_id", ""), "troca manual")
        if not allowed:
            raise ValueError(reason)
        target_url = str(stream_url or "").strip()
        target_camera_id = str(camera_id or "").strip()
        target_profile_id = str(profile_id or "").strip()
        if target_profile_id:
            for existing_profile in stream_store.list_profiles():
                if str(existing_profile.get("id") or "") == target_profile_id:
                    target_url = str(existing_profile.get("stream_url") or "").strip()
                    target_camera_id = str(existing_profile.get("camera_id") or "").strip()
                    stream_name = str(existing_profile.get("name") or "").strip()
                    break

        current_camera_id = str(cfg.get("camera_id") or "").strip()
        candidate_profile = next(
            (
                dict(item)
                for item in stream_store.list_profiles()
                if str(item.get("stream_url") or "").strip() == str(target_url or cfg.get("stream_url", "")).strip()
                and str(item.get("camera_id") or "").strip() == str(target_camera_id or cfg.get("camera_id", "")).strip()
            ),
            None,
        )
        if candidate_profile is None:
            candidate_profile = {
                "id": "",
                "name": str(stream_name or "").strip(),
                "stream_url": str(target_url or cfg.get("stream_url", "")).strip(),
                "camera_id": str(target_camera_id or cfg.get("camera_id", "")).strip(),
            }
        ensure_profile_allowed_for_schedule(candidate_profile, action_name="forcar a troca")
        profile, _created = stream_store.save_profile_entry(
            name=stream_name,
            camera_id=target_camera_id or cfg.get("camera_id", ""),
            stream_url=target_url or cfg.get("stream_url", ""),
        )
        # Manual controls obey the same freeze as normal profile selection.
        pending_rotation_profile = None
        return select_stream_profile(profile["id"])

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

        target_url = validate_stream_url(stream_url or "")
        target_camera_id = str(camera_id or cfg.get("camera_id") or "").strip()
        candidate_profile = next(
            (
                dict(item)
                for item in stream_store.list_profiles()
                if str(item.get("stream_url") or "").strip() == target_url
                and str(item.get("camera_id") or "").strip() == target_camera_id
            ),
            None,
        )
        if candidate_profile is None:
            candidate_profile = {
                "id": "",
                "name": str(stream_name or "").strip(),
                "stream_url": target_url,
                "camera_id": target_camera_id,
            }
        ensure_profile_allowed_for_schedule(candidate_profile, action_name="abrir a stream")
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

    def save_stream_profile(
        stream_name: str,
        stream_url: str,
        camera_id: str,
        secondary_enabled: bool | None = None,
        secondary_band_px: int | None = None,
    ) -> dict:
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
            secondary_verification_enabled=secondary_enabled,
            secondary_verification_band_px=secondary_band_px,
        )
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        backend_suffix = ""
        queue_stream_profile(
            profile,
            message=(
                f"Configuracao salva na esteira{backend_suffix}: "
                f"{format_stream_profile_label(profile)}"
            ),
        )
        return profile

    def delete_stream_profile(profile_id: str) -> dict:
        schedule_store.detach_profile_references(profile_id)
        deleted = stream_store.delete_profile(profile_id)
        stream_schedule.clear()
        stream_schedule.update(cfg["stream_schedule"])
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        if control_panel is not None:
            control_panel.set_active_stream_profile(stream_store.get_selected_profile())
        if editor is not None:
            editor.message = f"Stream apagada da esteira: {format_stream_profile_label(deleted)}"
        return deleted

    def save_stream_schedule_rule(
        rule_id: str,
        name: str,
        start_time: str,
        end_time: str,
        allowed_profile_ids: list[str],
        enabled: bool,
    ) -> dict:
        rule, created = schedule_store.save_rule(
            rule_id=rule_id,
            name=name,
            start_time=start_time,
            end_time=end_time,
            allowed_profile_ids=allowed_profile_ids,
            enabled=enabled,
        )
        stream_schedule.clear()
        stream_schedule.update(cfg["stream_schedule"])
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        publish_schedule_status(
            "Agenda por hora salva." if not created else "Agenda por hora adicionada."
        )
        return rule

    def delete_stream_schedule_rule(rule_id: str) -> dict:
        deleted = schedule_store.delete_rule(rule_id)
        stream_schedule.clear()
        stream_schedule.update(cfg["stream_schedule"])
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        publish_schedule_status("Agenda por hora removida.")
        return deleted

    def toggle_stream_schedule_rule(rule_id: str) -> dict:
        toggled = schedule_store.toggle_rule(rule_id)
        stream_schedule.clear()
        stream_schedule.update(cfg["stream_schedule"])
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        publish_schedule_status(
            "Agenda por hora ativada." if toggled.get("enabled") else "Agenda por hora desativada."
        )
        return toggled

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
        control_panel = CompactEditorControlPanel(
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
            schedule_store,
            save_stream_schedule_rule,
            delete_stream_schedule_rule,
            toggle_stream_schedule_rule,
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

    def refresh_window_idle(title: str, subtitle: str = "") -> bool:
        if not cfg.get("show_window", True):
            return False

        if control_panel is not None:
            control_panel.refresh()
            if control_panel.should_close:
                return True

        idle_frame = np.zeros((540, 960, 3), dtype=np.uint8)
        cv2.putText(
            idle_frame,
            title[:72],
            (36, 220),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2,
        )
        if subtitle:
            cv2.putText(
                idle_frame,
                subtitle[:92],
                (36, 270),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.68,
                (140, 220, 255),
                2,
            )
        cv2.putText(
            idle_frame,
            "Pressione Q para fechar",
            (36, 500),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (180, 180, 180),
            1,
        )
        if editor is not None:
            idle_h, idle_w = idle_frame.shape[:2]
            editor.set_display_size(idle_w, idle_h)
        cv2.imshow(WINDOW_NAME, idle_frame)
        key = poll_window_key(1)
        if key == -1:
            return False
        key &= 0xFF
        return key == ord("q")

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
            proposal = dict(stream_store.get_selected_profile())
            proposal.update(stream_url=next_pipeline_start.source_url or cfg.get("stream_url"),
                            camera_id=next_pipeline_start.camera_id or cfg.get("camera_id"),
                            count_direction=next_pipeline_start.direction or count_direction,
                            line=next_pipeline_start.count_line or line)
            allowed, reason = backend.ensure_camera_change_allowed(cfg.get("camera_id", ""), "iniciar pipeline")
            if not allowed or not backend.register_operational_configuration(proposal):
                logger.warning("Pipeline nao alterada: configuracao bloqueada pelo backend.")
                continue
            # Reuse the normal profile handshake; do not start a pipeline without its frozen configuration.
            queue_stream_profile(proposal, message="Pipeline validada; aguardando ativacao.")
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
            cfg["secondary_verification_enabled"] = normalize_secondary_verification_enabled(
                profile.get("secondary_verification_enabled", DEFAULT_SECONDARY_VERIFICATION_ENABLED)
            )
            cfg["secondary_verification_band_px"] = normalize_secondary_verification_band_px(
                profile.get("secondary_verification_band_px", DEFAULT_SECONDARY_VERIFICATION_BAND_PX)
            )
            roi = dict(profile["roi"])
            line = dict(profile["line"])
            count_direction = profile["count_direction"]
            secondary_verification_enabled = cfg["secondary_verification_enabled"]
            secondary_verification_band_px = cfg["secondary_verification_band_px"]
            try:
                current_pipeline_cfg = build_pipeline_config(cfg)
                pipeline_runtime.start(current_pipeline_cfg)
                requested_camera_id = str(profile.get("camera_id") or "").strip()
                requested_profile_id = str(profile.get("id") or "").strip()
                requested_processed_path = str(current_pipeline_cfg.get("processed_stream_path") or "").strip()
                requested_profile_label = format_stream_profile_label(profile)
                activation_started_at = time.time()
                activation_session_id = uuid.uuid4().hex
                pending_camera_activation = {
                    "phase": "waiting_stream",
                    "activationSessionId": activation_session_id,
                    "requestedCameraId": requested_camera_id,
                    "requestedStreamProfileId": requested_profile_id,
                    "requestedProcessedStreamPath": requested_processed_path,
                    "requestedProfileLabel": requested_profile_label,
                    "activationStartedAt": activation_started_at,
                    "autoSwitchRound": bool(profile.get("_activation_auto_switch_round")),
                    "requestNotified": False,
                    "readyNotified": False,
                }
                update_camera_activation_status(
                    phase="waiting_stream",
                    activationSessionId=activation_session_id,
                    activationRequestedAt=activation_started_at,
                    firstCaptureAt=None,
                    firstProcessedAt=None,
                    firstRenderableFrameAt=None,
                    firstPublishedAt=None,
                    requestedCameraId=requested_camera_id,
                    requestedStreamProfileId=requested_profile_id,
                    requestedProcessedStreamPath=requested_processed_path,
                    requestedProfileLabel=requested_profile_label,
                    readyCameraId="",
                    readyStreamProfileId="",
                    readyProcessedStreamPath="",
                    readyProfileLabel="",
                    readyForRounds=False,
                    frontendAckRequired=True,
                    frontendAckPhase="requested",
                    frontendAckNonce="",
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
                    request_notified = backend.notify_stream_profile_activated(
                        cfg.get("camera_id", ""),
                        profile.get("id", ""),
                        allow_settling=bool(profile.get("_activation_allow_settling")),
                        auto_switch_round=bool(profile.get("_activation_auto_switch_round")),
                        phase="requested",
                        activation_session_id=activation_session_id,
                        configuration=cfg,
                    )
                    if isinstance(pending_camera_activation, dict):
                        pending_camera_activation["requestNotified"] = request_notified
                publish_rotation_status(f"Perfil ativo: {format_stream_profile_label(profile)}")
            except Exception as exc:
                logger.warning("Falha ao aplicar perfil de stream: %s", exc)
                if editor is not None:
                    editor.message = f"Falha ao resolver/iniciar perfil: {exc}"

        poll_round_state_if_needed()

        if not pipeline_runtime.is_running():
            if refresh_window_idle(
                "Pipeline pausada",
                str(get_stream_schedule_status().get("lastMessage") or editor.message if editor is not None else ""),
            ):
                break
            time.sleep(0.05)
            continue

        last_raw_seq, frame, captured_at = pipeline_runtime.wait_for_raw_frame(last_raw_seq, timeout=0.5)
        if frame is None or captured_at is None:
            if frame_count == 0:
                logger.warning("Nenhum frame recebido ainda do stream...")
            if refresh_window_idle(
                "Aguardando frames da stream",
                str(editor.message if editor is not None else get_stream_schedule_status().get("lastMessage") or ""),
            ):
                break
            active_pipeline_cfg = pipeline_runtime.get_config() or current_pipeline_cfg
            active_source_url = str(active_pipeline_cfg.get("stream_url") or cfg.get("stream_url") or "").strip()
            if is_youtube_url(active_source_url) and time.time() >= youtube_retry_after:
                youtube_retry_after = time.time() + 30.0
                logger.info("Stream YouTube sem frames; solicitando nova resolucao da URL.")
                queue_pipeline_refresh()
            continue

        frame_count += 1
        youtube_retry_after = 0.0
        current_activation_status = get_camera_activation_status()
        current_activation_session_id = str(current_activation_status.get("activationSessionId") or "").strip()
        current_camera_id = str(cfg.get("camera_id") or "").strip()
        current_profile_id = str(cfg.get("selected_stream_profile_id") or "").strip()
        if current_activation_session_id:
            mark_camera_activation_observation(
                current_activation_session_id,
                camera_id=current_camera_id,
                stream_profile_id=current_profile_id,
                captured_at=captured_at,
            )

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

        now_ts = time.time()
        if now_ts - last_config_poll >= CONFIG_POLL_INTERVAL:
            last_config_poll = now_ts
            admin_cfg = backend.fetch_camera_config(cfg["camera_id"])
            if admin_cfg and (editor is None or (editor.mode == "idle" and not editor.dirty)):
                proposal = dict(stream_store.get_selected_profile())
                proposal.update(roi=admin_cfg.get("roi") or roi,
                                line=admin_cfg.get("countLine") or line,
                                count_direction=admin_cfg.get("countDirection") or count_direction)
                try:
                    queue_stream_profile(proposal, message="Configuracao remota validada; aguardando ativacao.")
                except ValueError as exc:
                    logger.warning("Configuracao remota nao aplicada: %s", exc)

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
                count_reason = ""

                if is_inside and inference_is_fresh:
                    last_seen[track_id] = frame_count

                    prev = last_positions.get(track_id)
                    primary_cross = should_count_track(
                        prev_position=prev,
                        curr_position=(cx, cy),
                        line=line,
                        direction=count_direction,
                        hits=track_hits.get(track_id, 0),
                        min_hits_to_count=min_hits_to_count,
                        already_counted=track_id in counted_ids,
                    )
                    fallback_state = fallback_states.setdefault(
                        track_id,
                        {
                            "enteredFallbackBand": False,
                            "bestDistanceToLine": None,
                            "fallbackDirectionSign": 0,
                            "fallbackEligibleFrames": 0,
                            "fallbackProgressPx": 0.0,
                            "bboxTouchedBand": False,
                            "countReason": "",
                        },
                    )
                    fallback_cross = False
                    if (
                        not primary_cross
                        and secondary_verification_enabled
                    ):
                        fallback_cross = should_count_track_fallback(
                            prev_position=prev,
                            curr_position=(cx, cy),
                            curr_bbox=(x1, y1, x2, y2),
                            line=line,
                            direction=count_direction,
                            hits=track_hits.get(track_id, 0),
                            min_hits_to_count=min_hits_to_count,
                            already_counted=track_id in counted_ids,
                            band_px=secondary_verification_band_px,
                            state=fallback_state,
                        )

                    if primary_cross or fallback_cross:
                        count_reason = "primary" if primary_cross else "fallback"
                        fallback_state["countReason"] = count_reason
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
                                "countMethod": count_reason,
                                "fallbackBandPx": secondary_verification_band_px if count_reason == "fallback" else None,
                                "countBefore": total - 1,
                                "countAfter": total,
                                "totalCount": total,
                            }
                        )

                        logger.info(
                            "Count: %d (%s #%d) via %s",
                            total,
                            vehicle_name,
                            track_id,
                            count_reason,
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
                        "countReason": count_reason or fallback_states.get(track_id, {}).get("countReason", ""),
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
                fallback_states.pop(tid, None)
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
            style="clean",
        )
        browser_stream = resize_frame_max_width(browser_stream, browser_stream_max_width)

        operator_stream = browser_stream
        if cfg.get("show_window", True):
            preview_interval = 1.0 / max(1.0, operator_preview_fps_limit)
            if last_operator_preview is None or (time.time() - last_operator_preview_at) >= preview_interval:
                operator_stream = annotate_frame(
                    frame,
                    roi,
                    line,
                    detections_list,
                    total,
                    style="clean",
                )
                operator_stream = resize_frame_max_width(operator_stream, operator_preview_max_width)
                if editor is not None:
                    display_h, display_w = operator_stream.shape[:2]
                    editor.set_display_size(display_w, display_h)
                    editor.draw_overlay(operator_stream)
                last_operator_preview = operator_stream
                last_operator_preview_at = time.time()
            else:
                operator_stream = last_operator_preview

        runtime_stats.record_processed_frame(total)
        pipeline_runtime.push_annotated_frame(browser_stream)
        runtime_stats.record_pipeline_ms((time.time() - captured_at) * 1000)
        renderable_at = time.time()
        if current_activation_session_id:
            mark_camera_activation_observation(
                current_activation_session_id,
                camera_id=current_camera_id,
                stream_profile_id=current_profile_id,
                processed_at=renderable_at,
                renderable_at=renderable_at,
            )
            published_at = float((runtime_stats.snapshot().get("lastPublishAt")) or 0.0)
            if published_at > 0:
                mark_camera_activation_observation(
                    current_activation_session_id,
                    camera_id=current_camera_id,
                    stream_profile_id=current_profile_id,
                    published_at=published_at,
                )

        if isinstance(pending_camera_activation, dict):
            activation_session_id = str(pending_camera_activation.get("activationSessionId") or "").strip()
            activation_requested_camera = str(pending_camera_activation.get("requestedCameraId") or "").strip()
            activation_requested_profile = str(pending_camera_activation.get("requestedStreamProfileId") or "").strip()
            activation_requested_path = str(pending_camera_activation.get("requestedProcessedStreamPath") or "").strip()
            activation_requested_label = str(pending_camera_activation.get("requestedProfileLabel") or activation_requested_camera).strip()
            activation_started_at = float(pending_camera_activation.get("activationStartedAt") or 0.0)
            runtime_snapshot = runtime_stats.snapshot()
            last_capture_at = float(runtime_snapshot.get("lastCaptureAt") or 0.0)
            last_frame_at = float(runtime_snapshot.get("lastFrameAt") or 0.0)
            last_publish_at = float(runtime_snapshot.get("lastPublishAt") or 0.0)
            stream_ready = (
                activation_requested_camera
                and activation_requested_camera == current_camera_id
                and activation_requested_profile == current_profile_id
                and bool(runtime_snapshot.get("streamConnected"))
                and bool(runtime_snapshot.get("publisherHealthy"))
                and last_capture_at >= activation_started_at
                and last_frame_at >= activation_started_at
                and last_publish_at >= activation_started_at
            )
            if stream_ready:
                activation_nonce = str(pending_camera_activation.get("frontendAckNonce") or "").strip()
                if not activation_nonce:
                    activation_nonce = uuid.uuid4().hex
                    pending_camera_activation["frontendAckNonce"] = activation_nonce
                if not bool(pending_camera_activation.get("readyNotified")):
                    ready_notified = backend.notify_stream_profile_activated(
                        activation_requested_camera,
                        activation_requested_profile,
                        allow_settling=True,
                        auto_switch_round=bool(pending_camera_activation.get("autoSwitchRound")),
                        phase="frontend_pending",
                        activation_nonce=activation_nonce,
                        activation_session_id=activation_session_id,
                        configuration=cfg,
                    )
                    pending_camera_activation["readyNotified"] = ready_notified
                    if not ready_notified:
                        continue
                remember_recent_runtime_camera_id(activation_requested_camera)
                update_camera_activation_status(
                    phase="ready",
                    activationSessionId=activation_session_id,
                    requestedCameraId=activation_requested_camera,
                    readyCameraId=activation_requested_camera,
                    requestedStreamProfileId=activation_requested_profile,
                    readyStreamProfileId=activation_requested_profile,
                    requestedProcessedStreamPath=activation_requested_path,
                    readyProcessedStreamPath=activation_requested_path,
                    requestedProfileLabel=activation_requested_label,
                    readyProfileLabel=activation_requested_label,
                    readyForRounds=False,
                    frontendAckRequired=True,
                    frontendAckPhase="frontend_pending",
                    frontendAckNonce=activation_nonce,
                )
                pending_camera_activation = None

        if cfg.get("show_window", True):
            if control_panel is not None:
                control_panel.refresh()
                if control_panel.should_close:
                    break

            if editor is not None and operator_stream is not None:
                display_h, display_w = operator_stream.shape[:2]
                editor.set_display_size(display_w, display_h)
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
    if not acquire_single_instance_lock():
        logger.error(
            "Outra instancia do vision-worker ja esta em execucao. Encerrando esta abertura para evitar conflito de portas e publisher."
        )
        sys.exit(1)

    restart_attempt = 0

    while True:
        try:
            if restart_attempt > 0:
                logger.warning(
                    "Reiniciando loop principal do worker apos falha inesperada (tentativa %d).",
                    restart_attempt,
                )
            main()
            break
        except KeyboardInterrupt:
            logger.info("Encerrando por Ctrl+C.")
            cleanup_runtime()
            break
        except Exception:
            restart_attempt += 1
            logger.exception(
                "Falha nao tratada no worker principal. O loop sera reiniciado em 2 segundos."
            )
            try:
                cleanup_runtime()
            except Exception:
                logger.exception("Falha ao limpar runtime apos excecao nao tratada.")
            time.sleep(2.0)
