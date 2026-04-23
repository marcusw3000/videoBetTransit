import unittest

from app import (
    DEFAULT_LINE,
    DEFAULT_ROI,
    StreamProfileStore,
    choose_stream_rotation_target,
    count_settled_round_for_stream_rotation,
    consume_pipeline_commands,
    create_mjpeg_app,
    ensure_stream_rotation_profile_state,
    format_stream_profile_table_row,
    is_round_safe_for_stream_rotation,
    normalize_config,
    select_random_stream_profile,
    should_apply_pending_stream_rotation,
    stream_rotation_target_reached,
)


class _FirstChoiceRandom:
    def choice(self, values):
        return values[0]


class _FixedRandIntRandom:
    def __init__(self, value):
        self.value = value

    def randint(self, start, end):
        if not start <= self.value <= end:
            raise AssertionError(f"{self.value} outside {start}..{end}")
        return self.value


def make_cfg():
    return {
        "stream_url": "rtsp://camera-a/live",
        "camera_id": "cam_a",
        "roi": {"x": 1, "y": 2, "w": 100, "h": 80},
        "line": {"x1": 10, "y1": 20, "x2": 90, "y2": 20},
        "count_direction": "down",
        "stream_profiles": [
            {
                "id": "profile-a",
                "name": "Camera A",
                "stream_url": "rtsp://camera-a/live",
                "camera_id": "cam_a",
                "roi": {"x": 1, "y": 2, "w": 100, "h": 80},
                "line": {"x1": 10, "y1": 20, "x2": 90, "y2": 20},
                "count_direction": "down",
            }
        ],
        "selected_stream_profile_id": "profile-a",
    }


class StreamProfileStoreTests(unittest.TestCase):
    def test_apply_stream_url_creates_profile_with_camera_id_and_default_geometry(self):
        cfg = make_cfg()
        store = StreamProfileStore(cfg)

        profile, created = store.apply_stream_url(
            "rtsp://camera-b/live",
            name="Camera B",
            camera_id="cam_b",
        )

        self.assertTrue(created)
        self.assertEqual("cam_b", profile["camera_id"])
        self.assertEqual("rtsp://camera-b/live", profile["stream_url"])
        self.assertEqual(DEFAULT_ROI, profile["roi"])
        self.assertEqual(DEFAULT_LINE, profile["line"])
        self.assertEqual("any", profile["count_direction"])
        self.assertEqual("cam_b", cfg["camera_id"])
        self.assertEqual(profile["id"], cfg["selected_stream_profile_id"])

    def test_save_selected_profile_updates_camera_id_url_roi_and_line_together(self):
        cfg = make_cfg()
        store = StreamProfileStore(cfg)

        profile = store.save_selected_profile(
            name="Camera A Ajustada",
            camera_id="cam_a_adjusted",
            stream_url="rtsp://camera-a-adjusted/live",
            roi={"x": 5, "y": 6, "w": 70, "h": 40},
            line={"x1": 7, "y1": 8, "x2": 90, "y2": 91},
            count_direction="up",
        )

        self.assertEqual("cam_a_adjusted", profile["camera_id"])
        self.assertEqual("rtsp://camera-a-adjusted/live", profile["stream_url"])
        self.assertEqual({"x": 5, "y": 6, "w": 70, "h": 40}, profile["roi"])
        self.assertEqual({"x1": 7, "y1": 8, "x2": 90, "y2": 91}, profile["line"])
        self.assertEqual("up", profile["count_direction"])
        self.assertEqual("cam_a_adjusted", cfg["camera_id"])

    def test_save_selected_profile_accepts_horizontal_count_direction(self):
        cfg = make_cfg()
        store = StreamProfileStore(cfg)

        profile = store.save_selected_profile(count_direction="left_to_right")

        self.assertEqual("right", profile["count_direction"])
        self.assertEqual("right", cfg["count_direction"])

    def test_select_profile_applies_saved_count_direction(self):
        cfg = make_cfg()
        store = StreamProfileStore(cfg)
        selected, _created = store.apply_stream_url(
            "rtsp://camera-b/live",
            name="Camera B",
            camera_id="cam_b",
        )
        store.save_selected_profile(
            roi={"x": 5, "y": 6, "w": 70, "h": 40},
            line={"x1": 100, "y1": 10, "x2": 100, "y2": 90},
            count_direction="left",
        )

        store.select_profile("profile-a")
        profile = store.select_profile(selected["id"])

        self.assertEqual("left", profile["count_direction"])
        self.assertEqual({"x": 5, "y": 6, "w": 70, "h": 40}, profile["roi"])
        self.assertEqual({"x1": 100, "y1": 10, "x2": 100, "y2": 90}, profile["line"])
        self.assertEqual("left", cfg["count_direction"])

    def test_save_profile_entry_adds_inactive_next_stream_with_default_geometry(self):
        cfg = make_cfg()
        store = StreamProfileStore(cfg)

        profile, created = store.save_profile_entry(
            name="Camera B",
            camera_id="cam_b",
            stream_url="rtsp://camera-b/live",
        )

        self.assertTrue(created)
        self.assertEqual("cam_b", profile["camera_id"])
        self.assertEqual(DEFAULT_ROI, profile["roi"])
        self.assertEqual(DEFAULT_LINE, profile["line"])
        self.assertEqual("any", profile["count_direction"])
        self.assertEqual("profile-a", cfg["selected_stream_profile_id"])
        self.assertEqual("cam_a", cfg["camera_id"])

    def test_save_profile_entry_preserves_existing_geometry_and_direction(self):
        cfg = make_cfg()
        store = StreamProfileStore(cfg)
        selected, _created = store.apply_stream_url(
            "rtsp://camera-b/live",
            name="Camera B",
            camera_id="cam_b",
        )
        saved = store.save_selected_profile(
            roi={"x": 5, "y": 6, "w": 70, "h": 40},
            line={"x1": 100, "y1": 10, "x2": 100, "y2": 90},
            count_direction="right",
        )
        store.select_profile("profile-a")

        profile, created = store.save_profile_entry(
            name="Camera B Renomeada",
            camera_id="cam_b",
            stream_url="rtsp://camera-b/live",
        )

        self.assertFalse(created)
        self.assertEqual(selected["id"], profile["id"])
        self.assertEqual("Camera B Renomeada", profile["name"])
        self.assertEqual(saved["roi"], profile["roi"])
        self.assertEqual(saved["line"], profile["line"])
        self.assertEqual("right", profile["count_direction"])
        self.assertEqual("profile-a", cfg["selected_stream_profile_id"])

    def test_normalize_config_adds_disabled_stream_rotation_defaults(self):
        cfg = normalize_config(make_cfg())

        self.assertEqual(
            {
                "enabled": False,
                "mode": "round_boundary",
                "strategy": "uniform_excluding_current",
                "min_rounds_per_stream": 6,
                "max_rounds_per_stream": 11,
                "current_stream_profile_id": "",
                "rounds_on_current_stream": 0,
                "target_rounds_for_current_stream": 0,
                "last_counted_round_id": "",
            },
            cfg["stream_rotation"],
        )

    def test_list_profiles_preserves_multiple_saved_streams(self):
        cfg = make_cfg()
        store = StreamProfileStore(cfg)

        store.apply_stream_url("rtsp://camera-b/live", name="Camera B", camera_id="cam_b")

        profiles = store.list_profiles()
        self.assertEqual(["Camera A", "Camera B"], [profile["name"] for profile in profiles])
        self.assertEqual(["cam_a", "cam_b"], [profile["camera_id"] for profile in profiles])
        self.assertEqual(
            ["rtsp://camera-a/live", "rtsp://camera-b/live"],
            [profile["stream_url"] for profile in profiles],
        )

    def test_format_stream_profile_table_row_includes_name_camera_id_and_url(self):
        profile = {
            "name": "Camera B",
            "camera_id": "cam_b",
            "stream_url": "rtsp://camera-b/live",
        }

        row = format_stream_profile_table_row(profile, active=True)

        self.assertEqual(("*", "Camera B", "cam_b", "rtsp://camera-b/live"), row)

    def test_delete_non_active_profile_preserves_selected_profile(self):
        cfg = make_cfg()
        store = StreamProfileStore(cfg)
        selected, _created = store.apply_stream_url(
            "rtsp://camera-b/live",
            name="Camera B",
            camera_id="cam_b",
        )

        deleted = store.delete_profile("profile-a")

        self.assertEqual("Camera A", deleted["name"])
        self.assertEqual(selected["id"], cfg["selected_stream_profile_id"])
        self.assertEqual(["Camera B"], [profile["name"] for profile in store.list_profiles()])
        self.assertEqual("cam_b", cfg["camera_id"])

    def test_delete_active_profile_is_blocked(self):
        cfg = make_cfg()
        store = StreamProfileStore(cfg)
        selected, _created = store.apply_stream_url(
            "rtsp://camera-b/live",
            name="Camera B",
            camera_id="cam_b",
        )

        with self.assertRaisesRegex(ValueError, "Carregue outra stream"):
            store.delete_profile(selected["id"])

    def test_delete_last_profile_is_blocked(self):
        cfg = make_cfg()
        store = StreamProfileStore(cfg)

        with self.assertRaisesRegex(ValueError, "pelo menos uma stream"):
            store.delete_profile("profile-a")


class StreamRotationTests(unittest.TestCase):
    def test_rotation_target_is_drawn_inside_configured_range(self):
        rotation = {
            "min_rounds_per_stream": 6,
            "max_rounds_per_stream": 11,
        }

        target = choose_stream_rotation_target(rotation, rng=_FixedRandIntRandom(9))

        self.assertEqual(9, target)

    def test_profile_state_resets_counter_when_stream_changes(self):
        rotation = {
            "current_stream_profile_id": "profile-a",
            "rounds_on_current_stream": 7,
            "target_rounds_for_current_stream": 9,
            "last_counted_round_id": "round-a",
            "min_rounds_per_stream": 6,
            "max_rounds_per_stream": 11,
        }

        changed = ensure_stream_rotation_profile_state(
            rotation,
            "profile-b",
            rng=_FixedRandIntRandom(10),
        )

        self.assertTrue(changed)
        self.assertEqual("profile-b", rotation["current_stream_profile_id"])
        self.assertEqual(0, rotation["rounds_on_current_stream"])
        self.assertEqual(10, rotation["target_rounds_for_current_stream"])
        self.assertEqual("", rotation["last_counted_round_id"])

    def test_profile_state_draws_target_when_missing_without_resetting_same_stream(self):
        rotation = {
            "current_stream_profile_id": "profile-a",
            "rounds_on_current_stream": 3,
            "target_rounds_for_current_stream": 0,
            "last_counted_round_id": "round-a",
            "min_rounds_per_stream": 6,
            "max_rounds_per_stream": 11,
        }

        changed = ensure_stream_rotation_profile_state(
            rotation,
            "profile-a",
            rng=_FixedRandIntRandom(11),
        )

        self.assertTrue(changed)
        self.assertEqual(3, rotation["rounds_on_current_stream"])
        self.assertEqual("round-a", rotation["last_counted_round_id"])
        self.assertEqual(11, rotation["target_rounds_for_current_stream"])

    def test_rotation_counts_safe_round_once_when_settling_starts(self):
        rotation = {
            "rounds_on_current_stream": 0,
            "target_rounds_for_current_stream": 2,
            "last_counted_round_id": "",
        }

        for status in ["open", "closing", "void"]:
            self.assertFalse(count_settled_round_for_stream_rotation(rotation, {"roundId": f"round-{status}", "status": status}))

        self.assertTrue(count_settled_round_for_stream_rotation(rotation, {"roundId": "round-1", "status": "settling"}))
        self.assertFalse(count_settled_round_for_stream_rotation(rotation, {"roundId": "round-1", "status": "settled"}))
        self.assertEqual(1, rotation["rounds_on_current_stream"])

    def test_rotation_target_reached_when_counter_reaches_drawn_target(self):
        rotation = {
            "rounds_on_current_stream": 7,
            "target_rounds_for_current_stream": 8,
        }

        self.assertFalse(stream_rotation_target_reached(rotation))
        rotation["rounds_on_current_stream"] = 8
        self.assertTrue(stream_rotation_target_reached(rotation))

    def test_random_selection_excludes_current_profile(self):
        cfg = make_cfg()
        store = StreamProfileStore(cfg)
        store.apply_stream_url("rtsp://camera-b/live", name="Camera B", camera_id="cam_b")

        selected = select_random_stream_profile(
            store.list_profiles(),
            "profile-a",
            rng=_FirstChoiceRandom(),
        )

        self.assertIsNotNone(selected)
        self.assertEqual("cam_b", selected["camera_id"])

    def test_random_selection_requires_two_eligible_profiles(self):
        cfg = make_cfg()
        store = StreamProfileStore(cfg)

        selected = select_random_stream_profile(
            store.list_profiles(),
            "profile-a",
            rng=_FirstChoiceRandom(),
        )

        self.assertIsNone(selected)

    def test_pending_rotation_waits_for_non_countable_round_window(self):
        pending = {"id": "profile-b", "camera_id": "cam_b", "stream_url": "rtsp://camera-b/live"}

        self.assertFalse(should_apply_pending_stream_rotation(pending, {"status": "open"}))
        self.assertFalse(should_apply_pending_stream_rotation(pending, {"status": "closing"}))
        self.assertTrue(should_apply_pending_stream_rotation(pending, {"status": "settling"}))
        self.assertTrue(is_round_safe_for_stream_rotation({"status": "settling"}))


class WorkerApiContractTests(unittest.TestCase):
    def test_health_exposes_active_profile_and_rotation_status(self):
        client = create_mjpeg_app().test_client()

        response = client.get("/health")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertIn("selectedStreamProfileId", payload)
        self.assertIn("streamRotation", payload)
        self.assertIn("pending", payload["streamRotation"])

    def test_pipeline_start_accepts_stream_contract_without_starting_capture_inline(self):
        client = create_mjpeg_app().test_client()

        response = client.post(
            "/pipeline/start",
            json={
                "sessionId": "session-1",
                "cameraId": "cam_contract",
                "sourceUrl": "rtsp://camera-contract/live",
                "rawStreamPath": "raw/cam_contract",
                "processedStreamPath": "processed/cam_contract",
                "direction": "left",
                "countLine": {"x1": 1, "y1": 2, "x2": 3, "y2": 4},
            },
        )

        self.assertEqual(200, response.status_code)
        queued, should_stop, should_refresh = consume_pipeline_commands()
        self.assertFalse(should_stop)
        self.assertFalse(should_refresh)
        self.assertEqual("cam_contract", queued.camera_id)
        self.assertEqual("rtsp://camera-contract/live", queued.source_url)
        self.assertEqual("left", queued.direction)
        self.assertEqual({"x1": 1, "y1": 2, "x2": 3, "y2": 4}, queued.count_line)


if __name__ == "__main__":
    unittest.main()
