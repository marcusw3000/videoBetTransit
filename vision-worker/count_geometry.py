from __future__ import annotations
import math
import numpy as np
from worker_config import normalize_count_direction, normalize_secondary_verification_band_px
from worker_defaults import SECONDARY_VERIFICATION_MIN_BAND_FRAMES, SECONDARY_VERIFICATION_MIN_PROGRESS_PX


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



def line_geometry_metrics(point: tuple[int, int], line: dict) -> dict:
    px, py = point
    x1 = float(line["x1"])
    y1 = float(line["y1"])
    x2 = float(line["x2"])
    y2 = float(line["y2"])
    dx = x2 - x1
    dy = y2 - y1
    length = float(np.hypot(dx, dy))
    if length < 1.0:
        return {
            "length": 0.0,
            "projection": 0.0,
            "signed_distance": 0.0,
        }

    tx = dx / length
    ty = dy / length
    nx = -dy / length
    ny = dx / length
    rel_x = float(px) - x1
    rel_y = float(py) - y1
    return {
        "length": length,
        "projection": rel_x * tx + rel_y * ty,
        "signed_distance": rel_x * nx + rel_y * ny,
    }



def point_inside_line_band(point: tuple[int, int], line: dict, band_px: int) -> bool:
    metrics = line_geometry_metrics(point, line)
    length = float(metrics["length"])
    if length < 1.0:
        return False
    band = float(normalize_secondary_verification_band_px(band_px))
    projection = float(metrics["projection"])
    return (
        -band <= projection <= length + band
        and abs(float(metrics["signed_distance"])) <= band
    )



def distance_point_to_segment(
    point: tuple[float, float],
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
) -> float:
    px, py = point
    x1, y1 = segment_start
    x2, y2 = segment_end
    dx = x2 - x1
    dy = y2 - y1
    segment_length_sq = (dx * dx) + (dy * dy)
    if segment_length_sq <= 1e-9:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / segment_length_sq
    t = max(0.0, min(1.0, t))
    closest_x = x1 + (t * dx)
    closest_y = y1 + (t * dy)
    return math.hypot(px - closest_x, py - closest_y)



def segment_orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return ((b[0] - a[0]) * (c[1] - a[1])) - ((b[1] - a[1]) * (c[0] - a[0]))



def point_on_segment(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> bool:
    return (
        min(start[0], end[0]) - 1e-9 <= point[0] <= max(start[0], end[0]) + 1e-9
        and min(start[1], end[1]) - 1e-9 <= point[1] <= max(start[1], end[1]) + 1e-9
    )



def segments_intersect(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> bool:
    o1 = segment_orientation(a1, a2, b1)
    o2 = segment_orientation(a1, a2, b2)
    o3 = segment_orientation(b1, b2, a1)
    o4 = segment_orientation(b1, b2, a2)

    if (o1 > 0 and o2 < 0 or o1 < 0 and o2 > 0) and (o3 > 0 and o4 < 0 or o3 < 0 and o4 > 0):
        return True
    if abs(o1) <= 1e-9 and point_on_segment(b1, a1, a2):
        return True
    if abs(o2) <= 1e-9 and point_on_segment(b2, a1, a2):
        return True
    if abs(o3) <= 1e-9 and point_on_segment(a1, b1, b2):
        return True
    if abs(o4) <= 1e-9 and point_on_segment(a2, b1, b2):
        return True
    return False



def segment_distance(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> float:
    if segments_intersect(a1, a2, b1, b2):
        return 0.0
    return min(
        distance_point_to_segment(a1, b1, b2),
        distance_point_to_segment(a2, b1, b2),
        distance_point_to_segment(b1, a1, a2),
        distance_point_to_segment(b2, a1, a2),
    )



def bbox_distance_to_line_segment(bbox: tuple[int, int, int, int], line: dict) -> float:
    x1, y1, x2, y2 = bbox
    left = float(min(x1, x2))
    right = float(max(x1, x2))
    top = float(min(y1, y2))
    bottom = float(max(y1, y2))
    line_start = (float(line["x1"]), float(line["y1"]))
    line_end = (float(line["x2"]), float(line["y2"]))

    corners = [
        (left, top),
        (right, top),
        (right, bottom),
        (left, bottom),
    ]
    if any(point_inside_line_band((int(px), int(py)), line, 0) for px, py in corners):
        return 0.0

    rect_edges = [
        ((left, top), (right, top)),
        ((right, top), (right, bottom)),
        ((right, bottom), (left, bottom)),
        ((left, bottom), (left, top)),
    ]
    return min(segment_distance(line_start, line_end, edge_start, edge_end) for edge_start, edge_end in rect_edges)



def bbox_touches_line_band(bbox: tuple[int, int, int, int] | None, line: dict, band_px: int) -> bool:
    if bbox is None:
        return False
    band = float(normalize_secondary_verification_band_px(band_px))
    return bbox_distance_to_line_segment(bbox, line) <= band



def movement_delta_for_direction(
    prev_position: tuple[int, int],
    curr_position: tuple[int, int],
    line: dict,
) -> int:
    prev_x, prev_y = prev_position
    curr_x, curr_y = curr_position
    if count_line_is_horizontal(line):
        return int(curr_y - prev_y)
    return int(curr_x - prev_x)



def movement_matches_direction(delta: int, direction: str) -> bool:
    normalized = normalize_count_direction(direction)
    if normalized == "down":
        return delta > 0
    if normalized == "up":
        return delta < 0
    if normalized == "right":
        return delta > 0
    if normalized == "left":
        return delta < 0
    return delta != 0



def should_count_track_fallback(
    prev_position: tuple[int, int] | None,
    curr_position: tuple[int, int],
    curr_bbox: tuple[int, int, int, int] | None,
    line: dict,
    direction: str,
    hits: int,
    min_hits_to_count: int,
    already_counted: bool,
    band_px: int,
    state: dict | None,
) -> bool:
    if prev_position is None or already_counted or hits < min_hits_to_count:
        return False

    state = state if isinstance(state, dict) else {}
    band = normalize_secondary_verification_band_px(band_px)
    prev_in_band = point_inside_line_band(prev_position, line, band)
    curr_in_band = point_inside_line_band(curr_position, line, band)
    curr_bbox_touches_band = bbox_touches_line_band(curr_bbox, line, band)
    delta = movement_delta_for_direction(prev_position, curr_position, line)
    progress_px = abs(delta)

    if not curr_in_band and not curr_bbox_touches_band:
        return False
    if progress_px < SECONDARY_VERIFICATION_MIN_PROGRESS_PX:
        return False
    if not movement_matches_direction(delta, direction):
        return False

    best_distance = state.get("bestDistanceToLine")
    current_distance = (
        bbox_distance_to_line_segment(curr_bbox, line)
        if curr_bbox is not None
        else abs(float(line_geometry_metrics(curr_position, line)["signed_distance"]))
    )
    if best_distance is None:
        best_distance = current_distance
    else:
        best_distance = min(float(best_distance), current_distance)

    prior_direction_sign = int(state.get("fallbackDirectionSign") or 0)
    current_direction_sign = 1 if delta > 0 else -1
    if prior_direction_sign and current_direction_sign != prior_direction_sign:
        return False

    if not bool(state.get("enteredFallbackBand")):
        eligible_frames = 1 if prev_in_band or curr_in_band or curr_bbox_touches_band else 0
        state["fallbackProgressPx"] = float(progress_px)
    else:
        eligible_frames = int(state.get("fallbackEligibleFrames") or 0) + 1
        state["fallbackProgressPx"] = float(state.get("fallbackProgressPx") or 0.0) + float(progress_px)

    state["enteredFallbackBand"] = True
    state["bestDistanceToLine"] = best_distance
    state["fallbackDirectionSign"] = current_direction_sign
    state["fallbackEligibleFrames"] = eligible_frames
    state["bboxTouchedBand"] = bool(state.get("bboxTouchedBand")) or curr_bbox_touches_band

    return (
        eligible_frames >= SECONDARY_VERIFICATION_MIN_BAND_FRAMES
        and float(state.get("fallbackProgressPx") or 0.0) >= (SECONDARY_VERIFICATION_MIN_PROGRESS_PX * 2)
        and best_distance <= (band if state.get("bboxTouchedBand") else (band * 0.55))
    )



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
        "any": "Qualquer direcao",
        "up": "Baixo para cima",
        "down": "Cima para baixo",
        "left": "Direita para esquerda",
        "right": "Esquerda para direita",
    }.get(normalize_count_direction(direction), "Qualquer direcao")



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

