from __future__ import annotations
import cv2
import numpy as np


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
    style: str = "classic",
):
    annotated = frame.copy()

    def blend_shape(draw_fn, alpha: float):
        overlay = annotated.copy()
        draw_fn(overlay)
        cv2.addWeighted(overlay, alpha, annotated, 1.0 - alpha, 0, annotated)

    def draw_clean_reference_band():
        x1 = int(line["x1"])
        y1 = int(line["y1"])
        x2 = int(line["x2"])
        y2 = int(line["y2"])
        dx = x2 - x1
        dy = y2 - y1
        length = float(np.hypot(dx, dy))
        if length < 1.0:
            cv2.line(annotated, (x1, y1), (x2, y2), (64, 224, 255), 3)
            return

        nx = -dy / length
        ny = dx / length
        band_half = max(12, min(24, int(length * 0.045)))
        glow_half = band_half + 8

        def build_band(half_width: int):
            return np.array(
                [
                    [int(round(x1 + nx * half_width)), int(round(y1 + ny * half_width))],
                    [int(round(x2 + nx * half_width)), int(round(y2 + ny * half_width))],
                    [int(round(x2 - nx * half_width)), int(round(y2 - ny * half_width))],
                    [int(round(x1 - nx * half_width)), int(round(y1 - ny * half_width))],
                ],
                dtype=np.int32,
            )

        glow_pts = build_band(glow_half)
        band_pts = build_band(band_half)
        blend_shape(lambda overlay: cv2.fillConvexPoly(overlay, glow_pts, (90, 255, 255)), 0.16)
        blend_shape(lambda overlay: cv2.fillConvexPoly(overlay, band_pts, (34, 220, 240)), 0.34)
        cv2.polylines(annotated, [band_pts], True, (215, 255, 255), 1, lineType=cv2.LINE_AA)
        cv2.line(annotated, (x1, y1), (x2, y2), (255, 255, 255), 2, lineType=cv2.LINE_AA)

    def draw_stylized_box(x: int, y: int, w: int, h: int, color: tuple[int, int, int], label: str | None):
        x = int(x)
        y = int(y)
        w = max(1, int(w))
        h = max(1, int(h))
        x2 = x + w
        y2 = y + h

        blend_shape(lambda overlay: cv2.rectangle(overlay, (x, y), (x2, y2), color, -1), 0.12)

        corner = max(10, min(24, min(w, h) // 4))
        thickness = 2
        line_type = cv2.LINE_AA

        cv2.line(annotated, (x, y), (x + corner, y), color, thickness, lineType=line_type)
        cv2.line(annotated, (x, y), (x, y + corner), color, thickness, lineType=line_type)
        cv2.line(annotated, (x2, y), (x2 - corner, y), color, thickness, lineType=line_type)
        cv2.line(annotated, (x2, y), (x2, y + corner), color, thickness, lineType=line_type)
        cv2.line(annotated, (x, y2), (x + corner, y2), color, thickness, lineType=line_type)
        cv2.line(annotated, (x, y2), (x, y2 - corner), color, thickness, lineType=line_type)
        cv2.line(annotated, (x2, y2), (x2 - corner, y2), color, thickness, lineType=line_type)
        cv2.line(annotated, (x2, y2), (x2, y2 - corner), color, thickness, lineType=line_type)

        if not label:
            return

        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.45
        weight = 1
        (text_w, text_h), baseline = cv2.getTextSize(label, font, scale, weight)
        chip_x = x
        chip_y2 = max(text_h + 10, y - 6)
        chip_y1 = max(0, chip_y2 - text_h - baseline - 10)
        chip_x2 = chip_x + text_w + 16

        blend_shape(
            lambda overlay: cv2.rectangle(overlay, (chip_x, chip_y1), (chip_x2, chip_y2), color, -1),
            0.26,
        )
        cv2.rectangle(annotated, (chip_x, chip_y1), (chip_x2, chip_y2), color, 1, lineType=line_type)
        cv2.putText(
            annotated,
            label,
            (chip_x + 8, chip_y2 - 7),
            font,
            scale,
            (255, 255, 255),
            weight,
            lineType=line_type,
        )

    if style == "clean":
        draw_clean_reference_band()
    else:
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
        is_counted = det["counted"]
        color = (80, 255, 160) if is_counted else (34, 220, 240)
        label = f"#{tid} {vtype}" if show_labels else None

        if style == "clean":
            draw_stylized_box(dx, dy, dw, dh, color, label)
        else:
            cv2.rectangle(annotated, (dx, dy), (dx + dw, dy + dh), color, 2)
        if show_labels and style != "clean":
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
        total_color = (80, 255, 160) if style == "clean" else (0, 255, 0)
        cv2.putText(
            annotated,
            f"TOTAL: {total}",
            (30, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            total_color,
            3,
            lineType=cv2.LINE_AA,
        )

    return annotated

