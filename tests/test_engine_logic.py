import unittest

from app import (
    bbox_area,
    crossed_horizontal_segment,
    inside_roi,
    resolve_round_sync,
    should_count_track,
)


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


class ResolveRoundSyncTests(unittest.TestCase):
    def test_keeps_current_round_when_backend_payload_is_missing(self):
        round_id, total, changed = resolve_round_sync("rnd_1", None, 4)

        self.assertEqual("rnd_1", round_id)
        self.assertEqual(4, total)
        self.assertFalse(changed)

    def test_detects_round_change_and_resets_total_to_backend_count(self):
        round_id, total, changed = resolve_round_sync(
            "rnd_1",
            {"id": "rnd_2", "currentCount": 0},
            9,
        )

        self.assertEqual("rnd_2", round_id)
        self.assertEqual(0, total)
        self.assertTrue(changed)

    def test_keeps_total_when_round_is_the_same(self):
        round_id, total, changed = resolve_round_sync(
            "rnd_2",
            {"id": "rnd_2", "currentCount": 0},
            6,
        )

        self.assertEqual("rnd_2", round_id)
        self.assertEqual(6, total)
        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
