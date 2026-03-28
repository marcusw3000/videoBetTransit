import unittest

from app import bbox_area, crossed_horizontal_segment, get_class_thresholds, inside_roi, should_count_track


class InsideRoiTests(unittest.TestCase):
    def test_point_inside_roi(self):
        roi = {"x": 10, "y": 20, "w": 100, "h": 50}
        self.assertTrue(inside_roi(50, 40, roi))

    def test_point_on_roi_border_counts_as_inside(self):
        roi = {"x": 10, "y": 20, "w": 100, "h": 50}
        self.assertTrue(inside_roi(10, 20, roi))
        self.assertTrue(inside_roi(110, 70, roi))

    def test_point_outside_roi(self):
        roi = {"x": 10, "y": 20, "w": 100, "h": 50}
        self.assertFalse(inside_roi(9, 40, roi))
        self.assertFalse(inside_roi(50, 71, roi))


class CrossedHorizontalSegmentTests(unittest.TestCase):
    def test_counts_downward_crossing_inside_segment(self):
        self.assertTrue(
            crossed_horizontal_segment(
                prev_y=90,
                curr_y=110,
                line_y=100,
                cx=50,
                x1=10,
                x2=90,
                direction="down",
            )
        )

    def test_counts_upward_crossing_inside_segment(self):
        self.assertTrue(
            crossed_horizontal_segment(
                prev_y=110,
                curr_y=90,
                line_y=100,
                cx=50,
                x1=10,
                x2=90,
                direction="up",
            )
        )

    def test_any_direction_accepts_both_crossings(self):
        self.assertTrue(
            crossed_horizontal_segment(
                prev_y=110,
                curr_y=90,
                line_y=100,
                cx=50,
                x1=10,
                x2=90,
                direction="any",
            )
        )
        self.assertTrue(
            crossed_horizontal_segment(
                prev_y=90,
                curr_y=110,
                line_y=100,
                cx=50,
                x1=10,
                x2=90,
                direction="any",
            )
        )

    def test_does_not_count_without_crossing_line(self):
        self.assertFalse(
            crossed_horizontal_segment(
                prev_y=90,
                curr_y=95,
                line_y=100,
                cx=50,
                x1=10,
                x2=90,
                direction="down",
            )
        )

    def test_does_not_count_outside_horizontal_segment(self):
        self.assertFalse(
            crossed_horizontal_segment(
                prev_y=90,
                curr_y=110,
                line_y=100,
                cx=5,
                x1=10,
                x2=90,
                direction="down",
            )
        )

    def test_invalid_direction_does_not_count(self):
        self.assertFalse(
            crossed_horizontal_segment(
                prev_y=90,
                curr_y=110,
                line_y=100,
                cx=50,
                x1=10,
                x2=90,
                direction="sideways",
            )
        )

    def test_dead_zone_requires_real_crossing_beyond_band(self):
        self.assertFalse(
            crossed_horizontal_segment(
                prev_y=96,
                curr_y=104,
                line_y=100,
                cx=50,
                x1=10,
                x2=90,
                direction="down",
                dead_zone_px=5,
            )
        )
        self.assertTrue(
            crossed_horizontal_segment(
                prev_y=90,
                curr_y=106,
                line_y=100,
                cx=50,
                x1=10,
                x2=90,
                direction="down",
                dead_zone_px=5,
            )
        )


class BboxAreaTests(unittest.TestCase):
    def test_returns_positive_area(self):
        self.assertEqual(bbox_area(10, 10, 25, 30), 300)

    def test_returns_zero_for_inverted_coordinates(self):
        self.assertEqual(bbox_area(25, 10, 10, 30), 0)
        self.assertEqual(bbox_area(10, 30, 25, 10), 0)


class ShouldCountTrackTests(unittest.TestCase):
    def setUp(self):
        self.line = {"x1": 10, "y1": 100, "x2": 90, "y2": 100}

    def test_requires_previous_position(self):
        self.assertFalse(
            should_count_track(
                prev_y=None,
                curr_y=110,
                cx=50,
                line=self.line,
                direction="down",
                hits=4,
                min_hits_to_count=4,
                already_counted=False,
            )
        )

    def test_requires_minimum_hits(self):
        self.assertFalse(
            should_count_track(
                prev_y=90,
                curr_y=110,
                cx=50,
                line=self.line,
                direction="down",
                hits=3,
                min_hits_to_count=4,
                already_counted=False,
            )
        )

    def test_prevents_double_counting(self):
        self.assertFalse(
            should_count_track(
                prev_y=90,
                curr_y=110,
                cx=50,
                line=self.line,
                direction="down",
                hits=4,
                min_hits_to_count=4,
                already_counted=True,
            )
        )

    def test_counts_valid_crossing(self):
        self.assertTrue(
            should_count_track(
                prev_y=90,
                curr_y=110,
                cx=50,
                line=self.line,
                direction="down",
                hits=4,
                min_hits_to_count=4,
                already_counted=False,
            )
        )

    def test_respects_direction(self):
        self.assertFalse(
            should_count_track(
                prev_y=90,
                curr_y=110,
                cx=50,
                line=self.line,
                direction="up",
                hits=4,
                min_hits_to_count=4,
                already_counted=False,
            )
        )

    def test_respects_dead_zone(self):
        self.assertFalse(
            should_count_track(
                prev_y=96,
                curr_y=104,
                cx=50,
                line=self.line,
                direction="down",
                hits=4,
                min_hits_to_count=4,
                already_counted=False,
                dead_zone_px=5,
            )
        )


class ClassThresholdTests(unittest.TestCase):
    def test_returns_defaults_when_override_is_missing(self):
        cfg = {
            "conf": 0.2,
            "min_bbox_area": 100,
            "min_hits_to_count": 4,
            "class_thresholds": {},
        }

        self.assertEqual(
            {
                "min_bbox_area": 100,
                "min_hits_to_count": 4,
                "min_confidence": 0.2,
            },
            get_class_thresholds(cfg, "car"),
        )

    def test_merges_class_specific_thresholds(self):
        cfg = {
            "conf": 0.2,
            "min_bbox_area": 100,
            "min_hits_to_count": 4,
            "class_thresholds": {
                "motorcycle": {
                    "min_bbox_area": 80,
                    "min_hits_to_count": 5,
                    "min_confidence": 0.18,
                }
            },
        }

        self.assertEqual(
            {
                "min_bbox_area": 80,
                "min_hits_to_count": 5,
                "min_confidence": 0.18,
            },
            get_class_thresholds(cfg, "motorcycle"),
        )


if __name__ == "__main__":
    unittest.main()
