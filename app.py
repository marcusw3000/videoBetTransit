import json
import logging
import os
import queue
import threading
import time
import atexit
import tkinter as tk
from tkinter import ttk
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
        self._frames_processed = 0
        self._last_capture_at = None
        self._last_frame_at = None
        self._fps_instant = 0.0
        self._fps_average = 0.0
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

    def record_capture(self, captured_at: float):
        with self._lock:
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

    def snapshot(self, backend_health: dict | None = None) -> dict:
        with self._lock:
            return {
                "ok": self._stream_connected,
                "framesProcessed": self._frames_processed,
                "fpsInstant": round(self._fps_instant, 2),
                "fpsAverage": round(self._fps_average, 2),
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
                "lastStreamErrorAt": self._last_stream_error_at,
                "totalCount": self._total_count,
                "backend": backend_health or {},
            }


runtime_stats = RuntimeStats()
backend_client_ref: BackendClient | None = None
mjpeg_token_ref: str = ""
active_stream_ref = None
active_mjpeg_server_ref = None
active_control_panel_ref = None
active_snapshot_writer_ref = None

# ---------------------------------------------------------------------------
# Annotated MJPEG stream
# ---------------------------------------------------------------------------
class AnnotatedFrameStreamer:
    def __init__(self, jpeg_quality: int = 80, stats: RuntimeStats | None = None):
        self.jpeg_quality = jpeg_quality
        self.stats = stats
        self._lock = threading.Lock()
        self._latest_jpeg: bytes | None = None

    def set_jpeg_quality(self, jpeg_quality: int):
        self.jpeg_quality = max(30, min(95, int(jpeg_quality)))

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


streamer = AnnotatedFrameStreamer(jpeg_quality=80, stats=runtime_stats)

def is_mjpeg_request_authorized() -> bool:
    if not mjpeg_token_ref:
        return True

    header_token = request.headers.get("X-API-Key", "")
    query_token = request.args.get("token", "")
    return header_token == mjpeg_token_ref or query_token == mjpeg_token_ref


def create_mjpeg_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        backend_health = (
            backend_client_ref.get_health_snapshot() if backend_client_ref else {}
        )
        return jsonify(runtime_stats.snapshot(backend_health))

    @app.get("/video_feed")
    def video_feed():
        if not is_mjpeg_request_authorized():
            return jsonify({"message": "Invalid or missing MJPEG token."}), 401

        def generate():
            last_sent = None
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

                    last_sent = frame
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
    if direction in {"up", "down", "any"}:
        return direction
    return "any"


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


def make_stream_profile_id(existing_ids: set[str]) -> str:
    base = f"stream_{int(time.time() * 1000)}"
    candidate = base
    suffix = 1
    while candidate in existing_ids:
        suffix += 1
        candidate = f"{base}_{suffix}"
    return candidate


def build_stream_profile(
    source: dict | None,
    fallback_cfg: dict,
    *,
    index: int,
) -> dict:
    source = source if isinstance(source, dict) else {}
    stream_url = str(
        source.get("stream_url")
        or source.get("url")
        or fallback_cfg.get("stream_url", "")
    ).strip()
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
    profile["stream_url"] = str(profile.get("stream_url") or "").strip()
    if not profile["name"]:
        profile["name"] = guess_stream_profile_name(
            profile["stream_url"],
            profile["camera_id"],
        )

    cfg["selected_stream_profile_id"] = profile["id"]
    cfg["stream_url"] = profile["stream_url"]
    cfg["camera_id"] = profile["camera_id"]
    cfg["roi"] = dict(profile["roi"])
    cfg["line"] = dict(profile["line"])
    cfg["count_direction"] = profile["count_direction"]
    return profile


def normalize_config(cfg: dict | None) -> dict:
    cfg = dict(cfg or {})
    raw_profiles = cfg.get("stream_profiles")
    profiles = []

    if isinstance(raw_profiles, list):
        for index, raw_profile in enumerate(raw_profiles, start=1):
            profile = build_stream_profile(raw_profile, cfg, index=index)
            if profile["stream_url"]:
                profiles.append(profile)

    if not profiles:
        profiles.append(build_stream_profile({}, cfg, index=1))

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
    selected_profile = next(
        (profile for profile in profiles if profile["id"] == selected_profile_id),
        None,
    )
    if selected_profile is None:
        current_stream_url = str(cfg.get("stream_url") or "").strip()
        selected_profile = next(
            (profile for profile in profiles if profile["stream_url"] == current_stream_url),
            None,
        )
    if selected_profile is None:
        selected_profile = profiles[0]

    sync_config_with_selected_profile(cfg, selected_profile)
    return cfg


def load_config(path: str = "config.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return normalize_config(json.load(f))


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

    def save_selected_profile(
        self,
        *,
        name: str | None = None,
        stream_url: str | None = None,
        roi: dict | None = None,
        line: dict | None = None,
        count_direction: str | None = None,
    ) -> dict:
        current = get_selected_stream_profile(self.cfg)
        target_url = str(stream_url or current.get("stream_url") or "").strip()
        if not target_url:
            raise ValueError("Informe uma URL de stream antes de salvar.")

        selected_stream_url = str(current.get("stream_url") or "").strip()
        if target_url != selected_stream_url:
            for profile in self.cfg.get("stream_profiles", []):
                if str(profile.get("stream_url") or "").strip() == target_url:
                    current = profile
                    break
            else:
                current = {
                    "id": make_stream_profile_id(
                        {str(profile.get("id") or "") for profile in self.cfg.get("stream_profiles", [])}
                    ),
                    "name": "",
                    "stream_url": target_url,
                    "camera_id": str(self.cfg.get("camera_id") or "").strip(),
                    "roi": dict(self.cfg.get("roi") or DEFAULT_ROI),
                    "line": dict(self.cfg.get("line") or DEFAULT_LINE),
                    "count_direction": self.cfg.get("count_direction", "any"),
                }
                self.cfg.setdefault("stream_profiles", []).append(current)

        if name is not None:
            current["name"] = str(name).strip()
        current["stream_url"] = target_url
        if roi is not None:
            current["roi"] = normalize_roi_config(roi, current.get("roi"))
        if line is not None:
            current["line"] = normalize_line_config(line, current.get("line"))
        if count_direction is not None:
            current["count_direction"] = normalize_count_direction(count_direction)

        return dict(sync_config_with_selected_profile(self.cfg, current))

    def apply_stream_url(self, stream_url: str, *, name: str | None = None) -> tuple[dict, bool]:
        target_url = str(stream_url or "").strip()
        if not target_url:
            raise ValueError("Informe uma URL de stream.")

        for profile in self.cfg.get("stream_profiles", []):
            if str(profile.get("stream_url") or "").strip() == target_url:
                if name is not None and str(name).strip():
                    profile["name"] = str(name).strip()
                return dict(sync_config_with_selected_profile(self.cfg, profile)), False

        profile = {
            "id": make_stream_profile_id(
                {str(existing.get("id") or "") for existing in self.cfg.get("stream_profiles", [])}
            ),
            "name": str(name or "").strip()
            or guess_stream_profile_name(
                target_url,
                self.cfg.get("camera_id", ""),
                index=len(self.cfg.get("stream_profiles", [])) + 1,
            ),
            "stream_url": target_url,
            "camera_id": str(self.cfg.get("camera_id") or "").strip(),
            "roi": normalize_roi_config(self.cfg.get("roi")),
            "line": normalize_line_config(self.cfg.get("line")),
            "count_direction": normalize_count_direction(self.cfg.get("count_direction", "any")),
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

    backend_round_id = str(backend_round.get("id", "")).strip()
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

    if direction == "down":
        return prev_y < line_y <= curr_y

    if direction == "up":
        return prev_y > line_y >= curr_y

    if direction == "any":
        return (prev_y < line_y <= curr_y) or (prev_y > line_y >= curr_y)

    return False


def should_count_track(
    prev_y: int | None,
    curr_y: int,
    cx: int,
    line: dict,
    direction: str,
    hits: int,
    min_hits_to_count: int,
    already_counted: bool,
) -> bool:
    if prev_y is None or already_counted or hits < min_hits_to_count:
        return False

    return crossed_horizontal_segment(
        prev_y=prev_y,
        curr_y=curr_y,
        line_y=line["y1"],
        cx=cx,
        x1=line["x1"],
        x2=line["x2"],
        direction=direction,
    )


def anchor_point(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int]:
    return (int((x1 + x2) / 2), int(y2))


def clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(val, hi))


def build_class_names(allowed_classes: dict) -> dict[int, str]:
    return {v: k for k, v in allowed_classes.items()}


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
    ):
        self.editor = editor
        self.stream_store = stream_store
        self.on_save = on_save
        self.on_reset_stream = on_reset_stream
        self.on_select_stream = on_select_stream
        self.on_open_stream = on_open_stream
        self.on_save_stream_profile = on_save_stream_profile
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
        self._stream_url_var = tk.StringVar()
        self._stream_selector = ttk.Combobox(frame, state="readonly", width=48)
        self._stream_selector.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        self._stream_selector.bind("<<ComboboxSelected>>", self._handle_profile_preview)
        ttk.Button(frame, text="Carregar", command=self.load_selected_stream).grid(
            row=1, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Label(frame, text="Nome da stream").grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Entry(frame, textvariable=self._stream_name_var).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        ttk.Label(frame, text="URL da stream").grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Entry(frame, textvariable=self._stream_url_var).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Abrir URL", command=self.open_stream_url).grid(
            row=6, column=0, sticky="ew", padx=(0, 6), pady=(0, 10)
        )
        ttk.Button(frame, text="Salvar na Esteira", command=self.save_stream_profile).grid(
            row=6, column=1, sticky="ew", pady=(0, 10)
        )

        ttk.Label(frame, text="Ajuste de ROI e Linha", font=("Segoe UI", 11, "bold")).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        ttk.Button(frame, text="Editar ROI", command=self.editor.begin_roi_mode).grid(
            row=8, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(frame, text="Editar Linha", command=self.editor.begin_line_mode).grid(
            row=8, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Salvar", command=self.save).grid(
            row=9, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(frame, text="Cancelar", command=self.cancel).grid(
            row=9, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Resetar Stream", command=self.reset_stream).grid(
            row=10, column=0, columnspan=2, sticky="ew"
        )
        ttk.Button(frame, text="Fechar", command=self.request_close).grid(
            row=11, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )

        self._mode_var = tk.StringVar(value=f"Modo: {self.editor.mode}")
        self._message_var = tk.StringVar(value=self.editor.message)
        ttk.Label(frame, textvariable=self._mode_var).grid(
            row=12, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Label(frame, textvariable=self._message_var, wraplength=360).grid(
            row=13, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )

        ttk.Label(frame, text="Atalhos opcionais: R, L, S, C, T, Q").grid(
            row=14, column=0, columnspan=2, sticky="w", pady=(10, 0)
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
        self.on_save()

    def cancel(self):
        self.editor.cancel()

    def reset_stream(self):
        self.on_reset_stream()

    def load_selected_stream(self):
        index = self._stream_selector.current()
        if index < 0 or index >= len(self._stream_profile_ids):
            self.editor.message = "Selecione uma stream salva na esteira."
            return

        try:
            profile = self.on_select_stream(self._stream_profile_ids[index])
        except ValueError as exc:
            self.editor.message = str(exc)
            return

        self.set_active_stream_profile(profile)

    def open_stream_url(self):
        try:
            profile = self.on_open_stream(
                self._stream_url_var.get(),
                self._stream_name_var.get(),
            )
        except ValueError as exc:
            self.editor.message = str(exc)
            return

        self.set_active_stream_profile(profile)

    def save_stream_profile(self):
        try:
            profile = self.on_save_stream_profile(
                self._stream_name_var.get(),
                self._stream_url_var.get(),
            )
        except ValueError as exc:
            self.editor.message = str(exc)
            return

        self.set_active_stream_profile(profile)

    def set_active_stream_profile(self, profile: dict):
        self._refresh_stream_profiles(selected_profile_id=profile.get("id"))
        self._stream_name_var.set(str(profile.get("name") or ""))
        self._stream_url_var.set(str(profile.get("stream_url") or ""))

    def _refresh_stream_profiles(self, selected_profile_id: str | None = None):
        profiles = self.stream_store.list_profiles()
        self._stream_profile_ids = [str(profile.get("id") or "") for profile in profiles]
        self._stream_selector["values"] = [format_stream_profile_label(profile) for profile in profiles]

        target_id = selected_profile_id or str(
            self.stream_store.get_selected_profile().get("id") or ""
        )
        if target_id in self._stream_profile_ids:
            self._stream_selector.current(self._stream_profile_ids.index(target_id))
        elif self._stream_profile_ids:
            self._stream_selector.current(0)

    def _handle_profile_preview(self, _event=None):
        index = self._stream_selector.current()
        if index < 0 or index >= len(self._stream_profile_ids):
            return

        profile_id = self._stream_profile_ids[index]
        for profile in self.stream_store.list_profiles():
            if str(profile.get("id") or "") == profile_id:
                self._stream_name_var.set(str(profile.get("name") or ""))
                self._stream_url_var.set(str(profile.get("stream_url") or ""))
                break

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
        self._frame_interval_s = 0.0
        self._next_frame_due = 0.0
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

        self._frame_interval_s = 1.0 / self._effective_fps
        self._next_frame_due = time.perf_counter()
        logger.info(
            "Pacing do stream: fps configurado=%.2f | fps detectado=%.2f | fps efetivo=%.2f",
            self.target_fps,
            reported_fps,
            self._effective_fps,
        )

        if not self.cap.isOpened():
            logger.warning("Falha ao abrir stream na conexão inicial.")

    def read(self):
        if self._frame_interval_s > 0:
            now_ts = time.perf_counter()
            if self._next_frame_due > now_ts:
                time.sleep(self._next_frame_due - now_ts)
                now_ts = time.perf_counter()
            self._next_frame_due = max(self._next_frame_due + self._frame_interval_s, now_ts)

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

    def reset(self):
        logger.info("Reset manual do stream solicitado.")
        self._connect()

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
    streamer.set_jpeg_quality(int(cfg.get("mjpeg_jpeg_quality", 70)))

    os.makedirs(cfg["snapshot_dir"], exist_ok=True)

    model = YOLO(cfg["model"])
    backend = BackendClient(cfg["backend_url"], cfg["api_key"])
    backend_client_ref = backend
    mjpeg_token_ref = str(cfg.get("mjpeg_token", "")).strip()
    snapshot_writer = AsyncSnapshotWriter(
        queue_size=int(cfg.get("snapshot_queue_size", 32)),
        jpeg_quality=int(cfg.get("snapshot_jpeg_quality", 85)),
    )
    active_snapshot_writer_ref = snapshot_writer
    stream = StreamCapture(
        cfg["stream_url"],
        stats=runtime_stats,
        ffmpeg_options=cfg.get("ffmpeg_capture_options"),
        buffer_size=int(cfg.get("stream_buffer_size", 1)),
        open_timeout_ms=int(cfg.get("stream_open_timeout_ms", 5000)),
        read_timeout_ms=int(cfg.get("stream_read_timeout_ms", 5000)),
        target_fps=float(cfg.get("stream_target_fps", 15)),
    )
    active_stream_ref = stream
    mjpeg_server = run_mjpeg_server(
        host=cfg.get("mjpeg_host", "0.0.0.0"),
        port=int(cfg.get("mjpeg_port", 8090)),
    )
    active_mjpeg_server_ref = mjpeg_server

    class_names = build_class_names(cfg["allowed_classes"])

    last_positions: dict[int, tuple[int, int]] = {}
    last_seen: dict[int, int] = {}
    track_hits: dict[int, int] = {}
    counted_ids: set[int] = set()

    total = 0
    frame_count = 0
    last_live_send = 0.0
    last_config_poll = 0.0
    last_round_sync = 0.0
    last_stream_resync = time.time()
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
    auto_resync_interval_seconds = float(cfg.get("stream_auto_resync_interval_seconds", 0))
    editor = None
    control_panel = None
    reset_stream_requested = False
    pending_stream_profile = None
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

        saved_backend = backend.save_camera_config(
            camera_id=cfg["camera_id"],
            roi=roi,
            line={
                "x1": line["x1"],
                "y1": line["y1"],
                "x2": line["x2"],
                "y2": line["y2"],
            },
            count_direction=count_direction,
        )
        if saved_backend:
            editor.message = f"Saved locally and synced to backend ({cfg['camera_id']})"
        else:
            editor.message = "Saved locally, but backend sync failed"

    def request_stream_reset():
        nonlocal reset_stream_requested

        reset_stream_requested = True
        if editor is not None:
            editor.message = "Manual stream reset requested"

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

    def select_stream_profile(profile_id: str) -> dict:
        profile = stream_store.select_profile(profile_id)
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        queue_stream_profile(
            profile,
            message=f"Stream pronta para trocar: {format_stream_profile_label(profile)}",
        )
        return profile

    def open_stream_url(stream_url: str, stream_name: str) -> dict:
        profile, created = stream_store.apply_stream_url(stream_url, name=stream_name)
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        action = "adicionada" if created else "reaberta"
        queue_stream_profile(
            profile,
            message=f"Stream {action} na esteira: {format_stream_profile_label(profile)}",
        )
        return profile

    def save_stream_profile(stream_name: str, stream_url: str) -> dict:
        target_url = stream_url or cfg.get("stream_url", "")
        profile = stream_store.save_selected_profile(
            name=stream_name,
            stream_url=target_url,
            roi=editor.roi if editor is not None else roi,
            line=editor.line if editor is not None else line,
            count_direction=count_direction,
        )
        save_config(config_path, cfg)
        sync_stream_profiles_to_supabase(cfg, supabase_sync)
        saved_backend = backend.save_camera_config(
            camera_id=cfg["camera_id"],
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

    backend_round = backend.fetch_current_round()
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
        if pending_stream_profile is not None:
            profile = pending_stream_profile
            pending_stream_profile = None
            reset_tracking_state()
            backend_round = backend.fetch_current_round()
            if backend_round:
                backend_round_id = str(backend_round.get("id", "")).strip()
                if backend_round_id:
                    current_round_id = backend_round_id
                total = int(backend_round.get("currentCount", 0) or 0)

            cfg["stream_url"] = profile["stream_url"]
            cfg["camera_id"] = profile["camera_id"]
            cfg["roi"] = dict(profile["roi"])
            cfg["line"] = dict(profile["line"])
            cfg["count_direction"] = profile["count_direction"]
            roi = dict(profile["roi"])
            line = dict(profile["line"])
            count_direction = profile["count_direction"]
            stream.url = cfg["stream_url"]
            stream.reset()
            last_stream_resync = time.time()
            last_track_results = None
            last_visual_detections = []
            last_operator_preview = None
            last_operator_preview_at = 0.0
            frame_count = 0
            fps_frame_count = 0
            fps_start_ts = time.time()
            logger.info(
                "Perfil de stream aplicado: %s | url=%s",
                format_stream_profile_label(profile),
                cfg["stream_url"],
            )

        if reset_stream_requested:
            stream.reset()
            reset_stream_requested = False
            last_stream_resync = time.time()
            if editor is not None:
                editor.message = "Stream resetado manualmente"

        ret, frame = stream.read()
        if not ret:
            if frame_count == 0:
                logger.warning("Nenhum frame recebido ainda do stream...")
            continue
        captured_at = time.time()
        runtime_stats.record_capture(captured_at)

        frame_count += 1

        if frame_count == 1:
            h0, w0 = frame.shape[:2]
            logger.info("Resolução do stream: %dx%d", w0, h0)
            logger.info("ROI: %s | Linha: %s | Direção: %s", roi, line, count_direction)

        now_ts = time.time()
        if now_ts - last_round_sync >= ROUND_SYNC_INTERVAL:
            last_round_sync = now_ts
            backend_round = backend.fetch_current_round()
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

        if (
            auto_resync_interval_seconds > 0
            and (now_ts - last_stream_resync) >= auto_resync_interval_seconds
        ):
            logger.info(
                "Auto-resync do stream apos %.1fs para manter a live mais proxima do ao vivo.",
                auto_resync_interval_seconds,
            )
            request_stream_reset()
            last_stream_resync = now_ts

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
                    count_direction = admin_cfg["countDirection"]

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
        line_y = line["y1"]
        detections_list = []
        boxes = None

        if editor is not None:
            editor.set_frame_size(w, h)
            roi = dict(editor.roi)
            line = dict(editor.line)
            line_y = line["y1"]

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
                cx, cy = anchor_point(x1, y1, x2, y2)

                if inference_is_fresh:
                    track_hits[track_id] = track_hits.get(track_id, 0) + 1

                is_inside = inside_roi(cx, cy, roi)
                is_counted = track_id in counted_ids
                did_cross = False

                if is_inside and inference_is_fresh:
                    last_seen[track_id] = frame_count

                    prev = last_positions.get(track_id)
                    prev_y = prev[1] if prev else None
                    if should_count_track(
                        prev_y=prev_y,
                        curr_y=cy,
                        cx=cx,
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
                                "trackId": str(track_id),
                                "vehicleType": vehicle_name,
                                "crossedAt": now(),
                                "snapshotUrl": path,
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
        streamer.update(browser_stream)
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
