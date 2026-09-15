from __future__ import annotations
import json
import os
import random
import time
import logging
from datetime import datetime
from urllib.parse import urlparse
from supabase_sync import SupabaseStreamProfileSync
from worker_defaults import (DEFAULT_ROI, DEFAULT_LINE, DEFAULT_STREAM_ROTATION, DEFAULT_STREAM_SCHEDULE, DEFAULT_SECONDARY_VERIFICATION_ENABLED, DEFAULT_SECONDARY_VERIFICATION_BAND_PX, SECONDARY_VERIFICATION_MIN_BAND_FRAMES, SECONDARY_VERIFICATION_MIN_PROGRESS_PX, STREAM_ROTATION_SAFE_STATUSES, STREAM_ROTATION_DEFER_STATUSES)
from stream_schedule import (normalize_schedule_timezone, normalize_outside_window_behavior, normalize_schedule_time_text, schedule_time_to_minutes, make_stream_schedule_rule_id, normalize_allowed_profile_ids, expand_schedule_rule_windows, schedule_windows_overlap, validate_stream_schedule_rules, build_stream_schedule_rule, normalize_stream_schedule_config, schedule_rule_is_active, format_stream_schedule_window, resolve_stream_schedule_state, is_profile_allowed_by_schedule, choose_schedule_enforcement_profile, format_stream_schedule_rule_row)
logger = logging.getLogger(__name__)


def normalize_roi_config(value, fallback: dict | None = None) -> dict:
    source = value if isinstance(value, dict) else {}
    base = fallback if isinstance(fallback, dict) else DEFAULT_ROI
    return {
        "x": int(source.get("x", base.get("x", 0)) or 0),
        "y": int(source.get("y", base.get("y", 0)) or 0),
        "w": int(source.get("w", base.get("w", 0)) or 0),
        "h": int(source.get("h", base.get("h", 0)) or 0),
    }



def normalize_line_config(value, fallback: dict | None = None) -> dict:
    source = value if isinstance(value, dict) else {}
    base = fallback if isinstance(fallback, dict) else DEFAULT_LINE
    return {
        "x1": int(source.get("x1", base.get("x1", 0)) or 0),
        "y1": int(source.get("y1", base.get("y1", 0)) or 0),
        "x2": int(source.get("x2", base.get("x2", 0)) or 0),
        "y2": int(source.get("y2", base.get("y2", 0)) or 0),
    }



def normalize_count_direction(value) -> str:
    direction = str(value or "any").strip().lower()
    aliases = {
        "down_to_up": "up",
        "up_to_down": "down",
        "left_to_right": "right",
        "right_to_left": "left",
        "qualquer direcao": "any",
        "cima para baixo": "down",
        "baixo para cima": "up",
        "esquerda para direita": "right",
        "direita para esquerda": "left",
    }
    direction = aliases.get(direction, direction)
    if direction in {"up", "down", "left", "right", "any"}:
        return direction
    return "any"



def normalize_secondary_verification_enabled(value) -> bool:
    if isinstance(value, str):
        return str(value).strip().lower() in {"1", "true", "yes", "on", "sim"}
    return bool(value)



def normalize_secondary_verification_band_px(value, fallback: int | None = None) -> int:
    base = (
        DEFAULT_SECONDARY_VERIFICATION_BAND_PX
        if fallback is None
        else int(fallback or DEFAULT_SECONDARY_VERIFICATION_BAND_PX)
    )
    try:
        band_px = int(value if value is not None else base)
    except (TypeError, ValueError):
        band_px = base
    return max(4, min(120, band_px))



def normalize_stream_rotation_config(value) -> dict:
    source = value if isinstance(value, dict) else {}
    mode = str(source.get("mode") or DEFAULT_STREAM_ROTATION["mode"]).strip().lower()
    strategy = str(source.get("strategy") or DEFAULT_STREAM_ROTATION["strategy"]).strip().lower()
    min_rounds = int(source.get("min_rounds_per_stream", DEFAULT_STREAM_ROTATION["min_rounds_per_stream"]) or 0)
    max_rounds = int(source.get("max_rounds_per_stream", DEFAULT_STREAM_ROTATION["max_rounds_per_stream"]) or 0)
    min_rounds = max(1, min_rounds)
    max_rounds = max(min_rounds, max_rounds)
    target_rounds = int(source.get("target_rounds_for_current_stream", 0) or 0)

    if mode != "round_boundary":
        mode = DEFAULT_STREAM_ROTATION["mode"]
    if strategy != "uniform_excluding_current":
        strategy = DEFAULT_STREAM_ROTATION["strategy"]

    return {
        "enabled": bool(source.get("enabled", DEFAULT_STREAM_ROTATION["enabled"])),
        "mode": mode,
        "strategy": strategy,
        "min_rounds_per_stream": min_rounds,
        "max_rounds_per_stream": max_rounds,
        "current_stream_profile_id": str(source.get("current_stream_profile_id") or "").strip(),
        "rounds_on_current_stream": max(0, int(source.get("rounds_on_current_stream", 0) or 0)),
        "target_rounds_for_current_stream": target_rounds if min_rounds <= target_rounds <= max_rounds else 0,
        "last_counted_round_id": str(source.get("last_counted_round_id") or "").strip(),
    }



def get_round_status(backend_round: dict | None) -> str:
    if not isinstance(backend_round, dict):
        return ""
    return str(backend_round.get("status") or "").strip().lower()



def get_round_id(backend_round: dict | None) -> str:
    if not isinstance(backend_round, dict):
        return ""
    return str(backend_round.get("roundId") or "").strip()



def is_round_safe_for_stream_rotation(backend_round: dict | None) -> bool:
    return get_round_status(backend_round) in STREAM_ROTATION_SAFE_STATUSES



def should_defer_stream_rotation(backend_round: dict | None) -> bool:
    status = get_round_status(backend_round)
    return not status or status in STREAM_ROTATION_DEFER_STATUSES or status not in STREAM_ROTATION_SAFE_STATUSES



def select_random_stream_profile(
    profiles: list[dict],
    current_profile_id: str = "",
    *,
    rng=random,
) -> dict | None:
    eligible = [
        dict(profile)
        for profile in profiles
        if str(profile.get("id") or "").strip()
        and str(profile.get("stream_url") or "").strip()
        and str(profile.get("camera_id") or "").strip()
    ]
    if len(eligible) < 2:
        return None

    current_profile_id = str(current_profile_id or "").strip()
    candidates = [
        profile for profile in eligible
        if str(profile.get("id") or "").strip() != current_profile_id
    ]
    if not candidates:
        candidates = eligible

    return dict(rng.choice(candidates))



def should_apply_pending_stream_rotation(
    pending_profile: dict | None,
    backend_round: dict | None,
) -> bool:
    return isinstance(pending_profile, dict) and is_round_safe_for_stream_rotation(backend_round)



def choose_stream_rotation_target(rotation: dict, *, rng=random) -> int:
    normalized = normalize_stream_rotation_config(rotation)
    return int(rng.randint(
        normalized["min_rounds_per_stream"],
        normalized["max_rounds_per_stream"],
    ))



def ensure_stream_rotation_profile_state(
    rotation: dict,
    stream_profile_id: str,
    *,
    rng=random,
    force_new_target: bool = False,
) -> bool:
    profile_id = str(stream_profile_id or "").strip()
    previous_profile_id = str(rotation.get("current_stream_profile_id") or "").strip()
    changed = previous_profile_id != profile_id

    if changed:
        rotation["current_stream_profile_id"] = profile_id
        rotation["rounds_on_current_stream"] = 0
        rotation["last_counted_round_id"] = ""

    if changed or force_new_target or int(rotation.get("target_rounds_for_current_stream", 0) or 0) <= 0:
        rotation["target_rounds_for_current_stream"] = choose_stream_rotation_target(rotation, rng=rng)
        return True

    return changed



def count_settled_round_for_stream_rotation(rotation: dict, backend_round: dict | None) -> bool:
    if get_round_status(backend_round) not in {"settling", "settled"}:
        return False

    round_id = get_round_id(backend_round)
    if not round_id or round_id == str(rotation.get("last_counted_round_id") or ""):
        return False

    rotation["last_counted_round_id"] = round_id
    rotation["rounds_on_current_stream"] = max(
        0,
        int(rotation.get("rounds_on_current_stream", 0) or 0),
    ) + 1
    return True



def stream_rotation_target_reached(rotation: dict) -> bool:
    target = int(rotation.get("target_rounds_for_current_stream", 0) or 0)
    if target <= 0:
        return False
    rounds = int(rotation.get("rounds_on_current_stream", 0) or 0)
    return rounds >= target



def format_stream_rotation_progress(rotation: dict) -> str:
    if not rotation.get("enabled"):
        return "Rotacao randômica desativada."
    rounds = int(rotation.get("rounds_on_current_stream", 0) or 0)
    target = int(rotation.get("target_rounds_for_current_stream", 0) or 0)
    if target <= 0:
        return "Rotacao ativa: alvo ainda nao sorteado."
    return f"Rotacao ativa: {rounds}/{target} rounds nesta stream"



def shorten_text(value: str, max_len: int = 56) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3]}..."



def guess_stream_profile_name(stream_url: str, camera_id: str = "", index: int = 1) -> str:
    camera_id = str(camera_id or "").strip()
    if camera_id:
        return camera_id

    url = str(stream_url or "").strip()
    if url:
        parsed = urlparse(url)
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[-1].lower().startswith("stream"):
            return path_parts[-2]
        if path_parts:
            return path_parts[-1]
        if parsed.netloc:
            return parsed.netloc

    return f"Stream {index}"



def format_stream_profile_label(profile: dict) -> str:
    name = str(profile.get("name") or "").strip() or guess_stream_profile_name(
        profile.get("stream_url", ""),
        profile.get("camera_id", ""),
    )
    camera_id = str(profile.get("camera_id") or "").strip()
    hint = camera_id or str(profile.get("stream_url") or "").strip()
    hint = shorten_text(hint, max_len=48)
    if hint and hint != name:
        return f"{name} | {hint}"
    return name



def format_stream_profile_table_row(profile: dict, *, active: bool = False) -> tuple[str, str, str, str]:
    name = str(profile.get("name") or "").strip() or guess_stream_profile_name(
        profile.get("stream_url", ""),
        profile.get("camera_id", ""),
    )
    camera_id = str(profile.get("camera_id") or "").strip()
    stream_url = shorten_text(str(profile.get("stream_url") or "").strip(), max_len=72)
    return ("*" if active else "", name, camera_id, stream_url)



def make_stream_profile_id(existing_ids: set[str]) -> str:
    base = f"stream_{int(time.time() * 1000)}"
    candidate = base
    suffix = 1
    while candidate in existing_ids:
        suffix += 1
        candidate = f"{base}_{suffix}"
    return candidate



def build_stream_profile(source: dict | None, fallback_cfg: dict, *, index: int) -> dict:
    source = source if isinstance(source, dict) else {}
    stream_url = validate_stream_url(
        source.get("stream_url")
        or source.get("url")
        or fallback_cfg.get("stream_url", "")
    )
    camera_id = str(source.get("camera_id") or fallback_cfg.get("camera_id", "")).strip()
    profile = {
        "id": str(source.get("id") or "").strip(),
        "name": str(source.get("name") or "").strip(),
        "stream_url": stream_url,
        "camera_id": camera_id,
        "roi": normalize_roi_config(source.get("roi"), fallback_cfg.get("roi")),
        "line": normalize_line_config(source.get("line"), fallback_cfg.get("line")),
        "count_direction": normalize_count_direction(
            source.get("count_direction") or fallback_cfg.get("count_direction", "any")
        ),
        "secondary_verification_enabled": normalize_secondary_verification_enabled(
            source.get("secondary_verification_enabled")
            if "secondary_verification_enabled" in source
            else fallback_cfg.get("secondary_verification_enabled", DEFAULT_SECONDARY_VERIFICATION_ENABLED)
        ),
        "secondary_verification_band_px": normalize_secondary_verification_band_px(
            source.get("secondary_verification_band_px")
            if "secondary_verification_band_px" in source
            else fallback_cfg.get("secondary_verification_band_px", DEFAULT_SECONDARY_VERIFICATION_BAND_PX),
            fallback=int(fallback_cfg.get("secondary_verification_band_px", DEFAULT_SECONDARY_VERIFICATION_BAND_PX) or DEFAULT_SECONDARY_VERIFICATION_BAND_PX),
        ),
    }
    if not profile["name"]:
        profile["name"] = guess_stream_profile_name(stream_url, camera_id, index=index)
    return profile



def sync_config_with_selected_profile(cfg: dict, profile: dict) -> dict:
    profile["roi"] = normalize_roi_config(profile.get("roi"), cfg.get("roi"))
    profile["line"] = normalize_line_config(profile.get("line"), cfg.get("line"))
    profile["count_direction"] = normalize_count_direction(
        profile.get("count_direction") or cfg.get("count_direction", "any")
    )
    profile["secondary_verification_enabled"] = normalize_secondary_verification_enabled(
        profile.get("secondary_verification_enabled")
        if "secondary_verification_enabled" in profile
        else cfg.get("secondary_verification_enabled", DEFAULT_SECONDARY_VERIFICATION_ENABLED)
    )
    profile["secondary_verification_band_px"] = normalize_secondary_verification_band_px(
        profile.get("secondary_verification_band_px")
        if "secondary_verification_band_px" in profile
        else cfg.get("secondary_verification_band_px", DEFAULT_SECONDARY_VERIFICATION_BAND_PX),
        fallback=int(cfg.get("secondary_verification_band_px", DEFAULT_SECONDARY_VERIFICATION_BAND_PX) or DEFAULT_SECONDARY_VERIFICATION_BAND_PX),
    )
    profile["camera_id"] = str(profile.get("camera_id") or cfg.get("camera_id", "")).strip()
    profile["stream_url"] = validate_stream_url(profile.get("stream_url") or "")
    if not profile["name"]:
        profile["name"] = guess_stream_profile_name(profile["stream_url"], profile["camera_id"])

    cfg["selected_stream_profile_id"] = profile["id"]
    cfg["stream_url"] = profile["stream_url"]
    cfg["camera_id"] = profile["camera_id"]
    cfg["roi"] = dict(profile["roi"])
    cfg["line"] = dict(profile["line"])
    cfg["count_direction"] = profile["count_direction"]
    cfg["secondary_verification_enabled"] = bool(profile["secondary_verification_enabled"])
    cfg["secondary_verification_band_px"] = int(profile["secondary_verification_band_px"])
    return profile



def normalize_config(cfg: dict | None) -> dict:
    cfg = dict(cfg or {})
    cfg["youtube_cookies_from_browser"] = str(cfg.get("youtube_cookies_from_browser") or "").strip()
    cfg["youtube_cookies_file"] = str(cfg.get("youtube_cookies_file") or "").strip()
    cfg["secondary_verification_enabled"] = normalize_secondary_verification_enabled(
        cfg.get("secondary_verification_enabled", DEFAULT_SECONDARY_VERIFICATION_ENABLED)
    )
    cfg["secondary_verification_band_px"] = normalize_secondary_verification_band_px(
        cfg.get("secondary_verification_band_px", DEFAULT_SECONDARY_VERIFICATION_BAND_PX)
    )
    cfg["stream_rotation"] = normalize_stream_rotation_config(cfg.get("stream_rotation"))
    raw_profiles = cfg.get("stream_profiles")
    profiles = []

    if isinstance(raw_profiles, list):
        for index, raw_profile in enumerate(raw_profiles, start=1):
            try:
                profile = build_stream_profile(raw_profile, cfg, index=index)
            except ValueError as exc:
                logger.warning("Stream profile ignorado: %s", exc)
                continue
            if profile["stream_url"]:
                profiles.append(profile)

    if not profiles:
        try:
            profiles.append(build_stream_profile({}, cfg, index=1))
        except ValueError:
            fallback_cfg = dict(cfg)
            fallback_cfg["stream_url"] = ""
            profiles.append(build_stream_profile({}, fallback_cfg, index=1))

    existing_ids: set[str] = set()
    for index, profile in enumerate(profiles, start=1):
        if not profile["id"] or profile["id"] in existing_ids:
            profile["id"] = make_stream_profile_id(existing_ids)
        if not profile["name"]:
            profile["name"] = guess_stream_profile_name(
                profile["stream_url"],
                profile["camera_id"],
                index=index,
            )
        existing_ids.add(profile["id"])

    cfg["stream_profiles"] = profiles
    cfg["stream_schedule"] = normalize_stream_schedule_config(cfg.get("stream_schedule"), profiles)
    selected_profile_id = str(cfg.get("selected_stream_profile_id") or "").strip()
    selected_profile = next((profile for profile in profiles if profile["id"] == selected_profile_id), None)
    if selected_profile is None:
        current_stream_url = validate_stream_url(cfg.get("stream_url") or "")
        selected_profile = next((profile for profile in profiles if profile["stream_url"] == current_stream_url), None)
    if selected_profile is None:
        selected_profile = profiles[0]

    sync_config_with_selected_profile(cfg, selected_profile)
    return cfg



def load_config(path: str = "config.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = normalize_config(json.load(f))

    env_overrides = {
        "backend_url": os.getenv("BACKEND_URL"),
        "api_key": os.getenv("BACKEND_API_KEY") or os.getenv("API_KEY"),
        "mjpeg_token": os.getenv("MJPEG_TOKEN"),
        "mediamtx_api_url": os.getenv("MEDIAMTX_API_URL"),
        "mediamtx_rtsp_url": os.getenv("MEDIAMTX_RTSP_URL"),
        "publisher_ffmpeg_bin": os.getenv("FFMPEG_BIN"),
        "supabase_url": os.getenv("SUPABASE_URL"),
        "supabase_service_key": os.getenv("SUPABASE_SERVICE_KEY"),
        "supabase_stream_profiles_table": os.getenv("SUPABASE_STREAM_PROFILES_TABLE"),
        "supabase_stream_schedule_table": os.getenv("SUPABASE_STREAM_SCHEDULE_TABLE"),
        "supabase_stream_profiles_scope": os.getenv("SUPABASE_STREAM_PROFILES_SCOPE"),
        "camera_id": os.getenv("CAMERA_ID"),
        "session_id": os.getenv("SESSION_ID"),
        "line_id": os.getenv("LINE_ID"),
        "stream_url": os.getenv("STREAM_URL"),
        "youtube_cookies_from_browser": os.getenv("YOUTUBE_COOKIES_FROM_BROWSER"),
        "youtube_cookies_file": os.getenv("YOUTUBE_COOKIES_FILE"),
    }

    for key, value in env_overrides.items():
        if value is not None and str(value).strip():
            cfg[key] = value.strip()

    return normalize_config(cfg)



def save_config(path: str, cfg: dict):
    normalized_cfg = normalize_config(cfg)
    cfg.clear()
    cfg.update(normalized_cfg)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized_cfg, f, indent=2)



def bootstrap_stream_profiles_from_supabase(
    cfg: dict,
    config_path: str,
    sync_client: SupabaseStreamProfileSync | None,
) -> None:
    if sync_client is None:
        return

    try:
        remote_profiles, remote_selected_profile_id = sync_client.fetch_profiles()
    except Exception as exc:
        logger.warning("Falha ao carregar stream profiles do Supabase: %s", exc)
        remote_profiles = []
        remote_selected_profile_id = None

    try:
        remote_schedule_rules, remote_schedule_timezone = sync_client.fetch_schedule_rules()
    except Exception as exc:
        logger.warning("Falha ao carregar agenda por hora do Supabase: %s", exc)
        remote_schedule_rules = []
        remote_schedule_timezone = None

    remote_profiles_loaded = bool(remote_profiles)
    remote_schedule_loaded = bool(remote_schedule_rules)

    if remote_profiles_loaded:
        cfg["stream_profiles"] = remote_profiles
        if remote_selected_profile_id:
            cfg["selected_stream_profile_id"] = remote_selected_profile_id

    if remote_schedule_loaded:
        current_schedule = cfg.get("stream_schedule") if isinstance(cfg.get("stream_schedule"), dict) else {}
        cfg["stream_schedule"] = {
            "timezone": remote_schedule_timezone or current_schedule.get("timezone") or DEFAULT_STREAM_SCHEDULE["timezone"],
            "rules": remote_schedule_rules,
        }

    if remote_profiles_loaded or remote_schedule_loaded:
        try:
            normalize_config(cfg)
            save_config(config_path, cfg)
            if remote_profiles_loaded:
                logger.info(
                    "Stream profiles carregados do Supabase: %d perfil(is)",
                    len(cfg.get("stream_profiles", [])),
                )
            if remote_schedule_loaded:
                logger.info(
                    "Agenda por hora carregada do Supabase: %d regra(s)",
                    len(cfg.get("stream_schedule", {}).get("rules", [])),
                )
        except Exception as exc:
            logger.warning("Falha ao aplicar estado remoto de streams/agendas: %s", exc)

    if not remote_profiles_loaded:
        try:
            sync_client.upsert_profiles(
                cfg.get("stream_profiles", []),
                cfg.get("selected_stream_profile_id"),
            )
            logger.info(
                "Supabase sem stream profiles. Config local publicada com %d perfil(is).",
                len(cfg.get("stream_profiles", [])),
            )
        except Exception as exc:
            logger.warning("Falha ao publicar stream profiles iniciais no Supabase: %s", exc)

    if not remote_schedule_loaded:
        try:
            sync_client.upsert_schedule_rules(
                cfg.get("stream_schedule", {}).get("rules", []),
                cfg.get("stream_schedule", {}).get("timezone", DEFAULT_STREAM_SCHEDULE["timezone"]),
            )
            logger.info(
                "Supabase sem agenda por hora. Config local publicada com %d regra(s).",
                len(cfg.get("stream_schedule", {}).get("rules", [])),
            )
        except Exception as exc:
            logger.warning("Falha ao publicar agenda por hora inicial no Supabase: %s", exc)



def sync_stream_profiles_to_supabase(
    cfg: dict,
    sync_client: SupabaseStreamProfileSync | None,
) -> None:
    if sync_client is None:
        return

    try:
        sync_client.upsert_profiles(
            cfg.get("stream_profiles", []),
            cfg.get("selected_stream_profile_id"),
        )
        sync_client.upsert_schedule_rules(
            cfg.get("stream_schedule", {}).get("rules", []),
            cfg.get("stream_schedule", {}).get("timezone", DEFAULT_STREAM_SCHEDULE["timezone"]),
        )
    except Exception as exc:
        logger.warning("Falha ao sincronizar esteira no Supabase: %s", exc)



def get_selected_stream_profile(cfg: dict) -> dict:
    selected_id = str(cfg.get("selected_stream_profile_id") or "").strip()
    profiles = cfg.get("stream_profiles", [])
    for profile in profiles:
        if profile.get("id") == selected_id:
            return profile
    if profiles:
        return profiles[0]
    profile = build_stream_profile({}, cfg, index=1)
    cfg["stream_profiles"] = [profile]
    return sync_config_with_selected_profile(cfg, profile)



class StreamProfileStore:
    def __init__(self, cfg: dict):
        normalized_cfg = normalize_config(cfg)
        cfg.clear()
        cfg.update(normalized_cfg)
        self.cfg = cfg

    def list_profiles(self) -> list[dict]:
        return [dict(profile) for profile in self.cfg.get("stream_profiles", [])]

    def get_selected_profile(self) -> dict:
        return dict(get_selected_stream_profile(self.cfg))

    def select_profile(self, profile_id: str) -> dict:
        for profile in self.cfg.get("stream_profiles", []):
            if profile.get("id") == profile_id:
                return dict(sync_config_with_selected_profile(self.cfg, profile))
        raise ValueError("Stream selecionada nao encontrada.")

    def delete_profile(self, profile_id: str) -> dict:
        target_id = str(profile_id or "").strip()
        profiles = self.cfg.get("stream_profiles", [])
        if len(profiles) <= 1:
            raise ValueError("A esteira precisa manter pelo menos uma stream salva.")

        selected_id = str(self.cfg.get("selected_stream_profile_id") or "").strip()
        if target_id == selected_id:
            raise ValueError("Carregue outra stream antes de apagar esta.")

        for index, profile in enumerate(profiles):
            if str(profile.get("id") or "") == target_id:
                deleted = dict(profile)
                del profiles[index]
                self.cfg["stream_profiles"] = profiles
                return deleted

        raise ValueError("Stream selecionada nao encontrada.")

    def save_selected_profile(
        self,
        *,
        name: str | None = None,
        camera_id: str | None = None,
        stream_url: str | None = None,
        roi: dict | None = None,
        line: dict | None = None,
        count_direction: str | None = None,
        secondary_verification_enabled: bool | None = None,
        secondary_verification_band_px: int | None = None,
    ) -> dict:
        current = get_selected_stream_profile(self.cfg)
        target_url = validate_stream_url(stream_url or current.get("stream_url") or "")
        target_camera_id = str(camera_id or current.get("camera_id") or self.cfg.get("camera_id") or "").strip()
        if not target_url:
            raise ValueError("Informe uma URL de stream antes de salvar.")
        if not target_camera_id:
            raise ValueError("Informe um camera_id antes de salvar.")

        selected_stream_url = str(current.get("stream_url") or "").strip()
        selected_camera_id = str(current.get("camera_id") or "").strip()
        if target_url != selected_stream_url or target_camera_id != selected_camera_id:
            for profile in self.cfg.get("stream_profiles", []):
                if (
                    str(profile.get("stream_url") or "").strip() == target_url
                    and str(profile.get("camera_id") or "").strip() == target_camera_id
                ):
                    current = profile
                    break
            else:
                current = {
                    "id": make_stream_profile_id({str(profile.get("id") or "") for profile in self.cfg.get("stream_profiles", [])}),
                    "name": "",
                    "stream_url": target_url,
                    "camera_id": target_camera_id,
                    "roi": dict(self.cfg.get("roi") or DEFAULT_ROI),
                    "line": dict(self.cfg.get("line") or DEFAULT_LINE),
                    "count_direction": self.cfg.get("count_direction", "any"),
                    "secondary_verification_enabled": normalize_secondary_verification_enabled(
                        self.cfg.get("secondary_verification_enabled", DEFAULT_SECONDARY_VERIFICATION_ENABLED)
                    ),
                    "secondary_verification_band_px": normalize_secondary_verification_band_px(
                        self.cfg.get("secondary_verification_band_px", DEFAULT_SECONDARY_VERIFICATION_BAND_PX)
                    ),
                }
                self.cfg.setdefault("stream_profiles", []).append(current)

        if name is not None:
            current["name"] = str(name).strip()
        current["stream_url"] = target_url
        current["camera_id"] = target_camera_id
        if roi is not None:
            current["roi"] = normalize_roi_config(roi, current.get("roi"))
        if line is not None:
            current["line"] = normalize_line_config(line, current.get("line"))
        if count_direction is not None:
            current["count_direction"] = normalize_count_direction(count_direction)
        if secondary_verification_enabled is not None:
            current["secondary_verification_enabled"] = normalize_secondary_verification_enabled(
                secondary_verification_enabled
            )
        if secondary_verification_band_px is not None:
            current["secondary_verification_band_px"] = normalize_secondary_verification_band_px(
                secondary_verification_band_px,
                fallback=int(current.get("secondary_verification_band_px", DEFAULT_SECONDARY_VERIFICATION_BAND_PX) or DEFAULT_SECONDARY_VERIFICATION_BAND_PX),
            )

        return dict(sync_config_with_selected_profile(self.cfg, current))

    def save_profile_entry(
        self,
        *,
        name: str | None = None,
        camera_id: str | None = None,
        stream_url: str | None = None,
    ) -> tuple[dict, bool]:
        target_url = validate_stream_url(stream_url or "")
        target_camera_id = str(camera_id or "").strip()
        if not target_url:
            raise ValueError("Informe uma URL de stream antes de salvar.")
        if not target_camera_id:
            raise ValueError("Informe um camera_id antes de salvar.")

        current = None
        for profile in self.cfg.get("stream_profiles", []):
            if (
                str(profile.get("stream_url") or "").strip() == target_url
                and str(profile.get("camera_id") or "").strip() == target_camera_id
            ):
                current = profile
                break

        created = current is None
        if current is None:
            current = {
                "id": make_stream_profile_id({str(profile.get("id") or "") for profile in self.cfg.get("stream_profiles", [])}),
                "name": "",
                "stream_url": target_url,
                "camera_id": target_camera_id,
                "roi": dict(DEFAULT_ROI),
                "line": dict(DEFAULT_LINE),
                "count_direction": "any",
                "secondary_verification_enabled": DEFAULT_SECONDARY_VERIFICATION_ENABLED,
                "secondary_verification_band_px": DEFAULT_SECONDARY_VERIFICATION_BAND_PX,
            }
            self.cfg.setdefault("stream_profiles", []).append(current)

        if name is not None:
            current["name"] = str(name).strip()
        if not current.get("name"):
            current["name"] = guess_stream_profile_name(target_url, target_camera_id)
        current["stream_url"] = target_url
        current["camera_id"] = target_camera_id

        return dict(current), created

    def apply_stream_url(
        self,
        stream_url: str,
        *,
        name: str | None = None,
        camera_id: str | None = None,
    ) -> tuple[dict, bool]:
        target_url = validate_stream_url(stream_url or "")
        target_camera_id = str(camera_id or self.cfg.get("camera_id") or "").strip()
        if not target_url:
            raise ValueError("Informe uma URL de stream.")
        if not target_camera_id:
            raise ValueError("Informe um camera_id.")

        for profile in self.cfg.get("stream_profiles", []):
            if (
                str(profile.get("stream_url") or "").strip() == target_url
                and str(profile.get("camera_id") or "").strip() == target_camera_id
            ):
                if name is not None and str(name).strip():
                    profile["name"] = str(name).strip()
                return dict(sync_config_with_selected_profile(self.cfg, profile)), False

        profile = {
            "id": make_stream_profile_id({str(existing.get("id") or "") for existing in self.cfg.get("stream_profiles", [])}),
            "name": str(name or "").strip()
            or guess_stream_profile_name(
                target_url,
                target_camera_id,
                index=len(self.cfg.get("stream_profiles", [])) + 1,
            ),
            "stream_url": target_url,
            "camera_id": target_camera_id,
            "roi": dict(DEFAULT_ROI),
            "line": dict(DEFAULT_LINE),
            "count_direction": "any",
            "secondary_verification_enabled": DEFAULT_SECONDARY_VERIFICATION_ENABLED,
            "secondary_verification_band_px": DEFAULT_SECONDARY_VERIFICATION_BAND_PX,
        }
        self.cfg.setdefault("stream_profiles", []).append(profile)
        return dict(sync_config_with_selected_profile(self.cfg, profile)), True



class StreamScheduleStore:
    def __init__(self, cfg: dict):
        normalized_cfg = normalize_config(cfg)
        cfg.clear()
        cfg.update(normalized_cfg)
        self.cfg = cfg

    def list_rules(self) -> list[dict]:
        return [dict(rule) for rule in self.cfg.get("stream_schedule", {}).get("rules", [])]

    def get_schedule(self) -> dict:
        schedule = normalize_stream_schedule_config(
            self.cfg.get("stream_schedule"),
            self.cfg.get("stream_profiles", []),
        )
        self.cfg["stream_schedule"] = schedule
        return {
            "timezone": schedule.get("timezone", DEFAULT_STREAM_SCHEDULE["timezone"]),
            "rules": [dict(rule) for rule in schedule.get("rules", [])],
        }

    def save_rule(
        self,
        *,
        rule_id: str = "",
        name: str | None = None,
        start_time: str,
        end_time: str,
        allowed_profile_ids: list[str],
        enabled: bool,
    ) -> tuple[dict, bool]:
        schedule = self.get_schedule()
        rules = schedule["rules"]
        existing_ids = {str(rule.get("id") or "").strip() for rule in rules}
        target_rule_id = str(rule_id or "").strip()
        created = not target_rule_id

        if created:
            target_rule_id = make_stream_schedule_rule_id(existing_ids)

        next_rule = {
            "id": target_rule_id,
            "name": str(name or "").strip() or f"Agenda {start_time}-{end_time}",
            "enabled": bool(enabled),
            "start_time": start_time,
            "end_time": end_time,
            "allowed_profile_ids": list(allowed_profile_ids or []),
        }

        updated_rules: list[dict] = []
        replaced = False
        for rule in rules:
            if str(rule.get("id") or "").strip() == target_rule_id:
                updated_rules.append(next_rule)
                replaced = True
            else:
                updated_rules.append(dict(rule))

        if not replaced:
            updated_rules.append(next_rule)

        normalized_schedule = normalize_stream_schedule_config(
            {
                "timezone": schedule.get("timezone", DEFAULT_STREAM_SCHEDULE["timezone"]),
                "rules": updated_rules,
            },
            self.cfg.get("stream_profiles", []),
        )
        self.cfg["stream_schedule"] = normalized_schedule
        saved_rule = next(
            dict(rule)
            for rule in normalized_schedule["rules"]
            if str(rule.get("id") or "").strip() == target_rule_id
        )
        return saved_rule, created

    def delete_rule(self, rule_id: str) -> dict:
        target_rule_id = str(rule_id or "").strip()
        schedule = self.get_schedule()
        deleted = None
        remaining_rules: list[dict] = []
        for rule in schedule["rules"]:
            if str(rule.get("id") or "").strip() == target_rule_id:
                deleted = dict(rule)
                continue
            remaining_rules.append(dict(rule))

        if deleted is None:
            raise ValueError("Agenda por hora nao encontrada.")

        self.cfg["stream_schedule"] = normalize_stream_schedule_config(
            {
                "timezone": schedule.get("timezone", DEFAULT_STREAM_SCHEDULE["timezone"]),
                "rules": remaining_rules,
            },
            self.cfg.get("stream_profiles", []),
        )
        return deleted

    def toggle_rule(self, rule_id: str) -> dict:
        target_rule_id = str(rule_id or "").strip()
        schedule = self.get_schedule()
        toggled = None
        updated_rules: list[dict] = []
        for rule in schedule["rules"]:
            next_rule = dict(rule)
            if str(rule.get("id") or "").strip() == target_rule_id:
                next_rule["enabled"] = not bool(rule.get("enabled", True))
                toggled = dict(next_rule)
            updated_rules.append(next_rule)

        if toggled is None:
            raise ValueError("Agenda por hora nao encontrada.")

        self.cfg["stream_schedule"] = normalize_stream_schedule_config(
            {
                "timezone": schedule.get("timezone", DEFAULT_STREAM_SCHEDULE["timezone"]),
                "rules": updated_rules,
            },
            self.cfg.get("stream_profiles", []),
        )
        return next(
            dict(rule)
            for rule in self.cfg["stream_schedule"]["rules"]
            if str(rule.get("id") or "").strip() == target_rule_id
        )

    def assert_profile_not_referenced(self, profile_id: str) -> None:
        target_id = str(profile_id or "").strip()
        for rule in self.list_rules():
            if target_id in rule.get("allowed_profile_ids", []):
                raise ValueError("A stream esta vinculada a uma agenda por hora ativa ou salva.")

    def detach_profile_references(self, profile_id: str) -> dict:
        target_id = str(profile_id or "").strip()
        schedule = self.get_schedule()
        updated_rule_ids: list[str] = []
        deleted_rule_ids: list[str] = []
        next_rules: list[dict] = []

        for rule in schedule["rules"]:
            allowed_ids = [
                str(allowed_profile_id or "").strip()
                for allowed_profile_id in rule.get("allowed_profile_ids", [])
                if str(allowed_profile_id or "").strip()
            ]
            if target_id not in allowed_ids:
                next_rules.append(dict(rule))
                continue

            remaining_ids = [allowed_id for allowed_id in allowed_ids if allowed_id != target_id]
            rule_id = str(rule.get("id") or "").strip()
            if remaining_ids:
                next_rule = dict(rule)
                next_rule["allowed_profile_ids"] = remaining_ids
                next_rules.append(next_rule)
                updated_rule_ids.append(rule_id)
            else:
                deleted_rule_ids.append(rule_id)

        if updated_rule_ids or deleted_rule_ids:
            self.cfg["stream_schedule"] = normalize_stream_schedule_config(
                {
                    "timezone": schedule.get("timezone", DEFAULT_STREAM_SCHEDULE["timezone"]),
                    "rules": next_rules,
                },
                self.cfg.get("stream_profiles", []),
            )

        return {
            "updatedRuleIds": updated_rule_ids,
            "deletedRuleIds": deleted_rule_ids,
        }



def is_blob_url(value: str) -> bool:
    return str(value or "").strip().lower().startswith("blob:")



def validate_stream_url(value: str) -> str:
    stream_url = str(value or "").strip()
    if is_blob_url(stream_url):
        raise ValueError("URL blob do navegador nao pode ser usada. Cole a URL normal do YouTube.")
    return stream_url

