import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

import cv2
from flask import Flask, Response, jsonify, request
from ultralytics import YOLO

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
mjpeg_app = Flask(__name__)


@mjpeg_app.get("/health")
def health():
    backend_health = backend_client_ref.get_health_snapshot() if backend_client_ref else {}
    return jsonify(runtime_stats.snapshot(backend_health))


def is_mjpeg_request_authorized() -> bool:
    if not mjpeg_token_ref:
        return True

    header_token = request.headers.get("X-API-Key", "")
    query_token = request.args.get("token", "")
    return header_token == mjpeg_token_ref or query_token == mjpeg_token_ref


@mjpeg_app.get("/video_feed")
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


def run_mjpeg_server(host: str = "0.0.0.0", port: int = 8090):
    thread = threading.Thread(
        target=lambda: mjpeg_app.run(
            host=host,
            port=port,
            threaded=True,
            debug=False,
            use_reloader=False,
        ),
        daemon=True,
    )
    thread.start()
    logger.info("MJPEG server iniciado em http://%s:%s/video_feed", host, port)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_config(path: str = "config.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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


def main():
    global backend_client_ref, mjpeg_token_ref

    cfg = load_config()

    os.makedirs(cfg["snapshot_dir"], exist_ok=True)

    model = YOLO(cfg["model"])
    backend = BackendClient(cfg["backend_url"], cfg["api_key"])
    backend_client_ref = backend
    mjpeg_token_ref = str(cfg.get("mjpeg_token", "")).strip()
    stream = StreamCapture(cfg["stream_url"], stats=runtime_stats)
    run_mjpeg_server(
        host=cfg.get("mjpeg_host", "0.0.0.0"),
        port=int(cfg.get("mjpeg_port", 8090)),
    )

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
    min_hits_to_count = int(cfg.get("min_hits_to_count", 4))
    max_track_history_age = int(cfg.get("max_track_history_age", 300))
    min_bbox_area = int(cfg.get("min_bbox_area", 100))

    logger.info("Iniciando contagem... | tracker: %s | conf: %s", cfg["tracker"], cfg["conf"])

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
            if admin_cfg:
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

        inference_start = time.perf_counter()
        try:
            results = model.track(
                frame,
                persist=True,
                tracker=cfg["tracker"],
                conf=cfg["conf"],
                classes=list(cfg["allowed_classes"].values()),
                imgsz=416,
                verbose=False,
            )
        except Exception as exc:
            logger.warning("Falha na inferência YOLO (frame %d ignorado): %s", frame_count, exc)
            continue

        runtime_stats.record_inference_ms((time.perf_counter() - inference_start) * 1000)

        h, w = frame.shape[:2]
        line_y = line["y1"]
        detections_list = []

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

                if bbox_area(x1, y1, x2, y2) < min_bbox_area:
                    continue

                vehicle_name = class_names.get(cls_id, str(cls_id))
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
        runtime_stats.record_processed_frame(total)
        streamer.update(stream_annotated)

        if cfg.get("show_window", True):
            cv2.imshow("Traffic Counter", stream_annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            continue

    stream.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Encerrando por Ctrl+C.")
