import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from app import (
    DEFAULT_LINE,
    DEFAULT_ROI,
    StreamProfileStore,
    StreamScheduleStore,
    choose_stream_rotation_target,
    choose_schedule_enforcement_profile,
    count_settled_round_for_stream_rotation,
    consume_pipeline_commands,
    create_mjpeg_app,
    ensure_stream_rotation_profile_state,
    format_stream_profile_table_row,
    is_round_safe_for_stream_rotation,
    normalize_config,
    normalize_stream_schedule_config,
    resolve_stream_schedule_state,
    select_random_stream_profile,
    should_apply_pending_stream_rotation,
    stream_rotation_target_reached,
)
from supabase_sync import SupabaseStreamProfileSync


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


def make_cfg_with_two_profiles():
    cfg = make_cfg()
    cfg["stream_profiles"].append(
        {
            "id": "profile-b",
            "name": "Camera B",
            "stream_url": "rtsp://camera-b/live",
            "camera_id": "cam_b",
            "roi": {"x": 5, "y": 6, "w": 70, "h": 40},
            "line": {"x1": 100, "y1": 10, "x2": 100, "y2": 90},
            "count_direction": "left",
        }
    )
    return cfg


def make_cfg_with_three_profiles():
    cfg = make_cfg_with_two_profiles()
    cfg["stream_profiles"].append(
        {
            "id": "profile-c",
            "name": "Camera C",
            "stream_url": "rtsp://camera-c/live",
            "camera_id": "cam_c",
            "roi": {"x": 9, "y": 10, "w": 60, "h": 44},
            "line": {"x1": 30, "y1": 40, "x2": 88, "y2": 40},
            "count_direction": "any",
        }
    )
    return cfg


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
        self.assertFalse(profile["secondary_verification_enabled"])
        self.assertEqual(18, profile["secondary_verification_band_px"])
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
            secondary_verification_enabled=True,
            secondary_verification_band_px=24,
        )

        self.assertEqual("cam_a_adjusted", profile["camera_id"])
        self.assertEqual("rtsp://camera-a-adjusted/live", profile["stream_url"])
        self.assertEqual({"x": 5, "y": 6, "w": 70, "h": 40}, profile["roi"])
        self.assertEqual({"x1": 7, "y1": 8, "x2": 90, "y2": 91}, profile["line"])
        self.assertEqual("up", profile["count_direction"])
        self.assertTrue(profile["secondary_verification_enabled"])
        self.assertEqual(24, profile["secondary_verification_band_px"])
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
        self.assertFalse(profile["secondary_verification_enabled"])
        self.assertEqual(18, profile["secondary_verification_band_px"])
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
        self.assertEqual(saved["secondary_verification_enabled"], profile["secondary_verification_enabled"])
        self.assertEqual(saved["secondary_verification_band_px"], profile["secondary_verification_band_px"])
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
        self.assertFalse(cfg["secondary_verification_enabled"])
        self.assertEqual(18, cfg["secondary_verification_band_px"])

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
        self.assertIn("secondary_verification_enabled", profiles[0])
        self.assertIn("secondary_verification_band_px", profiles[0])

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


class StreamScheduleTests(unittest.TestCase):
    def test_normalize_config_adds_stream_schedule_defaults(self):
        cfg = normalize_config(make_cfg())

        self.assertEqual(
            {
                "timezone": "America/Sao_Paulo",
                "outside_window_behavior": "allow_all",
                "rules": [],
            },
            cfg["stream_schedule"],
        )

    def test_normalize_stream_schedule_accepts_overnight_window(self):
        cfg = make_cfg_with_two_profiles()

        schedule = normalize_stream_schedule_config(
            {
                "timezone": "America/Sao_Paulo",
                "rules": [
                    {
                        "id": "night",
                        "name": "Madrugada",
                        "enabled": True,
                        "start_time": "23:00",
                        "end_time": "05:00",
                        "allowed_profile_ids": ["profile-b"],
                    }
                ],
            },
            cfg["stream_profiles"],
        )

        self.assertEqual("America/Sao_Paulo", schedule["timezone"])
        self.assertEqual("23:00", schedule["rules"][0]["start_time"])
        self.assertEqual("05:00", schedule["rules"][0]["end_time"])

    def test_normalize_stream_schedule_rejects_missing_profile_ids(self):
        cfg = make_cfg()

        with self.assertRaisesRegex(ValueError, "streams inexistentes"):
            normalize_stream_schedule_config(
                {
                    "rules": [
                        {
                            "id": "invalid",
                            "name": "Invalida",
                            "enabled": True,
                            "start_time": "10:00",
                            "end_time": "12:00",
                            "allowed_profile_ids": ["profile-z"],
                        }
                    ]
                },
                cfg["stream_profiles"],
            )

    def test_normalize_stream_schedule_allows_overlapping_enabled_rules_for_different_cameras(self):
        cfg = make_cfg_with_two_profiles()
        schedule = normalize_stream_schedule_config(
            {
                "rules": [
                    {
                        "id": "morning-a",
                        "name": "A",
                        "enabled": True,
                        "start_time": "08:00",
                        "end_time": "11:00",
                        "allowed_profile_ids": ["profile-a"],
                    },
                    {
                        "id": "morning-b",
                        "name": "B",
                        "enabled": True,
                        "start_time": "10:30",
                        "end_time": "12:00",
                        "allowed_profile_ids": ["profile-b"],
                    },
                ]
            },
            cfg["stream_profiles"],
        )

        self.assertEqual(2, len(schedule["rules"]))

    def test_normalize_stream_schedule_rejects_overlapping_enabled_rules_for_same_camera(self):
        cfg = make_cfg_with_two_profiles()

        with self.assertRaisesRegex(ValueError, "mesma camera"):
            normalize_stream_schedule_config(
                {
                    "rules": [
                        {
                            "id": "morning-a",
                            "name": "A1",
                            "enabled": True,
                            "start_time": "08:00",
                            "end_time": "11:00",
                            "allowed_profile_ids": ["profile-a"],
                        },
                        {
                            "id": "morning-b",
                            "name": "A2",
                            "enabled": True,
                            "start_time": "10:30",
                            "end_time": "12:00",
                            "allowed_profile_ids": ["profile-a"],
                        },
                    ]
                },
                cfg["stream_profiles"],
            )

    def test_resolve_stream_schedule_returns_all_profiles_outside_rule(self):
        cfg = make_cfg_with_two_profiles()
        cfg["stream_schedule"] = {
            "timezone": "America/Sao_Paulo",
            "rules": [
                {
                    "id": "rush",
                    "name": "Rush",
                    "enabled": True,
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "allowed_profile_ids": ["profile-a"],
                }
            ],
        }

        state = resolve_stream_schedule_state(
            cfg["stream_schedule"],
            cfg["stream_profiles"],
            now=datetime(2026, 4, 24, 11, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
        )

        self.assertFalse(state["isRestricted"])
        self.assertEqual({"profile-a", "profile-b"}, set(state["eligibleProfileIds"]))

    def test_resolve_stream_schedule_can_restrict_outside_window(self):
        cfg = make_cfg_with_two_profiles()
        cfg["stream_schedule"] = {
            "timezone": "America/Sao_Paulo",
            "outside_window_behavior": "restrict_configured",
            "rules": [
                {
                    "id": "rush",
                    "name": "Rush",
                    "enabled": True,
                    "start_time": "09:00",
                    "end_time": "19:00",
                    "allowed_profile_ids": ["profile-b"],
                }
            ],
        }

        state = resolve_stream_schedule_state(
            cfg["stream_schedule"],
            cfg["stream_profiles"],
            now=datetime(2026, 4, 24, 5, 29, tzinfo=ZoneInfo("America/Sao_Paulo")),
        )

        self.assertTrue(state["isRestricted"])
        self.assertFalse(state["outsideWindowRestricted"])
        self.assertEqual(["profile-a"], state["eligibleProfileIds"])

    def test_resolve_stream_schedule_keeps_unscheduled_profiles_allowed_by_default(self):
        cfg = make_cfg_with_three_profiles()
        cfg["stream_schedule"] = {
            "timezone": "America/Sao_Paulo",
            "outside_window_behavior": "restrict_configured",
            "rules": [
                {
                    "id": "rush-a",
                    "name": "Rush A",
                    "enabled": True,
                    "start_time": "09:00",
                    "end_time": "19:00",
                    "allowed_profile_ids": ["profile-a"],
                },
                {
                    "id": "rush-b",
                    "name": "Rush B",
                    "enabled": True,
                    "start_time": "09:00",
                    "end_time": "19:00",
                    "allowed_profile_ids": ["profile-b"],
                },
            ],
        }

        state = resolve_stream_schedule_state(
            cfg["stream_schedule"],
            cfg["stream_profiles"],
            now=datetime(2026, 4, 24, 5, 29, tzinfo=ZoneInfo("America/Sao_Paulo")),
        )

        self.assertTrue(state["isRestricted"])
        self.assertFalse(state["outsideWindowRestricted"])
        self.assertEqual(["profile-c"], state["eligibleProfileIds"])

    def test_resolve_stream_schedule_keeps_unscheduled_profiles_alongside_active_scheduled_profiles(self):
        cfg = make_cfg_with_three_profiles()
        cfg["stream_schedule"] = {
            "timezone": "America/Sao_Paulo",
            "outside_window_behavior": "restrict_configured",
            "rules": [
                {
                    "id": "rush-a",
                    "name": "Rush A",
                    "enabled": True,
                    "start_time": "09:00",
                    "end_time": "19:00",
                    "allowed_profile_ids": ["profile-a"],
                }
            ],
        }

        state = resolve_stream_schedule_state(
            cfg["stream_schedule"],
            cfg["stream_profiles"],
            now=datetime(2026, 4, 24, 9, 30, tzinfo=ZoneInfo("America/Sao_Paulo")),
        )

        self.assertTrue(state["isRestricted"])
        self.assertEqual({"profile-a", "profile-b", "profile-c"}, set(state["eligibleProfileIds"]))

    def test_resolve_stream_schedule_returns_only_allowed_profiles_inside_rule(self):
        cfg = make_cfg_with_two_profiles()
        cfg["stream_schedule"] = {
            "timezone": "America/Sao_Paulo",
            "rules": [
                {
                    "id": "rush",
                    "name": "Rush",
                    "enabled": True,
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "allowed_profile_ids": ["profile-b"],
                }
            ],
        }

        state = resolve_stream_schedule_state(
            cfg["stream_schedule"],
            cfg["stream_profiles"],
            now=datetime(2026, 4, 24, 8, 30, tzinfo=ZoneInfo("America/Sao_Paulo")),
        )

        self.assertTrue(state["isRestricted"])
        self.assertEqual("rush", state["activeRule"]["id"])
        self.assertEqual(["profile-a", "profile-b"], state["eligibleProfileIds"])

    def test_schedule_enforcement_prefers_first_eligible_when_current_is_invalid(self):
        cfg = make_cfg_with_two_profiles()

        chosen = choose_schedule_enforcement_profile(
            {"id": "profile-a"},
            [cfg["stream_profiles"][1]],
        )

        self.assertEqual("profile-b", chosen["id"])

    def test_schedule_store_blocks_profile_deletion_when_rule_references_it(self):
        cfg = normalize_config(make_cfg_with_two_profiles())
        cfg["stream_schedule"] = {
            "timezone": "America/Sao_Paulo",
            "rules": [
                {
                    "id": "rush",
                    "name": "Rush",
                    "enabled": True,
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "allowed_profile_ids": ["profile-a"],
                }
            ],
        }
        cfg = normalize_config(cfg)
        store = StreamScheduleStore(cfg)

        with self.assertRaisesRegex(ValueError, "vinculada a uma agenda"):
            store.assert_profile_not_referenced("profile-a")

    def test_detach_profile_references_deletes_empty_rules(self):
        cfg = normalize_config(make_cfg_with_two_profiles())
        cfg["stream_schedule"] = {
            "timezone": "America/Sao_Paulo",
            "rules": [
                {
                    "id": "rush",
                    "name": "Rush",
                    "enabled": True,
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "allowed_profile_ids": ["profile-a"],
                }
            ],
        }
        store = StreamScheduleStore(normalize_config(cfg))

        result = store.detach_profile_references("profile-a")

        self.assertEqual([], store.list_rules())
        self.assertEqual([], result["updatedRuleIds"])
        self.assertEqual(["rush"], result["deletedRuleIds"])

    def test_detach_profile_references_preserves_rules_with_other_profiles(self):
        cfg = normalize_config(make_cfg_with_two_profiles())
        cfg["stream_schedule"] = {
            "timezone": "America/Sao_Paulo",
            "rules": [
                {
                    "id": "rush",
                    "name": "Rush",
                    "enabled": True,
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "allowed_profile_ids": ["profile-a", "profile-b"],
                }
            ],
        }
        store = StreamScheduleStore(normalize_config(cfg))

        result = store.detach_profile_references("profile-a")

        self.assertEqual(["rush"], result["updatedRuleIds"])
        self.assertEqual([], result["deletedRuleIds"])
        self.assertEqual(["profile-b"], store.list_rules()[0]["allowed_profile_ids"])


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

    def test_random_selection_uses_only_profiles_allowed_by_schedule(self):
        cfg = make_cfg_with_two_profiles()
        cfg["stream_profiles"].append(
            {
                "id": "profile-c",
                "name": "Camera C",
                "stream_url": "rtsp://camera-c/live",
                "camera_id": "cam_c",
                "roi": DEFAULT_ROI,
                "line": DEFAULT_LINE,
                "count_direction": "any",
            }
        )
        store = StreamProfileStore(cfg)

        selected = select_random_stream_profile(
            [profile for profile in store.list_profiles() if profile["id"] in {"profile-b", "profile-c"}],
            "profile-a",
            rng=_FirstChoiceRandom(),
        )

        self.assertEqual("profile-b", selected["id"])

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
        self.assertIn("streamProfileCameraIds", payload)
        self.assertIn("streamRotation", payload)
        self.assertIn("streamSchedule", payload)
        self.assertIn("pending", payload["streamRotation"])
        self.assertIn("pendingEnforcement", payload["streamSchedule"])

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


class _FakeResponse:
    def __init__(self, payload=None):
        self._payload = payload if payload is not None else []

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self):
        self.get_payloads = {}
        self.posts = []
        self.deletes = []

    def get(self, url, headers=None, params=None, timeout=None):
        return _FakeResponse(self.get_payloads.get(url, []))

    def post(self, url, headers=None, params=None, json=None, timeout=None):
        self.posts.append({"url": url, "json": json, "params": params})
        return _FakeResponse([])

    def delete(self, url, headers=None, params=None, timeout=None):
        self.deletes.append({"url": url, "params": params})
        return _FakeResponse([])


class SupabaseSyncTests(unittest.TestCase):
    def test_schedule_rules_round_trip_uses_separate_table(self):
        sync = SupabaseStreamProfileSync(
            url="https://example.supabase.co",
            service_key="service-role",
            table="stream_profiles",
            schedule_table="stream_schedule_rules",
            scope="videoBetTransit",
        )
        fake_session = _FakeSession()
        sync._session = fake_session
        fake_session.get_payloads["https://example.supabase.co/rest/v1/stream_schedule_rules"] = [
            {
                "id": "rush",
                "name": "Rush",
                "enabled": True,
                "start_time": "08:00",
                "end_time": "10:00",
                "allowed_profile_ids": ["profile-a"],
                "timezone": "America/Sao_Paulo",
            }
        ]

        rules, timezone_name = sync.fetch_schedule_rules()
        sync.upsert_schedule_rules(rules, timezone_name)

        self.assertEqual("America/Sao_Paulo", timezone_name)
        self.assertEqual("rush", rules[0]["id"])
        self.assertEqual(
            "https://example.supabase.co/rest/v1/stream_schedule_rules",
            fake_session.posts[0]["url"],
        )
        self.assertEqual(["profile-a"], fake_session.posts[0]["json"][0]["allowed_profile_ids"])
        self.assertEqual(
            "not.in.(rush)",
            fake_session.deletes[0]["params"]["id"],
        )

    def test_profile_round_trip_includes_secondary_verification_fields(self):
        sync = SupabaseStreamProfileSync(
            url="https://example.supabase.co",
            service_key="service-role",
            table="stream_profiles",
            schedule_table="stream_schedule_rules",
            scope="videoBetTransit",
        )
        fake_session = _FakeSession()
        sync._session = fake_session
        fake_session.get_payloads["https://example.supabase.co/rest/v1/stream_profiles"] = [
            {
                "id": "profile-a",
                "name": "Camera A",
                "stream_url": "rtsp://camera-a/live",
                "camera_id": "cam_a",
                "roi": {"x": 1, "y": 2, "w": 3, "h": 4},
                "line": {"x1": 10, "y1": 20, "x2": 30, "y2": 40},
                "count_direction": "down",
                "secondary_verification_enabled": True,
                "secondary_verification_band_px": 22,
                "is_selected": True,
            }
        ]

        profiles, selected_profile_id = sync.fetch_profiles()
        sync.upsert_profiles(profiles, selected_profile_id)

        self.assertTrue(profiles[0]["secondary_verification_enabled"])
        self.assertEqual(22, profiles[0]["secondary_verification_band_px"])
        self.assertTrue(fake_session.posts[0]["json"][0]["secondary_verification_enabled"])
        self.assertEqual(22, fake_session.posts[0]["json"][0]["secondary_verification_band_px"])


if __name__ == "__main__":
    unittest.main()
