import unittest

from app import (
    bbox_area,
    crossed_horizontal_segment,
    crossed_vertical_segment,
    inside_roi,
    normalize_count_direction,
    point_inside_line_band,
    resolve_round_sync,
    should_count_track,
    should_count_track_fallback,
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


class CrossedVerticalSegmentTests(unittest.TestCase):
    def test_counts_rightward_crossing_inside_segment(self):
        self.assertTrue(
            crossed_vertical_segment(
                prev_x=90,
                curr_x=110,
                line_x=100,
                cy=50,
                y1=10,
                y2=90,
                direction="right",
            )
        )

    def test_counts_leftward_crossing_inside_segment(self):
        self.assertTrue(
            crossed_vertical_segment(
                prev_x=110,
                curr_x=90,
                line_x=100,
                cy=50,
                y1=10,
                y2=90,
                direction="left",
            )
        )

    def test_any_direction_accepts_both_vertical_crossings(self):
        self.assertTrue(
            crossed_vertical_segment(
                prev_x=110,
                curr_x=90,
                line_x=100,
                cy=50,
                y1=10,
                y2=90,
                direction="any",
            )
        )
        self.assertTrue(
            crossed_vertical_segment(
                prev_x=90,
                curr_x=110,
                line_x=100,
                cy=50,
                y1=10,
                y2=90,
                direction="any",
            )
        )

    def test_does_not_count_without_vertical_crossing(self):
        self.assertFalse(
            crossed_vertical_segment(
                prev_x=90,
                curr_x=95,
                line_x=100,
                cy=50,
                y1=10,
                y2=90,
                direction="right",
            )
        )

    def test_does_not_count_outside_vertical_segment(self):
        self.assertFalse(
            crossed_vertical_segment(
                prev_x=90,
                curr_x=110,
                line_x=100,
                cy=5,
                y1=10,
                y2=90,
                direction="right",
            )
        )


class CountDirectionNormalizationTests(unittest.TestCase):
    def test_accepts_new_horizontal_directions(self):
        self.assertEqual("left", normalize_count_direction("left"))
        self.assertEqual("right", normalize_count_direction("right"))

    def test_maps_legacy_vertical_names(self):
        self.assertEqual("up", normalize_count_direction("down_to_up"))
        self.assertEqual("down", normalize_count_direction("up_to_down"))

    def test_maps_legacy_horizontal_names(self):
        self.assertEqual("right", normalize_count_direction("left_to_right"))
        self.assertEqual("left", normalize_count_direction("right_to_left"))


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
                prev_position=None,
                curr_position=(50, 110),
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
                prev_position=(50, 90),
                curr_position=(50, 110),
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
                prev_position=(50, 90),
                curr_position=(50, 110),
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
                prev_position=(50, 90),
                curr_position=(50, 110),
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
                prev_position=(50, 90),
                curr_position=(50, 110),
                line=self.line,
                direction="up",
                hits=4,
                min_hits_to_count=4,
                already_counted=False,
            )
        )

    def test_counts_vertical_line_crossing(self):
        vertical_line = {"x1": 100, "y1": 10, "x2": 100, "y2": 90}

        self.assertTrue(
            should_count_track(
                prev_position=(90, 50),
                curr_position=(110, 50),
                line=vertical_line,
                direction="right",
                hits=4,
                min_hits_to_count=4,
                already_counted=False,
            )
        )


class SecondaryVerificationTests(unittest.TestCase):
    def test_point_inside_line_band_supports_diagonal_lines(self):
        diagonal_line = {"x1": 20, "y1": 20, "x2": 80, "y2": 80}

        self.assertTrue(point_inside_line_band((50, 54), diagonal_line, 8))
        self.assertFalse(point_inside_line_band((50, 70), diagonal_line, 8))

    def test_fallback_counts_after_multiple_band_hits_with_progress(self):
        line = {"x1": 20, "y1": 100, "x2": 140, "y2": 100}
        state = {}

        first = should_count_track_fallback(
            prev_position=(60, 88),
            curr_position=(60, 95),
            line=line,
            direction="down",
            hits=4,
            min_hits_to_count=4,
            already_counted=False,
            band_px=18,
            state=state,
        )
        second = should_count_track_fallback(
            prev_position=(60, 95),
            curr_position=(60, 102),
            line=line,
            direction="down",
            hits=5,
            min_hits_to_count=4,
            already_counted=False,
            band_px=18,
            state=state,
        )

        self.assertFalse(first)
        self.assertTrue(second)
        self.assertTrue(state["enteredFallbackBand"])
        self.assertGreaterEqual(state["fallbackEligibleFrames"], 2)

    def test_fallback_does_not_count_parallel_touch_without_progress(self):
        line = {"x1": 20, "y1": 100, "x2": 140, "y2": 100}
        state = {}

        counted = should_count_track_fallback(
            prev_position=(60, 96),
            curr_position=(72, 97),
            line=line,
            direction="down",
            hits=4,
            min_hits_to_count=4,
            already_counted=False,
            band_px=18,
            state=state,
        )

        self.assertFalse(counted)
        self.assertEqual(0, state.get("fallbackEligibleFrames", 0))

    def test_fallback_respects_double_count_guard(self):
        line = {"x1": 20, "y1": 100, "x2": 140, "y2": 100}
        state = {}

        counted = should_count_track_fallback(
            prev_position=(60, 88),
            curr_position=(60, 98),
            line=line,
            direction="down",
            hits=4,
            min_hits_to_count=4,
            already_counted=True,
            band_px=18,
            state=state,
        )

        self.assertFalse(counted)


class ResolveRoundSyncTests(unittest.TestCase):
    def test_keeps_current_round_when_backend_payload_is_missing(self):
        round_id, total, changed = resolve_round_sync("rnd_1", None, 4)

        self.assertEqual("rnd_1", round_id)
        self.assertEqual(4, total)
        self.assertFalse(changed)

    def test_detects_round_change_and_resets_total_to_backend_count(self):
        round_id, total, changed = resolve_round_sync(
            "rnd_1",
            {"roundId": "rnd_2", "currentCount": 0},
            9,
        )

        self.assertEqual("rnd_2", round_id)
        self.assertEqual(0, total)
        self.assertTrue(changed)

    def test_keeps_total_when_round_is_the_same(self):
        round_id, total, changed = resolve_round_sync(
            "rnd_2",
            {"roundId": "rnd_2", "currentCount": 0},
            6,
        )

        self.assertEqual("rnd_2", round_id)
        self.assertEqual(6, total)
        self.assertFalse(changed)

    def test_ignores_backend_payload_without_round_id(self):
        round_id, total, changed = resolve_round_sync(
            "rnd_2",
            {"id": "legacy_field_only", "currentCount": 3},
            6,
        )

        self.assertEqual("rnd_2", round_id)
        self.assertEqual(6, total)
        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
