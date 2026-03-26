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

    return False


def anchor_point(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int]:
    return (int((x1 + x2) / 2), int(y2))


def clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(val, hi))


def build_class_names(allowed_classes: dict) -> dict[int, str]:
    return {v: k for k, v in allowed_classes.items()}


def bbox_area(x1: int, y1: int, x2: int, y2: int) -> int:
    return max(0, x2 - x1) * max(0, y2 - y1)


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
        self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        self._fail_count = 0

        if not self.cap.isOpened():
            logger.warning("Falha ao abrir stream na conexão inicial.")

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
LIVE_SEND_INTERVAL = 0.2
CONFIG_POLL_INTERVAL = 10


def main():
    cfg = load_config()

    os.makedirs(cfg["snapshot_dir"], exist_ok=True)

    model = YOLO(cfg["model"])
    backend = BackendClient(cfg["backend_url"], cfg["api_key"])
    stream = StreamCapture(cfg["stream_url"])

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

    logger.info("Iniciando contagem...")

    while True:
        ret, frame = stream.read()
        if not ret:
            if frame_count == 0:
                logger.warning("Nenhum frame recebido ainda do stream...")
            time.sleep(0.1)
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

        results = model.track(
            frame,
            persist=True,
            tracker=cfg["tracker"],
            conf=cfg["conf"],
            classes=list(cfg["allowed_classes"].values()),
            verbose=False,
        )

        h, w = frame.shape[:2]
        line_y = line["y1"]
        detections_list = []

        boxes = results[0].boxes

        # Debug logging a cada 30 frames
        if frame_count % 30 == 0:
            n_boxes = len(boxes) if boxes is not None else 0
            has_ids = boxes.id is not None if boxes is not None else False
            logger.info(
                "[DEBUG] frame=%d | boxes=%d | has_track_ids=%s | total=%d",
                frame_count, n_boxes, has_ids, total,
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
                    if (
                        prev
                        and track_id not in counted_ids
                        and track_hits.get(track_id, 0) >= min_hits_to_count
                    ):
                        _, prev_y = prev

                        if crossed_horizontal_segment(
                            prev_y=prev_y,
                            curr_y=cy,
                            line_y=line_y,
                            cx=cx,
                            x1=line["x1"],
                            x2=line["x2"],
                            direction=count_direction,
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
                                    cv2.imwrite(path, crop)
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

        if cfg.get("show_window", True):
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
                (0, 255, 255),
                3,
            )

            cv2.putText(
                annotated,
                f"TOTAL: {total}",
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2,
                (0, 255, 0),
                3,
            )

            cv2.imshow("Traffic Counter", annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    stream.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
