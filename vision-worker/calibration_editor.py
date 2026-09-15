from __future__ import annotations
import cv2
from worker_config import save_config
from count_geometry import clamp


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
        self._display_w = 0
        self._display_h = 0
        self.dirty = False

    def set_frame_size(self, width: int, height: int):
        self._frame_w = width
        self._frame_h = height
        if self._display_w <= 0 or self._display_h <= 0:
            self._display_w = width
            self._display_h = height

    def set_display_size(self, width: int, height: int):
        self._display_w = max(1, int(width))
        self._display_h = max(1, int(height))

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
        x = clamp(x, 0, max(self._display_w - 1, 0))
        y = clamp(y, 0, max(self._display_h - 1, 0))
        x, y = self._display_to_frame_coords(x, y)

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
            hx, hy = self._frame_to_display_coords(hx, hy)
            cv2.circle(frame, (hx, hy), 6, (255, 255, 0), -1)

        x1, y1 = self._frame_to_display_coords(self.line["x1"], self.line["y1"])
        x2, y2 = self._frame_to_display_coords(self.line["x2"], self.line["y2"])
        cv2.circle(frame, (x1, y1), 7, (0, 0, 255), -1)
        cv2.circle(frame, (x2, y2), 7, (0, 0, 255), -1)

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

    def _display_to_frame_coords(self, x: int, y: int) -> tuple[int, int]:
        if self._frame_w <= 0 or self._frame_h <= 0:
            return int(x), int(y)
        if self._display_w <= 0 or self._display_h <= 0:
            return (
                clamp(int(x), 0, max(self._frame_w - 1, 0)),
                clamp(int(y), 0, max(self._frame_h - 1, 0)),
            )

        mapped_x = int(round((float(x) / float(self._display_w)) * self._frame_w))
        mapped_y = int(round((float(y) / float(self._display_h)) * self._frame_h))
        return (
            clamp(mapped_x, 0, max(self._frame_w - 1, 0)),
            clamp(mapped_y, 0, max(self._frame_h - 1, 0)),
        )

    def _frame_to_display_coords(self, x: int, y: int) -> tuple[int, int]:
        if self._frame_w <= 0 or self._frame_h <= 0:
            return int(x), int(y)
        if self._display_w <= 0 or self._display_h <= 0:
            return int(x), int(y)

        mapped_x = int(round((float(x) / float(self._frame_w)) * self._display_w))
        mapped_y = int(round((float(y) / float(self._frame_h)) * self._display_h))
        return (
            clamp(mapped_x, 0, max(self._display_w - 1, 0)),
            clamp(mapped_y, 0, max(self._display_h - 1, 0)),
        )

    def _reset_drag(self):
        self._drag_action = None
        self._drag_start = None
        self._roi_start = None
        self._line_start = None

