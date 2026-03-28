import json
import logging
import os
import threading
import time
import atexit
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timezone

import cv2
from flask import Flask, Response, jsonify, request
from ultralytics import YOLO
from waitress import create_server

from backend_client import BackendClient

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
        self._last_frame_at = None
        self._fps_instant = 0.0
        self._fps_average = 0.0
        self._last_inference_ms = 0.0
        self._avg_inference_ms = 0.0
        self._last_jpeg_encode_ms = 0.0
        self._avg_jpeg_encode_ms = 0.0
        self._mjpeg_clients = 0
        self._stream_connected = False
        self._stream_failures = 0
        self._last_stream_error_at = None
        self._total_count = 0

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
                "mjpegClients": self._mjpeg_clients,
                "streamConnected": self._stream_connected,
                "streamFailures": self._stream_failures,
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

# ---------------------------------------------------------------------------
# Annotated MJPEG stream
# ---------------------------------------------------------------------------
class AnnotatedFrameStreamer:
    def __init__(self, jpeg_quality: int = 80, stats: RuntimeStats | None = None):
        self.jpeg_quality = jpeg_quality
        self.stats = stats
        self._lock = threading.Lock()
        self._latest_jpeg: bytes | None = None

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


def cleanup_runtime():
    global active_stream_ref, active_mjpeg_server_ref, active_control_panel_ref

    if active_stream_ref is not None:
        active_stream_ref.release()
        active_stream_ref = None

    if active_mjpeg_server_ref is not None:
        active_mjpeg_server_ref.stop()
        active_mjpeg_server_ref = None

    if active_control_panel_ref is not None:
        active_control_panel_ref.close()
        active_control_panel_ref = None

    cv2.destroyAllWindows()


atexit.register(cleanup_runtime)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_config(path: str = "config.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(path: str, cfg: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    dead_zone_px: int = 0,
) -> bool:
    inside_segment = min(x1, x2) <= cx <= max(x1, x2)
    if not inside_segment:
        return False

    upper_band = line_y - dead_zone_px
    lower_band = line_y + dead_zone_px

    if direction == "down":
        return prev_y < upper_band and curr_y >= lower_band

    if direction == "up":
        return prev_y > lower_band and curr_y <= upper_band

    if direction == "any":
        return (
            (prev_y < upper_band and curr_y >= lower_band)
            or (prev_y > lower_band and curr_y <= upper_band)
        )

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
    dead_zone_px: int = 0,
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
        dead_zone_px=dead_zone_px,
    )


def anchor_point(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int]:
    return (int((x1 + x2) / 2), int(y2))


def clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(val, hi))


def build_class_names(allowed_classes: dict) -> dict[int, str]:
    return {v: k for k, v in allowed_classes.items()}


def bbox_area(x1: int, y1: int, x2: int, y2: int) -> int:
    return max(0, x2 - x1) * max(0, y2 - y1)


def get_class_thresholds(cfg: dict, vehicle_name: str) -> dict:
    defaults = {
        "min_bbox_area": int(cfg.get("min_bbox_area", 100)),
        "min_hits_to_count": int(cfg.get("min_hits_to_count", 4)),
        "min_confidence": float(cfg.get("conf", 0.2)),
    }
    thresholds = cfg.get("class_thresholds", {}).get(vehicle_name, {})
    return {
        "min_bbox_area": int(thresholds.get("min_bbox_area", defaults["min_bbox_area"])),
        "min_hits_to_count": int(thresholds.get("min_hits_to_count", defaults["min_hits_to_count"])),
        "min_confidence": float(thresholds.get("min_confidence", defaults["min_confidence"])),
    }


def annotate_frame(
    frame,
    roi: dict,
    line: dict,
    detections_list: list[dict],
    total: int,
):
    annotated = frame.copy()

    cv2.rectangle(
        annotated,
        (roi["x"], roi["y"]),
        (roi["x"] + roi["w"], roi["y"] + roi["h"]),
        (255, 255, 0),
        2,
    )
    cv2.line(
        annotated,
        (line["x1"], line["y1"]),
        (line["x2"], line["y2"]),
        (0, 0, 255),
        3,
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
        cv2.putText(
            annotated,
            f"#{tid} {vtype}",
            (dx, dy - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
        )

        cx_d = det["center"]["x"]
        cy_d = det["center"]["y"]
        cv2.circle(annotated, (cx_d, cy_d), 4, (0, 0, 255), -1)

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
    def __init__(self, editor: ConfigEditor, on_save):
        self.editor = editor
        self.on_save = on_save
        self.should_close = False
        self._root = tk.Tk()
        self._root.title("Controles de Configuracao")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self.request_close)

        frame = ttk.Frame(self._root, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="Ajuste de ROI e Linha", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        ttk.Button(frame, text="Editar ROI", command=self.editor.begin_roi_mode).grid(
            row=1, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(frame, text="Editar Linha", command=self.editor.begin_line_mode).grid(
            row=1, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Salvar", command=self.save).grid(
            row=2, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(frame, text="Cancelar", command=self.cancel).grid(
            row=2, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(frame, text="Fechar", command=self.request_close).grid(
            row=3, column=0, columnspan=2, sticky="ew"
        )

        self._mode_var = tk.StringVar(value=f"Modo: {self.editor.mode}")
        self._message_var = tk.StringVar(value=self.editor.message)
        ttk.Label(frame, textvariable=self._mode_var).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Label(frame, textvariable=self._message_var, wraplength=260).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )

        ttk.Label(frame, text="Atalhos opcionais: R, L, S, C, Q").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )

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

    def __init__(self, url: str, stats: RuntimeStats | None = None):
        self.url = url
        self.stats = stats
        self.cap: cv2.VideoCapture | None = None
        self._fail_count = 0
        self._connect()

    def _connect(self):
        if self.cap is not None:
            self.cap.release()

        logger.info("Conectando ao stream: %s", self.url)
        self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        self._fail_count = 0
        if self.stats is not None:
            self.stats.set_stream_status(self.cap.isOpened(), self._fail_count)

        if not self.cap.isOpened():
            logger.warning("Falha ao abrir stream na conexão inicial.")

    def read(self):
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

    def release(self):
        if self.cap:
            self.cap.release()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
LIVE_SEND_INTERVAL = 0.2
CONFIG_POLL_INTERVAL = 10
WINDOW_NAME = "Traffic Counter"


def main():
    global backend_client_ref, mjpeg_token_ref, active_stream_ref, active_mjpeg_server_ref, active_control_panel_ref

    config_path = "config.json"
    cfg = load_config(config_path)

    os.makedirs(cfg["snapshot_dir"], exist_ok=True)

    model = YOLO(cfg["model"])
    backend = BackendClient(cfg["backend_url"], cfg["api_key"])
    backend_client_ref = backend
    mjpeg_token_ref = str(cfg.get("mjpeg_token", "")).strip()
    stream = StreamCapture(cfg["stream_url"], stats=runtime_stats)
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

    roi = cfg["roi"]
    line = cfg["line"]
    count_direction = cfg["count_direction"]
    max_track_history_age = int(cfg.get("max_track_history_age", 300))
    line_dead_zone_px = int(cfg.get("line_dead_zone_px", 0))
    imgsz = int(cfg.get("imgsz", 416))
    editor = None
    control_panel = None

    def save_editor_state():
        nonlocal roi, line

        if editor is None:
            return

        editor.save(cfg, config_path)
        roi = dict(editor.roi)
        line = dict(editor.line)

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

    if cfg.get("show_window", True):
        editor = ConfigEditor(roi, line)
        cv2.namedWindow(WINDOW_NAME)
        cv2.setMouseCallback(WINDOW_NAME, lambda event, x, y, flags, param: editor.handle_mouse(event, x, y, flags, param))
        control_panel = EditorControlPanel(editor, save_editor_state)
        active_control_panel_ref = control_panel

    logger.info(
        "Iniciando contagem... | tracker: %s | conf: %s | imgsz: %s | dead-zone: %spx",
        cfg["tracker"],
        cfg["conf"],
        imgsz,
        line_dead_zone_px,
    )

    fps_frame_count = 0
    fps_start_ts = time.time()

    while True:
        ret, frame = stream.read()
        if not ret:
            if frame_count == 0:
                logger.warning("Nenhum frame recebido ainda do stream...")
            continue

        frame_count += 1

        if frame_count == 1:
            h0, w0 = frame.shape[:2]
            logger.info("Resolução do stream: %dx%d", w0, h0)
            logger.info("ROI: %s | Linha: %s | Direção: %s", roi, line, count_direction)

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
                    count_direction = admin_cfg["countDirection"]

                logger.info(
                    "Config atualizada pelo admin: line=%s, direction=%s",
                    line,
                    count_direction,
                )
                if editor is not None:
                    editor.sync_external_values(roi, line)

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
                "FPS inst: %.1f | inferencia media: %.1f ms | JPEG medio: %.1f ms | MJPEG clientes: %d | live descartados: %d",
                snapshot["fpsInstant"],
                snapshot["avgInferenceMs"],
                snapshot["avgJpegEncodeMs"],
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

                vehicle_name = class_names.get(cls_id, str(cls_id))
                class_thresholds = get_class_thresholds(cfg, vehicle_name)

                if conf < class_thresholds["min_confidence"]:
                    continue

                if bbox_area(x1, y1, x2, y2) < class_thresholds["min_bbox_area"]:
                    continue

                cx, cy = anchor_point(x1, y1, x2, y2)

                track_hits[track_id] = track_hits.get(track_id, 0) + 1

                is_inside = inside_roi(cx, cy, roi)
                is_counted = track_id in counted_ids
                did_cross = False

                if is_inside:
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
                        min_hits_to_count=class_thresholds["min_hits_to_count"],
                        already_counted=track_id in counted_ids,
                        dead_zone_px=line_dead_zone_px,
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
                                    cv2.imwrite(path, crop)
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
                                "roundId": cfg["round_id"],
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

        now_ts = time.time()
        if now_ts - last_live_send >= LIVE_SEND_INTERVAL:
            last_live_send = now_ts
            backend.send_live_detections(
                {
                    "cameraId": cfg["camera_id"],
                    "roundId": cfg["round_id"],
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

        stream_annotated = annotate_frame(frame, roi, line, detections_list, total)
        if editor is not None:
            editor.draw_overlay(stream_annotated)
        runtime_stats.record_processed_frame(total)
        streamer.update(stream_annotated)

        if cfg.get("show_window", True):
            if control_panel is not None:
                control_panel.refresh()
                if control_panel.should_close:
                    break

            cv2.imshow(WINDOW_NAME, stream_annotated)
            key = cv2.waitKey(1) & 0xFF
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
