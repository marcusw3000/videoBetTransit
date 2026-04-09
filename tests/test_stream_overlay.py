import unittest

import numpy as np

from app import annotate_frame, is_countable_vehicle


class AnnotateFrameTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((120, 160, 3), dtype=np.uint8)
        self.roi = {"x": 10, "y": 10, "w": 40, "h": 30}
        self.line = {"x1": 20, "y1": 80, "x2": 120, "y2": 80}
        self.detections = [
            {
                "trackId": "7",
                "vehicleType": "car",
                "bbox": {"x": 50, "y": 30, "w": 20, "h": 20},
                "center": {"x": 60, "y": 50},
                "counted": False,
            }
        ]

    def test_browser_overlay_keeps_only_line_and_boxes(self):
        annotated = annotate_frame(
            self.frame,
            self.roi,
            self.line,
            self.detections,
            total=3,
            show_roi=False,
            show_labels=False,
            show_centers=False,
            show_total=False,
        )

        self.assertTrue(np.any(annotated[80, 20:121] != 0))
        self.assertTrue(np.any(annotated[30:51, 50] != 0))
        self.assertTrue(np.all(annotated[10, 10] == 0))
        self.assertTrue(np.all(annotated[40, 60] == 0))
        self.assertTrue(np.all(annotated[50, 30] == 0))

    def test_operator_overlay_can_include_roi(self):
        annotated = annotate_frame(
            self.frame,
            self.roi,
            self.line,
            self.detections,
            total=3,
        )

        self.assertTrue(np.any(annotated[10, 10] != 0))


class VehicleFilterTests(unittest.TestCase):
    def test_only_car_is_countable(self):
        self.assertTrue(is_countable_vehicle("car"))
        self.assertTrue(is_countable_vehicle("CAR"))
        self.assertFalse(is_countable_vehicle("truck"))
        self.assertFalse(is_countable_vehicle("bus"))
        self.assertFalse(is_countable_vehicle("motorcycle"))


if __name__ == "__main__":
    unittest.main()
