DEFAULT_ROI = {"x": 0, "y": 0, "w": 0, "h": 0}

DEFAULT_LINE = {"x1": 0, "y1": 0, "x2": 0, "y2": 0}

DEFAULT_STREAM_ROTATION = {
    "enabled": False,
    "mode": "round_boundary",
    "strategy": "uniform_excluding_current",
    "min_rounds_per_stream": 6,
    "max_rounds_per_stream": 11,
    "current_stream_profile_id": "",
    "rounds_on_current_stream": 0,
    "target_rounds_for_current_stream": 0,
    "last_counted_round_id": "",
}

DEFAULT_STREAM_SCHEDULE = {
    "timezone": "America/Sao_Paulo",
    "outside_window_behavior": "allow_all",
    "rules": [],
}

DEFAULT_SECONDARY_VERIFICATION_ENABLED = False

DEFAULT_SECONDARY_VERIFICATION_BAND_PX = 18

SECONDARY_VERIFICATION_MIN_BAND_FRAMES = 2

SECONDARY_VERIFICATION_MIN_PROGRESS_PX = 6

STREAM_ROTATION_SAFE_STATUSES = {"settling", "settled", "void"}

STREAM_ROTATION_DEFER_STATUSES = {"open", "closing"}
