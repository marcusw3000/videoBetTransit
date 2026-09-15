from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import time
from worker_defaults import DEFAULT_STREAM_SCHEDULE


def normalize_schedule_timezone(value) -> str:
    timezone_name = str(value or DEFAULT_STREAM_SCHEDULE["timezone"]).strip() or DEFAULT_STREAM_SCHEDULE["timezone"]
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return DEFAULT_STREAM_SCHEDULE["timezone"]
    return timezone_name



def normalize_outside_window_behavior(value) -> str:
    normalized = str(value or DEFAULT_STREAM_SCHEDULE["outside_window_behavior"]).strip().lower()
    if normalized in {"allow_all", "restrict_configured"}:
        return normalized
    return DEFAULT_STREAM_SCHEDULE["outside_window_behavior"]



def normalize_schedule_time_text(value: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.strptime(text, "%H:%M")
    except ValueError as exc:
        raise ValueError("Horario da agenda deve estar no formato HH:MM.") from exc
    return parsed.strftime("%H:%M")



def schedule_time_to_minutes(value: str) -> int:
    normalized = normalize_schedule_time_text(value)
    hours, minutes = normalized.split(":")
    return int(hours) * 60 + int(minutes)



def make_stream_schedule_rule_id(existing_ids: set[str]) -> str:
    base = f"schedule_{int(time.time() * 1000)}"
    candidate = base
    suffix = 1
    while candidate in existing_ids:
        suffix += 1
        candidate = f"{base}_{suffix}"
    return candidate



def normalize_allowed_profile_ids(value) -> list[str]:
    normalized: list[str] = []
    for raw_value in value if isinstance(value, list) else []:
        profile_id = str(raw_value or "").strip()
        if profile_id and profile_id not in normalized:
            normalized.append(profile_id)
    return normalized



def expand_schedule_rule_windows(start_minutes: int, end_minutes: int) -> list[tuple[int, int]]:
    if start_minutes == end_minutes:
        raise ValueError("A agenda por hora nao pode ter duracao zero.")
    if end_minutes > start_minutes:
        return [(start_minutes, end_minutes)]
    return [
        (start_minutes, 24 * 60),
        (0, end_minutes),
    ]



def schedule_windows_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]



def validate_stream_schedule_rules(rules: list[dict], profile_ids: set[str]) -> None:
    expanded_rules: list[tuple[str, str, tuple[int, int], set[str]]] = []
    for rule in rules:
        rule_id = str(rule.get("id") or "").strip()
        rule_name = str(rule.get("name") or "").strip() or rule_id or "agenda"
        allowed_ids = normalize_allowed_profile_ids(rule.get("allowed_profile_ids"))
        if not allowed_ids:
            raise ValueError(f"A agenda '{rule_name}' precisa de ao menos uma stream permitida.")
        missing_ids = [profile_id for profile_id in allowed_ids if profile_id not in profile_ids]
        if missing_ids:
            raise ValueError(f"A agenda '{rule_name}' referencia streams inexistentes na esteira.")
        if not bool(rule.get("enabled", True)):
            continue

        start_minutes = schedule_time_to_minutes(rule.get("start_time"))
        end_minutes = schedule_time_to_minutes(rule.get("end_time"))
        for window in expand_schedule_rule_windows(start_minutes, end_minutes):
            expanded_rules.append((rule_id, rule_name, window, set(allowed_ids)))

    for index, (rule_id, rule_name, window, allowed_ids) in enumerate(expanded_rules):
        for other_rule_id, other_rule_name, other_window, other_allowed_ids in expanded_rules[index + 1:]:
            if rule_id == other_rule_id:
                continue
            if allowed_ids.isdisjoint(other_allowed_ids):
                continue
            if schedule_windows_overlap(window, other_window):
                raise ValueError(
                    f"As agendas '{rule_name}' e '{other_rule_name}' nao podem se sobrepor para a mesma camera."
                )



def build_stream_schedule_rule(
    source: dict | None,
    profile_ids: set[str],
    *,
    existing_ids: set[str] | None = None,
) -> dict:
    source = source if isinstance(source, dict) else {}
    known_ids = existing_ids if isinstance(existing_ids, set) else set()
    rule_id = str(source.get("id") or "").strip()
    if not rule_id or rule_id in known_ids:
        rule_id = make_stream_schedule_rule_id(known_ids)
    start_time = normalize_schedule_time_text(source.get("start_time") or source.get("startTime") or "")
    end_time = normalize_schedule_time_text(source.get("end_time") or source.get("endTime") or "")
    rule = {
        "id": rule_id,
        "name": str(source.get("name") or "").strip() or f"Agenda {start_time}-{end_time}",
        "enabled": bool(source.get("enabled", True)),
        "start_time": start_time,
        "end_time": end_time,
        "allowed_profile_ids": normalize_allowed_profile_ids(source.get("allowed_profile_ids")),
    }
    validate_stream_schedule_rules([rule], profile_ids)
    return rule



def normalize_stream_schedule_config(value, profiles: list[dict]) -> dict:
    source = value if isinstance(value, dict) else {}
    profile_ids = {
        str(profile.get("id") or "").strip()
        for profile in profiles
        if str(profile.get("id") or "").strip()
    }
    rules: list[dict] = []
    existing_ids: set[str] = set()

    for raw_rule in source.get("rules", []) if isinstance(source.get("rules"), list) else []:
        rule = build_stream_schedule_rule(raw_rule, profile_ids, existing_ids=existing_ids)
        existing_ids.add(rule["id"])
        rules.append(rule)

    validate_stream_schedule_rules(rules, profile_ids)
    rules.sort(key=lambda item: (schedule_time_to_minutes(item["start_time"]), str(item.get("id") or "")))
    return {
        "timezone": normalize_schedule_timezone(source.get("timezone")),
        "outside_window_behavior": normalize_outside_window_behavior(source.get("outside_window_behavior")),
        "rules": rules,
    }



def schedule_rule_is_active(rule: dict, current_minutes: int) -> bool:
    start_minutes = schedule_time_to_minutes(rule.get("start_time"))
    end_minutes = schedule_time_to_minutes(rule.get("end_time"))
    if end_minutes > start_minutes:
        return start_minutes <= current_minutes < end_minutes
    return current_minutes >= start_minutes or current_minutes < end_minutes



def format_stream_schedule_window(rule: dict | None) -> str:
    if not isinstance(rule, dict):
        return ""
    start_time = str(rule.get("start_time") or "").strip()
    end_time = str(rule.get("end_time") or "").strip()
    if not start_time or not end_time:
        return ""
    return f"{start_time}-{end_time}"



def resolve_stream_schedule_state(
    schedule: dict | None,
    profiles: list[dict],
    *,
    now: datetime | None = None,
) -> dict:
    normalized = normalize_stream_schedule_config(schedule, profiles)
    timezone_name = normalized["timezone"]
    tzinfo = ZoneInfo(timezone_name)
    current_time = now.astimezone(tzinfo) if isinstance(now, datetime) else datetime.now(tzinfo)
    current_minutes = current_time.hour * 60 + current_time.minute
    profiles_by_id = {
        str(profile.get("id") or "").strip(): dict(profile)
        for profile in profiles
        if str(profile.get("id") or "").strip()
    }

    active_rules = [
        dict(rule)
        for rule in normalized["rules"]
        if bool(rule.get("enabled", True)) and schedule_rule_is_active(rule, current_minutes)
    ]
    has_enabled_rules = any(bool(rule.get("enabled", True)) for rule in normalized["rules"])
    outside_window_behavior = normalize_outside_window_behavior(normalized.get("outside_window_behavior"))
    configured_profile_ids = {
        str(profile_id or "").strip()
        for rule in normalized["rules"]
        if bool(rule.get("enabled", True))
        for profile_id in rule.get("allowed_profile_ids", [])
        if str(profile_id or "").strip()
    }
    always_allowed_profile_ids = [
        profile_id
        for profile_id in profiles_by_id
        if profile_id not in configured_profile_ids
    ]

    if not active_rules:
        if has_enabled_rules and outside_window_behavior == "restrict_configured":
            eligible_profiles = [
                dict(profiles_by_id[profile_id])
                for profile_id in always_allowed_profile_ids
            ]
        else:
            eligible_profiles = [dict(profile) for profile in profiles]
    else:
        eligible_profile_ids: list[str] = []
        seen_ids: set[str] = set()
        for profile_id in always_allowed_profile_ids:
            if profile_id in profiles_by_id and profile_id not in seen_ids:
                eligible_profile_ids.append(profile_id)
                seen_ids.add(profile_id)
        for rule in active_rules:
            for profile_id in rule.get("allowed_profile_ids", []):
                profile_id = str(profile_id or "").strip()
                if profile_id and profile_id not in seen_ids and profile_id in profiles_by_id:
                    eligible_profile_ids.append(profile_id)
                    seen_ids.add(profile_id)
        eligible_profiles = [
            dict(profiles_by_id[profile_id])
            for profile_id in eligible_profile_ids
        ]

    active_rule = dict(active_rules[0]) if active_rules else None
    active_rule_names = [str(rule.get("name") or "").strip() for rule in active_rules if str(rule.get("name") or "").strip()]
    active_windows = []
    for rule in active_rules:
        window = format_stream_schedule_window(rule)
        if window and window not in active_windows:
            active_windows.append(window)

    return {
        "timezone": timezone_name,
        "activeRule": active_rule,
        "activeRules": active_rules,
        "activeRuleIds": [str(rule.get("id") or "").strip() for rule in active_rules if str(rule.get("id") or "").strip()],
        "activeRuleName": " + ".join(active_rule_names),
        "activeWindow": " | ".join(active_windows),
        "outsideWindowBehavior": outside_window_behavior,
        "outsideWindowRestricted": bool(
            has_enabled_rules
            and not active_rules
            and outside_window_behavior == "restrict_configured"
            and not eligible_profiles
        ),
        "eligibleProfiles": eligible_profiles,
        "eligibleProfileIds": [str(profile.get("id") or "").strip() for profile in eligible_profiles if str(profile.get("id") or "").strip()],
        "isRestricted": bool(active_rules) or bool(has_enabled_rules and outside_window_behavior == "restrict_configured"),
        "currentTime": current_time,
    }



def is_profile_allowed_by_schedule(profile: dict | None, schedule_state: dict | None) -> bool:
    if not isinstance(profile, dict):
        return False
    if not isinstance(schedule_state, dict):
        return True
    eligible_ids = set(schedule_state.get("eligibleProfileIds") or [])
    if not schedule_state.get("isRestricted"):
        return True
    return str(profile.get("id") or "").strip() in eligible_ids



def choose_schedule_enforcement_profile(
    current_profile: dict | None,
    eligible_profiles: list[dict],
) -> dict | None:
    current_profile_id = str((current_profile or {}).get("id") or "").strip()
    for profile in eligible_profiles:
        if str(profile.get("id") or "").strip() == current_profile_id:
            return dict(profile)
    if eligible_profiles:
        return dict(eligible_profiles[0])
    return None



def format_stream_schedule_rule_row(profile_labels_by_id: dict[str, str], rule: dict, *, active: bool = False) -> tuple[str, str, str, str]:
    allowed_labels = [
        profile_labels_by_id.get(profile_id, profile_id)
        for profile_id in rule.get("allowed_profile_ids", [])
        if str(profile_id or "").strip()
    ]
    profiles_label = ", ".join(allowed_labels[:3])
    if len(allowed_labels) > 3:
        profiles_label += f" +{len(allowed_labels) - 3}"
    return (
        "Ativa" if active else ("Ligada" if bool(rule.get("enabled", True)) else "Pausada"),
        str(rule.get("name") or "").strip(),
        format_stream_schedule_window(rule),
        profiles_label,
    )

