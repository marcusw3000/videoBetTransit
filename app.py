import json
import logging
import os
import time
from datetime import datetime, timezone

import cv2
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


def crossed_line(prev_y: int, curr_y: int, line_y: int, direction: str) -> bool:
    if direction == "down":
        return prev_y < line_y <= curr_y
    if direction == "up":
        return prev_y > line_y >= curr_y
    if direction == "any":
        return (prev_y < line_y <= curr_y) or (prev_y > line_y >= curr_y)
    return False


def center(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int]:
    return (int((x1 + x2) / 2), int((y1 + y2) / 2))


def clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(val, hi))


def build_class_names(allowed_classes: dict) -> dict[int, str]:
    return {v: k for k, v in allowed_classes.items()}


# ---------------------------------------------------------------------------
# Stream com reconexão automática
# ---------------------------------------------------------------------------

class StreamCapture:
    MAX_FAILURES = 30

    def __init__(self, url: str):
        self.url = url
        self.cap: cv2.VideoCapture | None = None
        self._fail_count = 0
        self._connect()

    def _connect(self):
        if self.cap is not None:
            self.cap.release()
        logger.info("Conectando ao stream: %s", self.url)
        self.cap = cv2.VideoCapture(self.url)
        self._fail_count = 0

    def read(self):
        ret, frame = self.cap.read()
        if not ret:
            self._fail_count += 1
            if self._fail_count >= self.MAX_FAILURES:
                logger.warning("Stream perdido — reconectando...")
                self._connect()
            return False, None
        self._fail_count = 0
        return True, frame

    def release(self):
        if self.cap:
            self.cap.release()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

STALE_THRESHOLD = 300
LIVE_SEND_INTERVAL = 0.2  # enviar live detections a cada 200ms
CONFIG_POLL_INTERVAL = 10  # verificar config do admin a cada 10s

def main():
    cfg = load_config()

    os.makedirs(cfg["snapshot_dir"], exist_ok=True)

    model = YOLO(cfg["model"])
    backend = BackendClient(cfg["backend_url"], cfg["api_key"])

    stream = StreamCapture(cfg["stream_url"])

    class_names = build_class_names(cfg["allowed_classes"])

    last_positions: dict[int, tuple[int, int]] = {}
    last_seen: dict[int, int] = {}
    counted_ids: set[int] = set()
    total = 0
    frame_count = 0
    last_live_send = 0.0
    last_config_poll = 0.0

    # Valores dinâmicos (podem ser atualizados pelo admin)
    roi = cfg["roi"]
    line = cfg["line"]
    count_direction = cfg["count_direction"]

    logger.info("🚀 Iniciando contagem...")

    while True:
        ret, frame = stream.read()
        if not ret:
            time.sleep(0.1)
            continue

        frame_count += 1

        # Poll config do admin a cada 10s
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
                logger.info("📋 Config atualizada pelo admin: line=%s, direction=%s", line, count_direction)

        results = model.track(
            frame,
            persist=True,
            tracker=cfg["tracker"],
            conf=cfg["conf"],
            classes=list(cfg["allowed_classes"].values()),
            verbose=False,
        )

        line_y = line["y1"]
        h, w = frame.shape[:2]

        boxes = results[0].boxes

        # Lista de detecções para o overlay
        detections_list = []

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

                cx, cy = center(x1, y1, x2, y2)

                is_inside = inside_roi(cx, cy, roi)
                is_counted = track_id in counted_ids
                did_cross = False

                if is_inside:
                    last_seen[track_id] = frame_count
                    prev = last_positions.get(track_id)

                    if prev and track_id not in counted_ids:
                        _, prev_y = prev
                        if crossed_line(prev_y, cy, line_y, count_direction):
                            counted_ids.add(track_id)
                            total += 1
                            is_counted = True
                            did_cross = True

                            # Snapshot
                            if cfg.get("save_snapshots", True):
                                sy1 = clamp(y1, 0, h)
                                sy2 = clamp(y2, 0, h)
                                sx1 = clamp(x1, 0, w)
                                sx2 = clamp(x2, 0, w)
                                crop = frame[sy1:sy2, sx1:sx2]

                                if crop.size > 0:
                                    filename = f"{track_id}_{int(time.time())}.jpg"
                                    path = os.path.join(cfg["snapshot_dir"], filename)
                                    cv2.imwrite(path, crop)
                                else:
                                    path = ""
                            else:
                                path = ""

                            backend.send_count_event({
                                "cameraId": cfg["camera_id"],
                                "roundId": cfg["round_id"],
                                "trackId": str(track_id),
                                "vehicleType": vehicle_name,
                                "crossedAt": now(),
                                "snapshotUrl": path,
                                "totalCount": total,
                            })

                            logger.info("🚗 Count: %d  (%s #%d)", total, vehicle_name, track_id)

                    last_positions[track_id] = (cx, cy)

                # Adiciona à lista de detecções (TODAS, dentro ou fora da ROI)
                detections_list.append({
                    "trackId": str(track_id),
                    "vehicleType": vehicle_name,
                    "bbox": {"x": int(x1), "y": int(y1), "w": int(x2 - x1), "h": int(y2 - y1)},
                    "center": {"x": cx, "y": cy},
                    "confidence": round(conf, 2),
                    "insideRoi": is_inside,
                    "crossedLine": did_cross,
                    "counted": is_counted,
                })

        # Enviar live detections throttled (a cada ~200ms)
        now_ts = time.time()
        if now_ts - last_live_send >= LIVE_SEND_INTERVAL:
            last_live_send = now_ts
            backend.send_live_detections({
                "cameraId": cfg["camera_id"],
                "roundId": cfg["round_id"],
                "frameWidth": w,
                "frameHeight": h,
                "totalCount": total,
                "roi": roi,
                "countLine": {
                    "x1": line["x1"],
                    "y1": line["y1"],
                    "x2": line["x2"],
                    "y2": line["y2"],
                },
                "detections": detections_list,
            })

        # Limpeza periódica de IDs antigos
        if frame_count % STALE_THRESHOLD == 0:
            stale = [
                tid for tid, last in last_seen.items()
                if frame_count - last > STALE_THRESHOLD
            ]
            for tid in stale:
                last_positions.pop(tid, None)
                last_seen.pop(tid, None)
                counted_ids.discard(tid)

        # HUD (janela local — opcional)
        if cfg.get("show_window", True):
            annotated = frame.copy()
            cv2.rectangle(
                annotated,
                (roi["x"], roi["y"]),
                (roi["x"] + roi["w"], roi["y"] + roi["h"]),
                (255, 255, 0), 2,
            )
            cv2.line(
                annotated,
                (line["x1"], line["y1"]),
                (line["x2"], line["y2"]),
                (0, 255, 255), 3,
            )
            cv2.putText(
                annotated,
                f"TOTAL: {total}",
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2, (0, 255, 0), 3,
            )
            cv2.imshow("Traffic Counter", annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    stream.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
